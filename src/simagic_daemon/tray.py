"""
Windows System Tray Application for Simagic Wheel Daemon
Runs the automation daemon in the Windows taskbar notification area (tray).
Key Features:
- Custom high-tech GT racing steering wheel icon with glowing rev lights.
- Right-click directly stops and exits the daemon cleanly.
- Left-click displays a native Windows status notification.
- Tooltip dynamically shows the active vehicle and SimPro preset.
"""

import os
import sys
import threading
import time
import subprocess
import logging
from typing import Optional

from PIL import Image
import pystray
from pystray import MenuItem as item, Menu

# Import win32 backend from pystray for precise click interception on Windows
try:
    from pystray import _win32
except ImportError:
    _win32 = None

from .daemon import SimagicWheelDaemon
from .notifications import send_windows_notification
from .process_utils import launch_simpro, is_simpro_running

logger = logging.getLogger("simagic_daemon.tray")


def get_icon_image() -> Image.Image:
    """Loads the high-resolution generated icon from assets or falls back gracefully."""
    assets_icon = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "icon.png")
    if os.path.exists(assets_icon):
        try:
            return Image.open(assets_icon)
        except Exception as e:
            logger.debug(f"Failed loading icon.png: {e}")

    # Fallback to generated icon in memory
    from PIL import ImageDraw
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, 60, 60), outline=(24, 24, 27), width=8)
    draw.ellipse((6, 6, 58, 58), outline=(220, 38, 38), width=4)
    draw.ellipse((22, 22, 42, 42), fill=(24, 24, 27), outline=(245, 158, 11), width=2)
    draw.line((10, 32, 22, 32), fill=(212, 212, 216), width=3)
    draw.line((42, 32, 54, 32), fill=(212, 212, 216), width=3)
    draw.line((32, 42, 32, 54), fill=(212, 212, 216), width=3)
    return img


class SimagicTrayApp:
    """Windows System Tray Controller for SimagicWheelDaemon."""

    def __init__(self, poll_interval: float = 1.0, revert_on_exit: bool = False):
        self.daemon = SimagicWheelDaemon(
            poll_interval=poll_interval,
            revert_on_exit=revert_on_exit,
            enable_notifications=True
        )
        self.daemon_thread: Optional[threading.Thread] = None
        self.icon: Optional[pystray.Icon] = None
        self._is_stopping = False

    def show_status_toast(self):
        """Displays current live status on left click."""
        status = self.daemon.get_status()
        car = status.get("vehicle", "None (Idle)")
        preset = status.get("preset_name", "Default")
        simpro = "Connected" if status.get("simpro_online") else "Offline"
        
        msg = f"Car: {car}\nProfile: [{preset}] | SimPro: {simpro}\n(Right-click icon to stop)"
        send_windows_notification("🏎️ Simagic Wheel Daemon Status", msg, force=True)

    def stop(self):
        """Cleanly stops the background daemon and exits the tray icon."""
        if self._is_stopping:
            return
        self._is_stopping = True
        logger.info("Stopping Simagic Wheel Daemon via right-click...")

        # Alert user of clean shutdown
        send_windows_notification(
            "Simagic Wheel Daemon",
            "Daemon stopped cleanly via right-click.",
            force=True
        )

        self.daemon.stop()
        if self.icon:
            self.icon.stop()

    def start(self):
        """Starts the background daemon thread and enters the system tray event loop."""
        # 1. Start daemon in background worker thread
        self.daemon_thread = threading.Thread(target=self.daemon.start, daemon=True)
        self.daemon_thread.start()

        # 2. Build system tray icon
        icon_img = get_icon_image()
        self.icon = pystray.Icon(
            name="simagic_wheel_daemon",
            icon=icon_img,
            title="Simagic Wheel Daemon (Right-click to stop)",
            menu=Menu(
                item("Stop Daemon (Right-Click)", lambda icon, item: self.stop(), default=True)
            )
        )

        # 3. Intercept Windows mouse events: Right-click immediately stops the daemon!
        self._setup_click_handlers()

        # 4. Start periodic tooltip updater
        updater_thread = threading.Thread(target=self._update_tray_tooltip_loop, daemon=True)
        updater_thread.start()

        # Welcome notification
        send_windows_notification(
            "Simagic Wheel Daemon Active",
            "Monitoring LMU sessions over CAN-FD.\nRight-click tray icon anytime to stop.",
            force=True
        )

        logger.info("System Tray Application started. Right-click icon to stop.")
        self.icon.run()

    def _setup_click_handlers(self):
        """Hooks Windows tray notification messages so right-click stops the app."""
        if not _win32 or not isinstance(self.icon, _win32.Icon):
            return

        original_notify = self.icon._on_notify

        def custom_on_notify(wparam, lparam):
            # WM_RBUTTONUP = 0x0205 (Right mouse button released)
            if lparam == _win32.win32.WM_RBUTTONUP:
                logger.info("Right-click received on tray icon. Stopping daemon...")
                self.stop()
                return

            # WM_LBUTTONUP = 0x0202 (Left mouse button released)
            elif lparam == _win32.win32.WM_LBUTTONUP:
                self.show_status_toast()
                return

            original_notify(wparam, lparam)

        self.icon._on_notify = custom_on_notify

    def _update_tray_tooltip_loop(self):
        """Periodically refreshes the tray tooltip based on daemon status."""
        while not self._is_stopping:
            try:
                if self.icon:
                    status = self.daemon.get_status()
                    if status["lmu_online"] and status["vehicle"] != "None (Idle)":
                        title = f"Simagic: [{status['preset_name']}] {status['vehicle']} (Right-click to stop)"
                    elif status["lmu_online"]:
                        title = "Simagic: LMU Menu (Right-click to stop)"
                    elif not status["simpro_online"]:
                        title = "Simagic: SimPro Offline (Right-click to stop)"
                    else:
                        title = "Simagic: Monitoring LMU (Right-click to stop)"

                    # Windows notification area tooltip limit is 128 chars
                    self.icon.title = title[:127]
            except Exception:
                pass
            time.sleep(2.0)


def main():
    # Safe UTF-8 encoding
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    app = SimagicTrayApp()
    app.start()


if __name__ == "__main__":
    main()
