"""
Simagic Wheel Daemon
Main automation service linking Le Mans Ultimate to Simagic hardware.
Features:
- Resilient polling and automatic reconnection state machine.
- Process monitoring for SimPro Manager v3 and Le Mans Ultimate.
- Native Windows Toast notifications on profile switches and game events.
- CAN-FD profile switching through the Simagic Quick Release.
"""

import os
import time
import threading
import signal
import sys
import argparse
import logging
from typing import Optional, Dict, Any, Callable, Tuple

# Safe UTF-8 encoding on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from .simagic_client import SimagicClient, get_preset_name_from_db
from .lmu_reader import LMUReader
from . import vehicle_mapping
from .catalog_sync import refresh_catalog
from .vehicle_mapping import (
    resolve_vehicle_to_preset,
    resolve_preset_key,
    get_preset_label,
    DEFAULT_BASE_PRESET_UUID,
)
from .notifications import send_windows_notification
from .process_utils import is_simpro_running, is_lmu_running, launch_simpro, acquire_single_instance_lock

logger = logging.getLogger("simagic_daemon")


class SimagicWheelDaemon:
    """
    Resilient background daemon managing Simagic hardware profiles and LMU integration.
    """

    APPLY_RETRY_MAX_DELAY = 10.0  # seconds between retries of a failed profile switch
    DEFAULT_VERIFY_INTERVAL = 15.0  # seconds between checks that the active profile is still ours
    CATALOG_RETRY_INTERVAL = 60.0   # seconds before retrying a failed vehicle catalog refresh
    REST_PROBE_INTERVAL = 30.0      # while no LMU process is seen, still probe its REST API this often
    CATALOG_UNKNOWN_INTERVAL = 300.0  # min seconds between refreshes triggered by unknown cars

    def __init__(
        self,
        poll_interval: float = 1.0,
        dry_run: bool = False,
        revert_on_exit: bool = False,
        enable_notifications: bool = True,
        auto_launch_simpro: bool = False,
        base_preset_uuid: str = DEFAULT_BASE_PRESET_UUID,
        default_wheel_preset_uuid: Optional[str] = None,
        on_status_change: Optional[Callable[[Dict[str, Any]], None]] = None,
        verify_interval: float = DEFAULT_VERIFY_INTERVAL,
        catalog_sync: bool = True,
    ):
        self.poll_interval = max(0.2, poll_interval)
        self.dry_run = dry_run
        self.revert_on_exit = revert_on_exit
        self.enable_notifications = enable_notifications
        self.auto_launch_simpro = auto_launch_simpro
        self.base_preset_uuid = base_preset_uuid
        self.default_wheel_preset_uuid = (
            default_wheel_preset_uuid if default_wheel_preset_uuid is not None
            else resolve_preset_key("DEFAULT")[1]
        )
        self.on_status_change = on_status_change
        self.verify_interval = max(0.0, verify_interval)  # 0 disables the periodic check
        self.catalog_sync = catalog_sync  # refresh the vehicle catalog from LMU's REST API

        self.client = SimagicClient()
        self.lmu_reader = LMUReader()

        self.is_running = False
        self.simpro_online = False
        self.lmu_online = False
        self.current_vehicle_identifier: Optional[str] = None
        self.current_model_name: Optional[str] = None
        self.active_wheel_preset_uuid: Optional[str] = None
        self.active_wheel_preset_name: str = "Default"
        self.active_base_preset_uuid: Optional[str] = None
        self.last_switch_time: float = 0.0

        # Pending profile application for the loaded car: (wheel preset uuid, preset name, model name)
        self._target: Optional[Tuple[str, str, str]] = None
        self._apply_pending = False
        self._apply_failures = 0
        self._next_apply_time = 0.0
        self._waiting_logged = False
        self._last_verify_time = 0.0
        self._readback_unavailable_logged = False

        # Self-healing vehicle catalog (refreshed in a background thread, applied in the poll loop)
        self._current_veh_info: Optional[Dict[str, Any]] = None
        self._last_rest_probe = 0.0
        self._catalog_thread: Optional[threading.Thread] = None
        self._catalog_result: Optional[Tuple[int, Optional[str]]] = None
        self._catalog_synced_this_session = False
        self._last_catalog_attempt = 0.0

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
            "model_name": self.current_model_name,
            "preset_name": self.active_wheel_preset_name,
            "preset_uuid": self.active_wheel_preset_uuid,
            "apply_pending": self._apply_pending,
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
        logger.info(f"  • Profile check     : {f'every {self.verify_interval:.0f}s' if self.verify_interval else 'DISABLED'}")
        logger.info(f"  • Vehicle catalog   : {len(vehicle_mapping.VEHICLE_CATALOG)} IDs, auto-refresh {'ON' if self.catalog_sync else 'OFF'}")
        logger.info(f"  • Code path         : {os.path.dirname(os.path.abspath(__file__))}")
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
                # SimPro may have restarted with a different active profile: re-apply for the loaded car
                self.active_wheel_preset_uuid = None
                self.active_base_preset_uuid = None
                if self._target is not None:
                    self._apply_pending = True
                    self._next_apply_time = 0.0
            self.simpro_online = True
            return True
        else:
            if self.simpro_online:
                logger.warning("[SimPro] Lost connection to SimPro Manager REST server.")
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

        # 2. Apply a finished background catalog refresh (may re-identify the current car)
        self._apply_catalog_result()

        # 3. Check LMU status. A refused localhost connection takes ~2s on Windows, so LMU's REST
        #    API is only queried while the game process runs (plus a periodic probe, in case the
        #    executable has an unexpected name).
        game_running = is_lmu_running()
        probe = game_running or self.lmu_online or time.time() - self._last_rest_probe >= self.REST_PROBE_INTERVAL
        veh_info = None
        if probe:
            if not game_running:
                self._last_rest_probe = time.time()
            veh_info = self.lmu_reader.get_active_vehicle()

        if veh_info and veh_info.get("identifier"):
            if not self.lmu_online:
                logger.info("🎮 Le Mans Ultimate session detected!")
                self._notify("Le Mans Ultimate Online", "Game session active. Monitoring vehicle loading...")
                self.lmu_online = True

            self._maybe_sync_catalog()
            ident = veh_info.get("identifier", "").strip()
            if ident and ident != self.current_vehicle_identifier:
                self._on_vehicle_detected(ident, veh_info)

            # 3. Apply (or retry) the profiles for the loaded car
            if self._apply_pending:
                if simpro_ready:
                    self._try_apply_profiles()
                elif not self._waiting_logged:
                    logger.info("   ⏳ SimPro is not reachable yet; profiles will be applied once it connects.")
                    self._waiting_logged = True
            elif simpro_ready:
                # 4. Periodically confirm nobody (SimPro, GUI, wheel reconnect) changed the profile
                self._verify_active_profiles()

            if self.on_status_change:
                self.on_status_change(self.get_status())
            return veh_info
        else:
            # LMU running but no car selected (main menu)?
            lmu_proc = game_running or (probe and self.lmu_reader.is_rest_api_online())
            if lmu_proc and not self.lmu_online:
                logger.info("🎮 Le Mans Ultimate is open (in main menu).")
                self.lmu_online = True
            elif not lmu_proc and self.lmu_online:
                logger.info("🏁 LMU closed or session unloaded.")
                self._on_vehicle_unloaded()
                self.lmu_online = False
                self._catalog_synced_this_session = False  # LMU may be updated before next launch
            if self.lmu_online:
                self._maybe_sync_catalog()

            if self.on_status_change:
                self.on_status_change(self.get_status())
            return None

    def _on_vehicle_detected(self, vehicle_id: str, veh_info: Dict[str, Any]):
        """Triggered when a new vehicle is selected or loaded in LMU. Resolves its target profiles."""
        vehicle_class = veh_info.get("classes") or veh_info.get("class")
        manufacturer = veh_info.get("manufacturer") or None
        model_name, target_preset_uuid, preset_name = resolve_vehicle_to_preset(vehicle_id, vehicle_class, manufacturer)
        source = veh_info.get("source", "UNKNOWN")

        logger.info(
            f"🚘 [CAR LOADED] '{model_name}' (Raw: '{vehicle_id}', Class: {vehicle_class or 'n/a'}, "
            f"Make: {manufacturer or 'n/a'}, Source: {source})"
        )
        logger.info(f"   Target GT NEO Preset : '{preset_name}' [{target_preset_uuid or 'NOT CONFIGURED'}]")

        if not target_preset_uuid:
            logger.warning(
                "   ⚠️ [SKIPPED] No GT NEO preset UUID configured for this car or DEFAULT; "
                "add it to user_presets.json"
            )

        # A real vehicle ID (.veh) that the catalog does not know: LMU may have new cars/liveries
        is_vehicle_id = bool(veh_info.get("veh_file")) or source == "REST_STANDINGS"
        if is_vehicle_id and vehicle_mapping.match_vehicle(vehicle_id).source != "catalog":
            logger.info("   🔄 Vehicle ID not in the catalog; refreshing it from LMU in the background")
            self._maybe_sync_catalog(unknown_vehicle=True)

        self._current_veh_info = veh_info
        self.current_vehicle_identifier = vehicle_id
        self.current_model_name = model_name
        self._target = (target_preset_uuid, preset_name, model_name)
        self._apply_pending = True
        self._apply_failures = 0
        self._next_apply_time = 0.0
        self._waiting_logged = False

    def _maybe_sync_catalog(self, unknown_vehicle: bool = False):
        """
        Starts a background refresh of the vehicle catalog from LMU's REST API:
        once per LMU session (retried every minute until it succeeds), and again when an
        unknown vehicle ID is loaded (at most every 5 minutes).
        """
        if not self.catalog_sync or (self._catalog_thread and self._catalog_thread.is_alive()):
            return
        now = time.time()
        if unknown_vehicle:
            if now - self._last_catalog_attempt < self.CATALOG_UNKNOWN_INTERVAL:
                return
        elif self._catalog_synced_this_session or now - self._last_catalog_attempt < self.CATALOG_RETRY_INTERVAL:
            return
        self._last_catalog_attempt = now

        def worker():
            self._catalog_result = refresh_catalog()

        self._catalog_thread = threading.Thread(target=worker, name="catalog-sync", daemon=True)
        self._catalog_thread.start()

    def _apply_catalog_result(self):
        """Reloads the catalog after a refresh and re-identifies the current car if it now resolves differently."""
        result, self._catalog_result = self._catalog_result, None
        if result is None:
            return
        added, error = result
        if error:
            logger.debug(f"[Catalog] Refresh from LMU failed ({error}); will retry")
            return
        self._catalog_synced_this_session = True
        if not added:
            return
        vehicle_mapping.reload_vehicle_catalog()
        if self.current_vehicle_identifier and self._current_veh_info and self._target:
            info = self._current_veh_info
            model, uuid, _ = resolve_vehicle_to_preset(
                self.current_vehicle_identifier,
                info.get("classes") or info.get("class"),
                info.get("manufacturer") or None,
            )
            if (uuid, model) != (self._target[0], self._target[2]):
                logger.info(f"[Catalog] Current car re-identified as '{model}' after the catalog update")
                self._on_vehicle_detected(self.current_vehicle_identifier, info)

    def _try_apply_profiles(self):
        """
        Switches the wheel and base presets for the current target.
        Stays pending (retried with backoff) until both succeed, so a SimPro hiccup
        never leaves the wheel on the previous car's rev lights.
        """
        if self._target is None or time.time() < self._next_apply_time:
            return
        target_preset_uuid, preset_name, model_name = self._target
        retrying = self._apply_failures > 0

        # 1. Switch GT NEO Steering Wheel Preset
        wheel_ok = True
        wheel_switched = False
        if target_preset_uuid and target_preset_uuid != self.active_wheel_preset_uuid:
            if self.dry_run:
                logger.info(f"   [DRY RUN] Would switch GT NEO profile to '{preset_name}'")
                ok = True
            else:
                ok = (self.client.select_wheel_preset(target_preset_uuid)
                      and self._confirm_selected("GT NEO", self.client.get_selected_wheel_preset, target_preset_uuid))
            if ok:
                if not self.dry_run:
                    logger.info(f"   ✅ [SWITCHED] GT NEO profile set to '{preset_name}' via CAN-FD")
                self.active_wheel_preset_uuid = target_preset_uuid
                self.active_wheel_preset_name = preset_name
                wheel_switched = True
            else:
                wheel_ok = False
                if not retrying:
                    logger.error(f"   ❌ [FAILED] Could not switch GT NEO profile to '{preset_name}', will retry")

        # 2. Switch Wheelbase Preset (FFB)
        base_ok = True
        if self.base_preset_uuid and self.active_base_preset_uuid != self.base_preset_uuid:
            if self.dry_run:
                logger.info(f"   [DRY RUN] Would set Base preset to {self.base_preset_uuid}")
                ok = True
            else:
                ok = (self.client.select_base_preset(self.base_preset_uuid)
                      and self._confirm_selected("Base", self.client.get_selected_base_preset, self.base_preset_uuid))
            if ok:
                if not self.dry_run:
                    base_name = get_preset_name_from_db(self.base_preset_uuid) or self.base_preset_uuid
                    logger.info(f"   ✅ [SWITCHED] Base profile set to '{base_name}'")
                self.active_base_preset_uuid = self.base_preset_uuid
            else:
                base_ok = False
                if not retrying:
                    logger.error("   ❌ [FAILED] Could not switch Base profile, will retry")

        # 3. Send Windows Toast Notification on switch
        if wheel_switched:
            self._notify(
                "Profile Switched",
                f"[{preset_name}]\n{model_name} (CAN-FD Active)",
                force=True
            )
            self.last_switch_time = time.time()

        if wheel_ok and base_ok:
            self._last_verify_time = time.time()
            if retrying:
                logger.info(f"   ✅ Profiles applied after {self._apply_failures} failed attempt(s).")
            self._apply_pending = False
            self._apply_failures = 0
        else:
            self._apply_failures += 1
            delay = min(self.APPLY_RETRY_MAX_DELAY, 2.0 * self._apply_failures)
            self._next_apply_time = time.time() + delay
            logger.debug(f"   Profile apply attempt {self._apply_failures} failed; retrying in {delay:.0f}s")

    def _confirm_selected(self, device: str, getter: Callable[[], Optional[str]], expected: str) -> bool:
        """
        Reads the active preset back from SimPro after a switch.
        False only on a definite mismatch; if SimPro cannot report it, the switch is trusted.
        """
        actual = getter()
        if actual is None:
            if not self._readback_unavailable_logged:
                logger.debug(f"   [VERIFY] SimPro did not report the active {device} preset; trusting the switch response")
                self._readback_unavailable_logged = True
            return True
        if str(actual) != str(expected):
            logger.warning(f"   ⚠️ [VERIFY] {device} switch accepted but SimPro reports preset {actual} still active")
            return False
        return True

    def _verify_active_profiles(self):
        """Re-applies the profiles if the active preset no longer matches the loaded car."""
        if self.dry_run or not self.verify_interval or self._target is None:
            return
        now = time.time()
        if now - self._last_verify_time < self.verify_interval:
            return
        self._last_verify_time = now

        target_preset_uuid = self._target[0]
        drifted = False
        if target_preset_uuid:
            actual = self.client.get_selected_wheel_preset()
            if actual is not None and actual != target_preset_uuid:
                logger.warning(f"[VERIFY] GT NEO profile changed outside the daemon (now {actual}); re-applying '{self._target[1]}'")
                self.active_wheel_preset_uuid = None
                drifted = True
        if self.base_preset_uuid:
            actual = self.client.get_selected_base_preset()
            if actual is not None and actual != self.base_preset_uuid:
                logger.warning(f"[VERIFY] Base profile changed outside the daemon (now {actual}); re-applying")
                self.active_base_preset_uuid = None
                drifted = True

        if drifted:
            self._apply_pending = True
            self._apply_failures = 0
            self._next_apply_time = 0.0
            self._try_apply_profiles()

    def _on_vehicle_unloaded(self):
        """Triggered when exiting the track or closing LMU."""
        self._target = None
        self._apply_pending = False
        self._apply_failures = 0

        if self.revert_on_exit and self.default_wheel_preset_uuid:
            if self.active_wheel_preset_uuid != self.default_wheel_preset_uuid:
                logger.info("   Reverting GT NEO profile to default profile...")
                ok = self.dry_run or self.client.select_wheel_preset(self.default_wheel_preset_uuid)
                if ok:
                    self.active_wheel_preset_uuid = self.default_wheel_preset_uuid
                    self.active_wheel_preset_name = get_preset_label("DEFAULT")
                    self._notify(
                        "LMU Session Ended",
                        "Reverted GT NEO to Default Profile.",
                        force=True
                    )
                else:
                    logger.error("   ❌ [FAILED] Could not revert GT NEO profile to default")

        self.current_vehicle_identifier = None
        self.current_model_name = None
        self._current_veh_info = None

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
        "--verify-interval",
        type=float,
        default=SimagicWheelDaemon.DEFAULT_VERIFY_INTERVAL,
        help="Seconds between checks that the active profile still matches the car; 0 disables "
             f"(default: {SimagicWheelDaemon.DEFAULT_VERIFY_INTERVAL:.0f})"
    )
    parser.add_argument(
        "--no-catalog-sync",
        action="store_true",
        help="Do not refresh the vehicle catalog from LMU's REST API automatically"
    )
    parser.add_argument(
        "--capture",
        nargs="?",
        const="",
        metavar="DIR",
        help="Record raw LMU data (REST + shared memory) for offline verification instead of running "
             "the daemon. Default folder: local/captures/<timestamp>"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Perform a single poll cycle and exit"
    )
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Enable full debug logging to console and rotating file"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Custom path for the rotating log file (default: logs/daemon.log)"
    )

    args = parser.parse_args()

    # Configure rotating file + console logging
    from .logger import setup_logging
    log_level = logging.DEBUG if (args.verbose or args.debug) else logging.INFO
    setup_logging(log_level=log_level, log_file=args.log_file)

    if args.capture is not None:
        from .capture import run_capture
        run_capture(out_dir=args.capture or None, interval=args.poll_interval)
        return

    daemon = SimagicWheelDaemon(
        poll_interval=args.poll_interval,
        dry_run=args.dry_run,
        revert_on_exit=args.revert_on_exit,
        enable_notifications=not args.no_notify,
        auto_launch_simpro=args.auto_launch_simpro,
        verify_interval=args.verify_interval,
        catalog_sync=not args.no_catalog_sync,
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

    if not acquire_single_instance_lock():
        logger.error("Another Simagic Wheel Daemon (console or tray) is already running. Exiting.")
        sys.exit(1)

    daemon.start()


if __name__ == "__main__":
    main()
