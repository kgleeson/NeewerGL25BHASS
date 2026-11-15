"""Tests for the light entity."""

from __future__ import annotations

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_COLOR_TEMP_KELVIN
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache,
)

from custom_components.neewer_gl25b.const import DOMAIN
from custom_components.neewer_gl25b.light import CONNECTION_CHECK_INTERVAL

BRIGHTNESS = bytes.fromhex("77 58 01 82")
KELVIN = bytes.fromhex("77 58 01 83")
ENTITY_ID = "light.key_light"


def brightness_body(percent: int) -> bytes:
    return BRIGHTNESS + bytes([percent, 0x8C])


def kelvin_body(kelvin: int) -> bytes:
    return KELVIN + bytes([kelvin // 100, 0x8C])


async def setup_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Key Light",
        data={"name": "Key Light"},
        unique_id="0581:011d",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def call(hass: HomeAssistant, service: str, **data) -> None:
    await hass.services.async_call(
        "light", service, {"entity_id": ENTITY_ID, **data}, blocking=True
    )


async def test_setup_names_entity_and_device_from_entry(
    hass: HomeAssistant, fake_hid
) -> None:
    await setup_entry(hass)

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_OFF
    assert state.name == "Key Light"

    entity = er.async_get(hass).async_get(ENTITY_ID)
    assert entity.unique_id == "neewer_gl25b_0581_011d"
    device = dr.async_get(hass).async_get(entity.device_id)
    assert device.name == "Key Light"


async def test_turn_on_and_off(hass: HomeAssistant, fake_hid) -> None:
    await setup_entry(hass)

    await call(hass, "turn_on", brightness=255, color_temp_kelvin=5600)
    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_BRIGHTNESS] == 255
    assert state.attributes[ATTR_COLOR_TEMP_KELVIN] == 5600
    assert fake_hid.bodies == [kelvin_body(5600), brightness_body(100)]

    await call(hass, "turn_off")
    assert hass.states.get(ENTITY_ID).state == STATE_OFF
    assert fake_hid.bodies[-1] == brightness_body(0)


async def test_commands_are_always_sent(hass: HomeAssistant, fake_hid) -> None:
    """Requests matching the assumed state still reach the light."""
    await setup_entry(hass)

    await call(hass, "turn_off")
    assert fake_hid.bodies == [brightness_body(0)]

    await call(hass, "turn_on", brightness=128, color_temp_kelvin=4400)
    await call(hass, "turn_on", brightness=128, color_temp_kelvin=4400)
    assert fake_hid.bodies[1:] == [
        kelvin_body(4400),
        brightness_body(50),
        kelvin_body(4400),
        brightness_body(50),
    ]


async def test_turn_on_without_kelvin_sends_only_brightness(
    hass: HomeAssistant, fake_hid
) -> None:
    await setup_entry(hass)
    await call(hass, "turn_on")
    assert fake_hid.bodies == [brightness_body(50)]


async def test_state_is_restored_after_restart(hass: HomeAssistant, fake_hid) -> None:
    mock_restore_cache(
        hass,
        [
            State(
                ENTITY_ID,
                STATE_ON,
                {ATTR_BRIGHTNESS: 51, ATTR_COLOR_TEMP_KELVIN: 6000},
            )
        ],
    )
    await setup_entry(hass)

    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_BRIGHTNESS] == 51
    assert state.attributes[ATTR_COLOR_TEMP_KELVIN] == 6000
    # Restoring must not send anything to the light.
    assert fake_hid.bodies == []

    await call(hass, "turn_off")
    assert fake_hid.bodies == [brightness_body(0)]

    # Turning back on reuses the restored brightness.
    await call(hass, "turn_on")
    assert fake_hid.bodies[-1] == brightness_body(20)


async def test_unavailable_when_dongle_missing_at_setup(
    hass: HomeAssistant, fake_hid
) -> None:
    fake_hid.present = False
    await setup_entry(hass)
    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE


async def test_unplug_and_replug_are_detected(hass: HomeAssistant, fake_hid) -> None:
    await setup_entry(hass)
    await call(hass, "turn_on")

    fake_hid.unplug()
    async_fire_time_changed(hass, dt_util.utcnow() + CONNECTION_CHECK_INTERVAL)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE

    fake_hid.replug()
    async_fire_time_changed(hass, dt_util.utcnow() + 2 * CONNECTION_CHECK_INTERVAL)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(ENTITY_ID).state == STATE_ON

    await call(hass, "turn_off")
    assert fake_hid.bodies[-1] == brightness_body(0)


async def test_failed_write_marks_unavailable_and_keeps_kelvin(
    hass: HomeAssistant, fake_hid
) -> None:
    await setup_entry(hass)
    await call(hass, "turn_on", color_temp_kelvin=5000)

    fake_hid.write_raises = True
    await call(hass, "turn_on", brightness=200)
    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE

    fake_hid.write_raises = False
    async_fire_time_changed(hass, dt_util.utcnow() + CONNECTION_CHECK_INTERVAL)
    await hass.async_block_till_done(wait_background_tasks=True)

    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_COLOR_TEMP_KELVIN] == 5000


async def test_unload_closes_device(hass: HomeAssistant, fake_hid) -> None:
    entry = await setup_entry(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert fake_hid.opened[0].closed
