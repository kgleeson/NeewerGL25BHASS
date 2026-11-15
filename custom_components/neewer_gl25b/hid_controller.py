"""USB HID controller for the Neewer GL25B dongle."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from .const import MAX_KELVIN, MIN_KELVIN

try:
    import hid
except (
    ImportError
):  # pragma: no cover - Home Assistant installs this from manifest.json.
    hid = None  # type: ignore[assignment]

_LOGGER = logging.getLogger(__name__)

VID = 0x0581
PID = 0x011D
HEADER = bytes.fromhex("ba 70 24 00 00 00 00")
PACKET_LENGTH = 64
WRITE_DELAY_SECONDS = 0.2

BRIGHTNESS_COMMAND = bytes.fromhex("77 58 01 82")
KELVIN_COMMAND = bytes.fromhex("77 58 01 83")
TOGGLE_COMMAND = bytes.fromhex("77 58 01 85 01 56")

MIN_BRIGHTNESS_PERCENT = 0
MAX_BRIGHTNESS_PERCENT = 100


class NeewerGL25BError(Exception):
    """Raised when the Neewer GL25B dongle cannot be controlled."""


class NeewerGL25BController:
    """Synchronous controller for the official Neewer GL25B USB HID dongle.

    Keeps the HID device open for the lifetime of the integration to avoid
    USB re-enumeration on every command (which causes udev initialisation failures).

    All public methods are safe to call from multiple threads; a lock serialises
    access to the HID handle.
    """

    def __init__(self) -> None:
        """Initialise without opening the device."""
        self._dev: Any | None = None
        self._lock = threading.RLock()

    def connect(self) -> bool:
        """Open the HID device. Returns True on success."""
        if hid is None:
            _LOGGER.error("hidapi is not installed")
            return False

        with self._lock:
            if self._dev is not None:
                return True

            try:
                # open_path() is reliable on Linux/hidraw where open(vid, pid) often
                # fails even though hid.enumerate() can see the device.
                matches = hid.enumerate(VID, PID)
                if not matches:
                    _LOGGER.debug(
                        "Neewer GL25B dongle (%04x:%04x) not found by hid.enumerate()",
                        VID,
                        PID,
                    )
                    return False

                dev = hid.device()
                dev.open_path(matches[0]["path"])
                self._dev = dev
                _LOGGER.info("Neewer GL25B dongle connected at %s", matches[0]["path"])
                return True
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Neewer GL25B dongle not available: %s", err)
                self._dev = None
                return False

    def disconnect(self) -> None:
        """Close the HID device."""
        with self._lock:
            if self._dev is None:
                return
            try:
                self._dev.close()
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Failed to close Neewer GL25B HID device", exc_info=True)
            finally:
                self._dev = None

    def is_connected(self) -> bool:
        """Return True if the device is currently open."""
        return self._dev is not None

    def check_connection(self) -> bool:
        """Verify the dongle is still plugged in, reconnecting if needed.

        Drops a stale handle when the dongle has disappeared from the USB bus,
        and opens a new one when it is present but not yet open.
        """
        if hid is None:
            return False

        with self._lock:
            try:
                present = bool(hid.enumerate(VID, PID))
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("hid.enumerate() failed: %s", err)
                present = False

            if not present:
                self.disconnect()
                return False

            return self.connect()

    def send_command(self, command: bytes) -> None:
        """Send a command body to the dongle as one 64-byte output report."""
        if hid is None:
            raise NeewerGL25BError("hidapi is not installed")

        packet = HEADER + command
        if len(packet) > PACKET_LENGTH:
            raise NeewerGL25BError(
                f"Command is too long: {len(packet)} bytes, expected at most {PACKET_LENGTH}"
            )

        packet = packet.ljust(PACKET_LENGTH, b"\x00")

        with self._lock:
            # A handle can go stale without us noticing (e.g. the dongle was
            # unplugged and re-plugged), so on failure reopen and retry once.
            had_handle = self._dev is not None
            try:
                self._write(packet)
            except NeewerGL25BError:
                if not had_handle:
                    raise
                _LOGGER.debug("Write failed on existing handle; reconnecting")
                self._write(packet)

            time.sleep(WRITE_DELAY_SECONDS)

    def _write(self, packet: bytes) -> None:
        """Write one packet, dropping the handle on any failure."""
        if self._dev is None and not self.connect():
            raise NeewerGL25BError("Neewer GL25B dongle is not available")

        try:
            written = self._dev.write(packet)  # type: ignore[union-attr]
        except Exception as err:  # noqa: BLE001 - hidapi can raise backend-specific errors.
            self.disconnect()
            raise NeewerGL25BError(
                f"Failed to write to Neewer GL25B dongle: {err}"
            ) from err

        _LOGGER.debug("Wrote %s bytes to Neewer GL25B: %s", written, packet[:13].hex())

        # hidapi signals most failures (including an unplugged device) by
        # returning -1 rather than raising.
        if written is not None and written < 0:
            self.disconnect()
            raise NeewerGL25BError("hidapi reported a failed write")

    def set_brightness(self, percent: int) -> None:
        """Set GL25B brightness in the 0-100 percent range."""
        brightness = max(MIN_BRIGHTNESS_PERCENT, min(MAX_BRIGHTNESS_PERCENT, percent))
        command = BRIGHTNESS_COMMAND + bytes([brightness]) + bytes.fromhex("8c")
        self.send_command(command)

    def set_kelvin(self, kelvin: int) -> None:
        """Set GL25B color temperature in Kelvin."""
        clamped_kelvin = max(MIN_KELVIN, min(MAX_KELVIN, kelvin))
        command = KELVIN_COMMAND + bytes([clamped_kelvin // 100]) + bytes.fromhex("8c")
        self.send_command(command)

    def toggle(self) -> None:
        """Send the raw hardware toggle command."""
        self.send_command(TOGGLE_COMMAND)
