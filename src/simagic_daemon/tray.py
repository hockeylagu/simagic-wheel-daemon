"""
Windows System Tray Application for Simagic Wheel Daemon
Runs the automation daemon in the Windows taskbar notification area (tray).
Key Features:
- Custom high-tech GT racing steering wheel icon with glowing rev lights.
- Right-click menu displays live real-time status:
    * 🎮 Game Status (LMU On Track / In Menu / Offline)
    * 🏎️ Current Car (e.g. Ferrari 296 GT3)
    * ⚡ Active Profile (e.g. GT3 296)
    * 🟢 SimPro Status (Connected / Offline)
    * 🛑 Stop Daemon (1-click exit)
- Left-click pops up a native Windows Toast notification with status summary.
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
from .process_utils import launch_simpro, is_simpro_running, is_lmu_running, acquire_single_instance_lock
from .logger import setup_logging, open_log_file

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

    # -------------------------------------------------------------------------
    # Dynamic Status Providers for Right-Click Context Menu
    # -------------------------------------------------------------------------
    def _get_game_status_text(self, item_instance=None) -> str:
        """Returns live game state (LMU on-track, menu, or offline)."""
        status = self.daemon.get_status()
        veh = status.get("vehicle", "None (Idle)")
        if status.get("lmu_online") and veh and veh != "None (Idle)":
            return "🎮 Game: LMU (On Track)"
        elif status.get("lmu_online"):
            return "🎮 Game: LMU (In Menu)"
        elif is_lmu_running():
            return "🎮 Game: LMU (Starting...)"
        else:
            return "🎮 Game: Not running"

    def _get_car_status_text(self, item_instance=None) -> str:
        """Returns the currently detected vehicle name."""
        status = self.daemon.get_status()
        veh = status.get("vehicle", "None (Idle)")
        if veh and veh != "None (Idle)":
            return f"🏎️ Car: {status.get('model_name') or veh}"
        return "🏎️ Car: None (Idle)"

    def _get_profile_status_text(self, item_instance=None) -> str:
        """Returns the active SimPro profile name."""
        status = self.daemon.get_status()
        preset = status.get("preset_name", "Default")
        return f"⚡ Wheel Profile: [{preset}]"

    def _get_simpro_status_text(self, item_instance=None) -> str:
        """Returns SimPro REST API status on port 4010."""
        status = self.daemon.get_status()
        if status.get("simpro_online"):
            return "🟢 SimPro: Connected (Port 4010)"
        elif is_simpro_running():
            return "🟡 SimPro: Running (Connecting...)"
        else:
            return "🔴 SimPro: Not running"

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------
    def show_status_toast(self):
        """Displays current live status on left click."""
        game_str = self._get_game_status_text()
        car_str = self._get_car_status_text()
        prof_str = self._get_profile_status_text()
        sim_str = self._get_simpro_status_text()
        
        body = f"{game_str}\n{car_str}\n{prof_str}\n{sim_str}"
        send_windows_notification("🏎️ Simagic Wheel Daemon Status", body, force=True)

    def stop(self):
        """Cleanly stops the background daemon and exits the tray icon."""
        if self._is_stopping:
            return
        self._is_stopping = True
        logger.info("Stopping Simagic Wheel Daemon...")

        # Alert user of clean shutdown
        send_windows_notification(
            "Simagic Wheel Daemon",
            "Daemon stopped cleanly.",
            force=True
        )

        self.daemon.stop()
        if self.icon:
            self.icon.stop()

    def _action_launch_simpro(self):
        """One-click launcher for SimPro Manager."""
        launch_simpro()

    def _action_test_notification(self):
        """Dispatches test Windows notification."""
        send_windows_notification(
            "Simagic Wheel Daemon",
            "Windows notifications are working!\nProfile alerts will pop up when cars are loaded over CAN-FD.",
            force=True
        )

    def _action_view_log(self):
        """Opens log file in Notepad."""
        open_log_file()

    def _toggle_revert_on_exit(self, icon, item_instance):
        """Toggles the auto-revert profile setting."""
        self.daemon.revert_on_exit = not self.daemon.revert_on_exit
        send_windows_notification(
            "Simagic Wheel Daemon",
            f"Revert profile on game exit: {'Enabled' if self.daemon.revert_on_exit else 'Disabled'}"
        )

    def _is_revert_checked(self, item_instance) -> bool:
        return self.daemon.revert_on_exit

    # -------------------------------------------------------------------------
    # Menu Construction & Lifecycle
    # -------------------------------------------------------------------------
    def _create_menu(self) -> Menu:
        """Constructs the right-click context menu with live status and actions."""
        return Menu(
            # Live Status indicators (read-only headers)
            item("🏎️ Simagic Wheel Daemon", None, enabled=False),
            item(self._get_game_status_text, None, enabled=False),
            item(self._get_car_status_text, None, enabled=False),
            item(self._get_profile_status_text, None, enabled=False),
            item(self._get_simpro_status_text, None, enabled=False),
            Menu.SEPARATOR,
            # Direct Actions
            item("🛑 Stop Daemon", lambda icon, item: self.stop()),
            item("🚀 Launch SimPro Manager", lambda icon, item: self._action_launch_simpro()),
            item("🔔 Test Notification", lambda icon, item: self._action_test_notification()),
            item("📋 View Debug Log", lambda icon, item: self._action_view_log()),
            item("⚙️ Revert Profile on Exit", self._toggle_revert_on_exit, checked=self._is_revert_checked),
        )

    def start(self):
        """Starts the background daemon thread and enters the system tray event loop."""
        # 1. Start daemon in background worker thread
        self.daemon_thread = threading.Thread(target=self.daemon.start, daemon=True)
        self.daemon_thread.start()

        # 2. Build system tray icon with dynamic context menu
        icon_img = get_icon_image()
        self.icon = pystray.Icon(
            name="simagic_wheel_daemon",
            icon=icon_img,
            title="Simagic Wheel Daemon (Right-click for status & stop)",
            menu=self._create_menu()
        )

        # 3. Intercept Windows mouse events: Left-click displays status toast!
        self._setup_click_handlers()

        # 4. Start periodic tooltip updater
        updater_thread = threading.Thread(target=self._update_tray_tooltip_loop, daemon=True)
        updater_thread.start()

        # Welcome notification
        send_windows_notification(
            "Simagic Wheel Daemon Active",
            "Monitoring LMU sessions over CAN-FD.\nRight-click tray icon to view live status or stop.",
            force=True
        )

        logger.info("System Tray Application started. Right-click icon for live status & controls.")
        self.icon.run()

    def _setup_click_handlers(self):
        """Hooks Windows tray notification messages so left-click shows live status toast."""
        if not _win32 or not isinstance(self.icon, _win32.Icon):
            return

        original_notify = self.icon._on_notify

        def custom_on_notify(wparam, lparam):
            # WM_LBUTTONUP = 0x0202 (Left mouse button released)
            if lparam == _win32.win32.WM_LBUTTONUP:
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
                    veh = status.get("vehicle", "None (Idle)")
                    if status.get("lmu_online") and veh and veh != "None (Idle)":
                        model_name = status.get("model_name") or veh
                        title = f"Simagic: [{status['preset_name']}] {model_name}"
                    elif status.get("lmu_online"):
                        title = "Simagic: LMU Menu"
                    elif not status.get("simpro_online"):
                        title = "Simagic: SimPro Offline"
                    else:
                        title = "Simagic: Monitoring LMU"

                    # Windows notification area tooltip limit is 128 chars
                    self.icon.title = title[:127]
            except Exception:
                pass
            time.sleep(2.0)


def main():
    # Safe UTF-8 encoding
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    # Setup rotating file debug logging (logs/daemon.log)
    setup_logging(log_level=logging.DEBUG)

    if not acquire_single_instance_lock():
        logger.error("Another Simagic Wheel Daemon (console or tray) is already running. Exiting.")
        send_windows_notification(
            "Simagic Wheel Daemon",
            "Already running. Check the system tray.",
            force=True
        )
        time.sleep(1.0)  # let the toast worker thread start before the process exits
        sys.exit(1)

    app = SimagicTrayApp()
    app.start()


if __name__ == "__main__":
    main()
