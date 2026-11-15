"""Light entity for the Neewer GL25B integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode,
    LightEntity,
)
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.restore_state import RestoreEntity

from . import NeewerGL25BConfigEntry
from .const import (
    DEFAULT_BRIGHTNESS,
    DEFAULT_COLOR_TEMP_KELVIN,
    DOMAIN,
    MAX_KELVIN,
    MIN_KELVIN,
)
from .hid_controller import PID, VID, NeewerGL25BController, NeewerGL25BError

_LOGGER = logging.getLogger(__name__)

CONNECTION_CHECK_INTERVAL = timedelta(seconds=30)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NeewerGL25BConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Neewer GL25B light entity."""
    async_add_entities([NeewerGL25BLight(entry.runtime_data, entry.title)])


class NeewerGL25BLight(LightEntity, RestoreEntity):
    """Representation of a Neewer GL25B light."""

    _attr_supported_color_modes = {ColorMode.COLOR_TEMP}
    _attr_color_mode = ColorMode.COLOR_TEMP
    _attr_min_color_temp_kelvin = MIN_KELVIN
    _attr_max_color_temp_kelvin = MAX_KELVIN
    _attr_assumed_state = True
    _attr_should_poll = False
    # The light is the device's main feature, so it takes the device name.
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(
        self,
        controller: NeewerGL25BController,
        name: str,
    ) -> None:
        """Initialize the Neewer GL25B light."""
        self._controller = controller

        self._attr_unique_id = f"{DOMAIN}_{VID:04x}_{PID:04x}"
        self._attr_is_on = False
        self._attr_available = True
        self._attr_brightness = DEFAULT_BRIGHTNESS
        self._attr_color_temp_kelvin = DEFAULT_COLOR_TEMP_KELVIN
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{VID:04x}:{PID:04x}")},
            manufacturer="Neewer",
            model="GL25B",
            name=name,
        )

    async def async_added_to_hass(self) -> None:
        """Restore the last known state and open the HID device."""
        await super().async_added_to_hass()

        # The light cannot be queried, so the last state Home Assistant recorded
        # is the best available guess after a restart.
        if (last_state := await self.async_get_last_state()) is not None:
            self._attr_is_on = last_state.state == STATE_ON
            if (brightness := last_state.attributes.get(ATTR_BRIGHTNESS)) is not None:
                self._attr_brightness = max(1, min(255, int(brightness)))
            if (kelvin := last_state.attributes.get(ATTR_COLOR_TEMP_KELVIN)) is not None:
                self._attr_color_temp_kelvin = max(
                    MIN_KELVIN, min(MAX_KELVIN, int(kelvin))
                )

        self._attr_available = await self.hass.async_add_executor_job(
            self._controller.connect
        )
        self.async_write_ha_state()

        self.async_on_remove(
            async_track_time_interval(
                self.hass, self._async_check_connection, CONNECTION_CHECK_INTERVAL
            )
        )

    async def _async_check_connection(self, _now: Any) -> None:
        """Track the dongle being unplugged or plugged back in."""
        available = await self.hass.async_add_executor_job(
            self._controller.check_connection
        )
        if available != self._attr_available:
            self._attr_available = available
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light and apply requested state.

        Commands are always sent, even when they match the assumed state: the
        light can be changed with its own controls, so the assumed state may be
        stale.
        """
        requested_brightness = kwargs.get(ATTR_BRIGHTNESS)
        requested_kelvin = kwargs.get(ATTR_COLOR_TEMP_KELVIN)

        target_brightness = (
            requested_brightness
            if requested_brightness is not None
            else self._attr_brightness
        )
        target_brightness = max(1, min(255, int(target_brightness)))

        try:
            if requested_kelvin is not None:
                target_kelvin = max(MIN_KELVIN, min(MAX_KELVIN, int(requested_kelvin)))
                await self.hass.async_add_executor_job(
                    self._controller.set_kelvin, target_kelvin
                )
                self._attr_color_temp_kelvin = target_kelvin

            await self.hass.async_add_executor_job(
                self._controller.set_brightness,
                self._ha_brightness_to_percent(target_brightness),
            )
        except NeewerGL25BError:
            _LOGGER.exception("Failed to turn on Neewer GL25B")
            self._attr_available = False
            self.async_write_ha_state()
            return

        self._attr_is_on = True
        self._attr_available = True
        self._attr_brightness = target_brightness
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light by setting brightness to zero."""
        try:
            await self.hass.async_add_executor_job(self._controller.set_brightness, 0)
        except NeewerGL25BError:
            _LOGGER.exception("Failed to turn off Neewer GL25B")
            self._attr_available = False
            self.async_write_ha_state()
            return

        self._attr_is_on = False
        self._attr_available = True
        self.async_write_ha_state()

    @staticmethod
    def _ha_brightness_to_percent(brightness: int) -> int:
        """Convert Home Assistant brightness 1-255 to GL25B brightness 1-100."""
        return max(1, min(100, round((brightness / 255) * 100)))
