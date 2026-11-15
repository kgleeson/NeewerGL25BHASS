"""Neewer GL25B Home Assistant integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .hid_controller import NeewerGL25BController

PLATFORMS: list[Platform] = [Platform.LIGHT]

type NeewerGL25BConfigEntry = ConfigEntry[NeewerGL25BController]


async def async_setup_entry(hass: HomeAssistant, entry: NeewerGL25BConfigEntry) -> bool:
    """Set up Neewer GL25B from a config entry."""
    entry.runtime_data = NeewerGL25BController()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: NeewerGL25BConfigEntry
) -> bool:
    """Unload a Neewer GL25B config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        await hass.async_add_executor_job(entry.runtime_data.disconnect)

    return unload_ok
