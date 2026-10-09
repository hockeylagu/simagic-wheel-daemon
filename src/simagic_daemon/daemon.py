"""
Simagic Wheel Daemon
Main automation service linking Le Mans Ultimate to Simagic hardware.
Features:
- Resilient polling and automatic reconnection state machine.
- Process monitoring for SimPro Manager v3 and Le Mans Ultimate.
- Native Windows Toast notifications on profile switches and game events.
- CAN-FD profile switching through the Simagic Quick Release.
"""

import time
import signal
import sys
import argparse
import logging
from typing import Optional, Dict, Any, Callable

# Safe UTF-8 encoding on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from .simagic_client import SimagicClient
from .lmu_reader import LMUReader
from .vehicle_mapping import resolve_vehicle_to_preset, DEFAULT_BASE_PRESET_UUID, PRESET_MAP_GT_NEO
from .notifications import send_windows_notification
from .process_utils import is_simpro_running, is_lmu_running, launch_simpro

logger = logging.getLogger("simagic_daemon")


class SimagicWheelDaemon:
    """
    Resilient background daemon managing Simagic hardware profiles and LMU integration.
    """

    def __init__(
        self,
        poll_interval: float = 1.0,
        dry_run: bool = False,
        revert_on_exit: bool = False,
        enable_notifications: bool = True,
        auto_launch_simpro: bool = False,
        base_preset_uuid: str = DEFAULT_BASE_PRESET_UUID,
        default_wheel_preset_uuid: str = PRESET_MAP_GT_NEO["DEFAULT"],
        on_status_change: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        self.poll_interval = max(0.2, poll_interval)
        self.dry_run = dry_run
        self.revert_on_exit = revert_on_exit
        self.enable_notifications = enable_notifications
        self.auto_launch_simpro = auto_launch_simpro
        self.base_preset_uuid = base_preset_uuid
        self.default_wheel_preset_uuid = default_wheel_preset_uuid
        self.on_status_change = on_status_change

        self.client = SimagicClient()
        self.lmu_reader = LMUReader()

        self.is_running = False
        self.simpro_online = False
        self.lmu_online = False
        self.current_vehicle_identifier: Optional[str] = None
        self.active_wheel_preset_uuid: Optional[str] = None
        self.active_wheel_preset_name: str = "Default"
        self.active_base_preset_uuid: Optional[str] = None
        self.last_switch_time: float = 0.0

        self._notified_simpro_offline = False

    def handle_signal(self, signum, frame):
        """Graceful shutdown handler for SIGINT/SIGTERM."""
        signame = signal.Signals(signum).name if hasattr(signal, 'Signals') else str(signum)
        logger.info(f"Received shutdown signal ({signame}). Stopping daemon...")
        self.stop()

    def get_status(self) -> Dict[str, Any]:
        """Returns the current operational status for CLI or GUI / System Tray."""
        return {
            "is_running": self.is_running,
            "simpro_online": self.simpro_online,
            "lmu_online": self.lmu_online,
            "vehicle": self.current_vehicle_identifier or "None (Idle)",
            "preset_name": self.active_wheel_preset_name,
            "preset_uuid": self.active_wheel_preset_uuid,
            "base_preset_uuid": self.active_base_preset_uuid,
            "dry_run": self.dry_run,
            "revert_on_exit": self.revert_on_exit,
            "notifications": self.enable_notifications,
        }

    def _notify(self, title: str, message: str, force: bool = False):
        """Sends a native Windows Toast notification if notifications are enabled."""
        if self.enable_notifications:
            send_windows_notification(title, message, force=force)

    def start(self):
        """Starts the daemon polling loop."""
        self.is_running = True

        try:
            signal.signal(signal.SIGINT, self.handle_signal)
            signal.signal(signal.SIGTERM, self.handle_signal)
        except Exception:
            pass  # Some environments or secondary threads do not support signal handling

        logger.info("=" * 65)
        logger.info("🏎️  SIMAGIC WHEEL DAEMON STARTED")
        logger.info("=" * 65)
        logger.info(f"  • Polling Interval : {self.poll_interval:.1f}s")
        logger.info(f"  • Mode              : {'[DRY RUN]' if self.dry_run else '[LIVE ACTIVE]'}")
        logger.info(f"  • Notifications     : {'ENABLED' if self.enable_notifications else 'DISABLED'}")
        logger.info(f"  • Revert on exit    : {self.revert_on_exit}")
        logger.info(f"  • Auto Launch SimPro: {self.auto_launch_simpro}")
        logger.info("-" * 65)

        # Check SimPro connectivity
        self._check_and_recover_simpro()

        logger.info("Watching for Le Mans Ultimate (LMU) sessions... (Press Ctrl+C to stop)")

        while self.is_running:
            try:
                self.poll_once()
            except Exception as e:
                logger.error(f"Error during poll cycle: {e}", exc_info=logger.isEnabledFor(logging.DEBUG))

            if self.is_running:
                # Adaptive sleep: slightly longer when LMU is offline to save CPU cycles
                sleep_duration = self.poll_interval if self.lmu_online else max(1.5, self.poll_interval)
                time.sleep(sleep_duration)

        self._cleanup()
        logger.info("Simagic Wheel Daemon stopped cleanly.")

    def stop(self):
        """Stops the daemon."""
        self.is_running = False

    def _check_and_recover_simpro(self) -> bool:
        """Verifies if SimPro Manager REST API is reachable; attempts auto-launch if configured."""
        api_ok = self.client.is_api_running()

        if api_ok:
            if not self.simpro_online:
                logger.info("[SimPro] Connected to SimPro Manager v3 REST server on port 4010.")
                if self._notified_simpro_offline:
                    self._notify("SimPro Connected", "Hardware connection established on port 4010.")
                    self._notified_simpro_offline = False
            self.simpro_online = True
            return True
        else:
            self.simpro_online = False
            # Check process status
            running_process = is_simpro_running()
            if not running_process:
                logger.warning("[SimPro] simpro3.exe process is not currently running.")
                if self.auto_launch_simpro:
                    logger.info("[SimPro] Auto-launching SimPro Manager...")
                    launch_simpro()
                elif not self._notified_simpro_offline:
                    self._notify("SimPro Offline", "SimPro Manager is not running. Please start SimPro.")
                    self._notified_simpro_offline = True
            else:
                logger.warning("[SimPro] simpro3.exe is running, but port 4010 is not responding yet (initializing).")

            return False

    def poll_once(self) -> Optional[Dict[str, Any]]:
        """
        Executes a single polling iteration.
        Returns vehicle info dict if a vehicle is detected, else None.
        """
        # 1. Ensure SimPro is online
        simpro_ready = self._check_and_recover_simpro()

        # 2. Check LMU status
        veh_info = self.lmu_reader.get_active_vehicle()

        if veh_info and veh_info.get("identifier"):
            if not self.lmu_online:
                logger.info("🎮 Le Mans Ultimate session detected!")
                self._notify("Le Mans Ultimate Online", "Game session active. Monitoring vehicle loading...")
                self.lmu_online = True

            ident = veh_info.get("identifier", "").strip()
            if ident and ident != self.current_vehicle_identifier:
                self._on_vehicle_detected(ident, veh_info)
            elif not simpro_ready:
                # If SimPro had temporarily dropped out and just recovered, re-apply
                pass

            if self.on_status_change:
                self.on_status_change(self.get_status())
            return veh_info
        else:
            # Check if LMU process is running in menu
            lmu_proc = is_lmu_running() or self.lmu_reader.is_rest_api_online()
            if lmu_proc and not self.lmu_online:
                logger.info("🎮 Le Mans Ultimate is open (in main menu).")
                self.lmu_online = True
            elif not lmu_proc and self.lmu_online:
                logger.info("🏁 LMU closed or session unloaded.")
                self._on_vehicle_unloaded()
                self.lmu_online = False

            if self.on_status_change:
                self.on_status_change(self.get_status())
            return None

    def _on_vehicle_detected(self, vehicle_id: str, veh_info: Dict[str, Any]):
        """Triggered when a new vehicle is selected or loaded in LMU."""
        model_name, target_preset_uuid, preset_name = resolve_vehicle_to_preset(vehicle_id)
        source = veh_info.get("source", "UNKNOWN")

        logger.info(f"🚘 [CAR LOADED] '{model_name}' (Raw: '{vehicle_id}', Source: {source})")
        logger.info(f"   Target GT NEO Preset : '{preset_name}' [{target_preset_uuid}]")

        # 1. Switch GT NEO Steering Wheel Preset
        wheel_switch_ok = False
        if target_preset_uuid != self.active_wheel_preset_uuid:
            if self.dry_run:
                logger.info(f"   [DRY RUN] Would switch GT NEO profile to '{preset_name}'")
                self.active_wheel_preset_uuid = target_preset_uuid
                self.active_wheel_preset_name = preset_name
                wheel_switch_ok = True
            else:
                ok = self.client.select_wheel_preset(target_preset_uuid)
                if ok:
                    logger.info(f"   ✅ [SWITCHED] GT NEO profile set to '{preset_name}' via CAN-FD")
                    self.active_wheel_preset_uuid = target_preset_uuid
                    self.active_wheel_preset_name = preset_name
                    wheel_switch_ok = True
                else:
                    logger.error(f"   ❌ [FAILED] Could not switch GT NEO profile to '{preset_name}'")

        # 2. Switch Wheelbase Preset (FFB)
        if self.base_preset_uuid and self.active_base_preset_uuid != self.base_preset_uuid:
            if self.dry_run:
                logger.info(f"   [DRY RUN] Would set Base preset to {self.base_preset_uuid}")
                self.active_base_preset_uuid = self.base_preset_uuid
            else:
                ok = self.client.select_base_preset(self.base_preset_uuid)
                if ok:
                    logger.info(f"   ✅ [SWITCHED] Base profile set to 'My LeMans Ultimate'")
                    self.active_base_preset_uuid = self.base_preset_uuid
                else:
                    logger.error(f"   ❌ [FAILED] Could not switch Base profile")

        # 3. Send Windows Toast Notification on switch
        if wheel_switch_ok:
            self._notify(
                "Profile Switched",
                f"[{preset_name}]\n{model_name} (CAN-FD Active)",
                force=True
            )

        self.current_vehicle_identifier = vehicle_id
        self.last_switch_time = time.time()

    def _on_vehicle_unloaded(self):
        """Triggered when exiting the track or closing LMU."""
        if self.revert_on_exit and self.default_wheel_preset_uuid:
            if self.active_wheel_preset_uuid != self.default_wheel_preset_uuid:
                logger.info("   Reverting GT NEO profile to default profile...")
                if not self.dry_run:
                    self.client.select_wheel_preset(self.default_wheel_preset_uuid)
                self.active_wheel_preset_uuid = self.default_wheel_preset_uuid
                self.active_wheel_preset_name = "My GT Neo Default"
                self._notify(
                    "LMU Session Ended",
                    "Reverted GT NEO to Default Profile.",
                    force=True
                )

        self.current_vehicle_identifier = None

    def _cleanup(self):
        """Cleans up resources."""
        self.lmu_reader.close_shared_memory()


def main():
    parser = argparse.ArgumentParser(
        prog="simagic-daemon",
        description="Simagic Wheel Daemon - Automatic LMU Profile Switching & CAN-FD Hardware Management"
    )
    parser.add_argument(
        "--poll-interval", "-i",
        type=float,
        default=1.0,
        help="Polling interval in seconds (default: 1.0)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate profile switches without sending commands to SimPro API"
    )
    parser.add_argument(
        "--revert-on-exit",
        action="store_true",
        help="Revert wheel to default preset when LMU exits"
    )
    parser.add_argument(
        "--no-notify",
        action="store_true",
        help="Disable native Windows toast notifications"
    )
    parser.add_argument(
        "--auto-launch-simpro",
        action="store_true",
        help="Automatically launch SimPro Manager if not currently running"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Perform a single poll cycle and exit"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose / debug logging"
    )

    args = parser.parse_args()

    # Setup logging format
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    daemon = SimagicWheelDaemon(
        poll_interval=args.poll_interval,
        dry_run=args.dry_run,
        revert_on_exit=args.revert_on_exit,
        enable_notifications=not args.no_notify,
        auto_launch_simpro=args.auto_launch_simpro
    )

    if args.once:
        logger.info("Simagic Wheel Daemon single poll cycle:")
        daemon._check_and_recover_simpro()
        res = daemon.poll_once()
        if res:
            logger.info(f"Result: {res}")
        else:
            logger.info("Result: LMU is not currently active.")
        daemon._cleanup()
        return

    daemon.start()


if __name__ == "__main__":
    main()
