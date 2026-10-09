"""
Windows System Tray Application for Simagic Wheel Daemon
Runs the automation daemon in the Windows taskbar notification area (tray).
Provides real-time profile indicators, hardware status, and quick actions.
"""

import os
import sys
import threading
import time
import subprocess
import logging
from typing import Optional

from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as item, Menu

from .daemon import SimagicWheelDaemon
from .notifications import send_windows_notification
from .process_utils import launch_simpro, is_simpro_running

logger = logging.getLogger("simagic_daemon.tray")


def get_icon_image(status: str = "connected") -> Image.Image:
    """Loads the icon from assets or creates an in-memory steering wheel icon."""
    assets_icon = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "icon.png")
    if os.path.exists(assets_icon):
        try:
            return Image.open(assets_icon)
        except Exception:
            pass

    # Fallback procedural steering wheel icon
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    rim_color = (220, 38, 38) if status == "connected" else (156, 163, 175)
    draw.ellipse((4, 4, 60, 60), outline=(24, 24, 27), width=8)
    draw.ellipse((6, 6, 58, 58), outline=rim_color, width=4)
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

    def start(self):
        """Starts the background daemon thread and enters the system tray event loop."""
        # Start daemon in background thread
        self.daemon_thread = threading.Thread(target=self.daemon.start, daemon=True)
        self.daemon_thread.start()

        # Build system tray icon and menu
        icon_img = get_icon_image("connected")
        self.icon = pystray.Icon(
            name="simagic_wheel_daemon",
            icon=icon_img,
            title="Simagic Wheel Daemon (Monitoring LMU)",
            menu=self._create_menu()
        )

        # Start periodic status updater thread
        updater_thread = threading.Thread(target=self._update_tray_tooltip_loop, daemon=True)
        updater_thread.start()

        logger.info("System Tray Application running.")
        self.icon.run()

    def _create_menu(self) -> Menu:
        """Constructs the right-click context menu."""
        def get_status_text(item_instance):
            status = self.daemon.get_status()
            if status["lmu_online"] and status["vehicle"] != "None (Idle)":
                return f"🚘 Car: {status['vehicle']}"
            elif status["lmu_online"]:
                return "🎮 LMU: In Main Menu"
            else:
                return "💤 LMU: Idle (Waiting for game)"

        def get_profile_text(item_instance):
            status = self.daemon.get_status()
            if status["preset_name"] and status["preset_name"] != "Default":
                return f"⚡ Wheel Profile: [{status['preset_name']}]"
            return "⚡ Wheel Profile: Default"

        def get_simpro_text(item_instance):
            status = self.daemon.get_status()
            if status["simpro_online"]:
                return "🟢 SimPro REST API: Online (Port 4010)"
            return "🔴 SimPro REST API: Offline"

        def toggle_revert_on_exit(icon, item_instance):
            self.daemon.revert_on_exit = not self.daemon.revert_on_exit
            send_windows_notification(
                "Simagic Wheel Daemon",
                f"Revert profile on exit: {'Enabled' if self.daemon.revert_on_exit else 'Disabled'}"
            )

        def is_revert_checked(item_instance):
            return self.daemon.revert_on_exit

        def action_test_notification(icon, item_instance):
            send_windows_notification(
                "Simagic Wheel Daemon",
                "Notifications active! CAN-FD profiles will alert on car load.",
                force=True
            )

        def action_launch_simpro(icon, item_instance):
            launch_simpro()

        def action_open_folder(icon, item_instance):
            root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            if sys.platform == "win32":
                os.startfile(root_dir)

        def action_exit(icon, item_instance):
            self._is_stopping = True
            logger.info("Exiting tray application...")
            self.daemon.stop()
            icon.stop()

        return Menu(
            item("🏎️ Simagic Wheel Daemon v0.1.0", None, enabled=False),
            item(get_status_text, None, enabled=False),
            item(get_profile_text, None, enabled=False),
            item(get_simpro_text, None, enabled=False),
            Menu.SEPARATOR,
            item("🔔 Test Windows Notification", action_test_notification),
            item("🚀 Launch SimPro Manager", action_launch_simpro),
            item("⚙️ Revert Profile on Game Exit", toggle_revert_on_exit, checked=is_revert_checked),
            item("📂 Open Project Folder", action_open_folder),
            Menu.SEPARATOR,
            item("❌ Exit Daemon", action_exit),
        )

    def _update_tray_tooltip_loop(self):
        """Periodically refreshes the tray tooltip based on daemon status."""
        while not self._is_stopping:
            try:
                if self.icon:
                    status = self.daemon.get_status()
                    if status["lmu_online"] and status["vehicle"] != "None (Idle)":
                        title = f"Simagic Daemon: [{status['preset_name']}] {status['vehicle']}"
                    elif status["lmu_online"]:
                        title = "Simagic Daemon: LMU Menu"
                    elif not status["simpro_online"]:
                        title = "Simagic Daemon: SimPro Offline"
                    else:
                        title = "Simagic Daemon: Monitoring LMU"

                    self.icon.title = title
            except Exception:
                pass
            time.sleep(2.0)


def main():
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    app = SimagicTrayApp()
    app.start()


if __name__ == "__main__":
    main()
