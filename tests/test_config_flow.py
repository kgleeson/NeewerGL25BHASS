"""Tests for the config flow."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USB, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.usb import UsbServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.neewer_gl25b.const import DOMAIN

USB_INFO = UsbServiceInfo(
    device="/dev/hidraw0",
    vid="0581",
    pid="011D",
    serial_number=None,
    manufacturer="Neewer",
    description="GL25B dongle",
)


async def test_user_flow_creates_entry(hass: HomeAssistant, fake_hid) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Key Light"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Key Light"
    assert result["data"] == {"name": "Key Light"}
    assert result["result"].unique_id == "0581:011d"


async def test_user_flow_cannot_connect_then_recovers(
    hass: HomeAssistant, fake_hid
) -> None:
    fake_hid.present = False
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Key Light"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    fake_hid.present = True
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Key Light"}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_usb_discovery_shows_form(hass: HomeAssistant, fake_hid) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USB}, data=USB_INFO
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_second_entry_is_aborted(hass: HomeAssistant, fake_hid) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id="0581:011d").add_to_hass(hass)

    for source, data in ((SOURCE_USER, None), (SOURCE_USB, USB_INFO)):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": source}, data=data
        )
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "already_configured"
