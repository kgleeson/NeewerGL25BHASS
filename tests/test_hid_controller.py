"""Tests for the USB HID controller."""

from __future__ import annotations

import pytest

from custom_components.neewer_gl25b.hid_controller import (
    HEADER,
    NeewerGL25BController,
    NeewerGL25BError,
)


def test_brightness_packet(fake_hid) -> None:
    NeewerGL25BController().set_brightness(50)

    assert len(fake_hid.packets) == 1
    packet = fake_hid.packets[0]
    assert len(packet) == 64
    assert packet.startswith(HEADER + bytes.fromhex("77 58 01 82 32 8c"))
    assert set(packet[len(HEADER) + 6 :]) == {0}


@pytest.mark.parametrize(("percent", "sent"), [(-5, 0), (0, 0), (100, 100), (250, 100)])
def test_brightness_is_clamped(fake_hid, percent: int, sent: int) -> None:
    NeewerGL25BController().set_brightness(percent)
    assert fake_hid.bodies == [bytes.fromhex("77 58 01 82") + bytes([sent, 0x8C])]


@pytest.mark.parametrize(
    ("kelvin", "sent"), [(5650, 56), (2900, 29), (1000, 29), (7000, 70), (9000, 70)]
)
def test_kelvin_is_clamped_and_rounded_down(fake_hid, kelvin: int, sent: int) -> None:
    NeewerGL25BController().set_kelvin(kelvin)
    assert fake_hid.bodies == [bytes.fromhex("77 58 01 83") + bytes([sent, 0x8C])]


def test_toggle_packet(fake_hid) -> None:
    NeewerGL25BController().toggle()
    assert fake_hid.bodies == [bytes.fromhex("77 58 01 85 01 56")]


def test_handle_is_reused(fake_hid) -> None:
    controller = NeewerGL25BController()
    controller.set_brightness(10)
    controller.set_brightness(20)
    assert len(fake_hid.opened) == 1


def test_missing_dongle_raises(fake_hid) -> None:
    fake_hid.present = False
    controller = NeewerGL25BController()

    assert controller.connect() is False
    with pytest.raises(NeewerGL25BError):
        controller.set_brightness(10)
    assert not controller.is_connected()


def test_failed_write_drops_handle(fake_hid) -> None:
    """A write that returns -1 must not leave a dead handle behind."""
    controller = NeewerGL25BController()
    assert controller.connect()

    fake_hid.unplug()
    with pytest.raises(NeewerGL25BError):
        controller.set_brightness(10)
    assert not controller.is_connected()

    fake_hid.replug()
    assert controller.connect()
    controller.set_brightness(10)
    assert len(fake_hid.packets) == 1


def test_stale_handle_is_reopened_within_one_command(fake_hid) -> None:
    """After an unplug and re-plug the next command reconnects and succeeds."""
    controller = NeewerGL25BController()
    assert controller.connect()

    fake_hid.unplug()
    fake_hid.replug()
    controller.set_brightness(10)

    assert len(fake_hid.packets) == 1
    assert len(fake_hid.opened) == 2


def test_write_exception_drops_handle(fake_hid) -> None:
    controller = NeewerGL25BController()
    assert controller.connect()

    fake_hid.write_raises = True
    with pytest.raises(NeewerGL25BError):
        controller.set_brightness(10)
    assert not controller.is_connected()


def test_check_connection_tracks_unplug_and_replug(fake_hid) -> None:
    controller = NeewerGL25BController()
    assert controller.check_connection() is True
    assert controller.is_connected()

    fake_hid.unplug()
    assert controller.check_connection() is False
    assert not controller.is_connected()

    fake_hid.replug()
    assert controller.check_connection() is True
    assert controller.is_connected()


def test_disconnect_closes_device(fake_hid) -> None:
    controller = NeewerGL25BController()
    controller.connect()
    controller.disconnect()

    assert fake_hid.opened[0].closed
    assert not controller.is_connected()
