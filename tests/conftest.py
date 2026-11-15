"""Shared fixtures for the Neewer GL25B tests."""

from __future__ import annotations

import pytest

from custom_components.neewer_gl25b import hid_controller


class FakeDevice:
    """Stand-in for a hidapi device handle."""

    def __init__(self, backend: FakeHid) -> None:
        self._backend = backend
        self.closed = False

    def open_path(self, path: bytes) -> None:
        if not self._backend.present:
            raise OSError("open failed")
        self._backend.opened.append(self)

    def write(self, packet: bytes) -> int:
        if self._backend.write_raises:
            raise OSError("write failed")
        # A handle opened before an unplug stays dead after a re-plug.
        if not self._backend.present or self not in self._backend.live:
            return -1
        self._backend.packets.append(bytes(packet))
        return len(packet)

    def close(self) -> None:
        self.closed = True


class FakeHid:
    """Stand-in for the hidapi module."""

    def __init__(self) -> None:
        self.present = True
        self.write_raises = False
        self.packets: list[bytes] = []
        self.opened: list[FakeDevice] = []
        self.live: list[FakeDevice] = []

    def enumerate(self, vid: int, pid: int) -> list[dict]:
        return [{"path": b"fake-path"}] if self.present else []

    def device(self) -> FakeDevice:
        dev = FakeDevice(self)
        self.live.append(dev)
        return dev

    def unplug(self) -> None:
        self.present = False
        self.live.clear()

    def replug(self) -> None:
        self.present = True

    @property
    def bodies(self) -> list[bytes]:
        """Command bodies written so far (header and padding stripped)."""
        return [p[len(hid_controller.HEADER) :].rstrip(b"\x00") for p in self.packets]


@pytest.fixture
def fake_hid(monkeypatch: pytest.MonkeyPatch) -> FakeHid:
    """Replace hidapi with a fake and remove the inter-write delay."""
    fake = FakeHid()
    monkeypatch.setattr(hid_controller, "hid", fake)
    monkeypatch.setattr(hid_controller, "WRITE_DELAY_SECONDS", 0)
    return fake


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load the integration from custom_components."""
