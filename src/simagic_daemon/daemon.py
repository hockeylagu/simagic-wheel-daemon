"""
Simagic Wheel Daemon
Main automation service linking Le Mans Ultimate to Simagic hardware.
Monitors game session/car loading and automatically switches Wheelbase and
GT NEO presets via SimPro Manager's local REST API over CAN-FD.
"""

import time
import signal
import sys
import argparse
import logging
from typing import Optional, Dict, Any

from .simagic_client import SimagicClient
from .lmu_reader import LMUReader
from .vehicle_mapping import resolve_vehicle_to_preset, DEFAULT_BASE_PRESET_UUID, PRESET_MAP_GT_NEO

logger = logging.getLogger("simagic_daemon")


class SimagicWheelDaemon:
    """
    Background daemon for Simagic hardware automation with Le Mans Ultimate.
    """

    def __init__(
        self,
        poll_interval: float = 1.0,
        dry_run: bool = False,
        revert_on_exit: bool = False,
        base_preset_uuid: str = DEFAULT_BASE_PRESET_UUID,
        default_wheel_preset_uuid: str = PRESET_MAP_GT_NEO["DEFAULT"]
    ):
        self.poll_interval = max(0.2, poll_interval)
        self.dry_run = dry_run
        self.revert_on_exit = revert_on_exit
        self.base_preset_uuid = base_preset_uuid
        self.default_wheel_preset_uuid = default_wheel_preset_uuid

        self.client = SimagicClient()
        self.lmu_reader = LMUReader()

        self.is_running = False
        self.current_vehicle_identifier: Optional[str] = None
        self.active_wheel_preset_uuid: Optional[str] = None
        self.active_base_preset_uuid: Optional[str] = None
        self.lmu_was_online = False

    def handle_signal(self, signum, frame):
        """Graceful shutdown handler for SIGINT/SIGTERM."""
        signame = signal.Signals(signum).name if hasattr(signal, 'Signals') else str(signum)
        logger.info(f"Received shutdown signal ({signame}). Stopping daemon...")
        self.stop()

    def start(self):
        """Starts the daemon polling loop."""
        self.is_running = True

        signal.signal(signal.SIGINT, self.handle_signal)
        signal.signal(signal.SIGTERM, self.handle_signal)

        logger.info("=" * 65)
        logger.info("🏎️  SIMAGIC WHEEL DAEMON STARTED")
        logger.info("=" * 65)
        logger.info(f"  • Polling Interval : {self.poll_interval:.1f}s")
        logger.info(f"  • Mode              : {'[DRY RUN]' if self.dry_run else '[LIVE ACTIVE]'}")
        logger.info(f"  • Revert on exit    : {self.revert_on_exit}")
        logger.info(f"  • Base Preset UUID  : {self.base_preset_uuid}")
        logger.info(f"  • Default Wheel UUID: {self.default_wheel_preset_uuid}")
        logger.info("-" * 65)

        # Check SimPro connectivity
        self._check_simpro_status()

        logger.info("Watching for Le Mans Ultimate (LMU) sessions... (Press Ctrl+C to stop)")

        while self.is_running:
            try:
                self.poll_once()
            except Exception as e:
                logger.error(f"Error during poll cycle: {e}", exc_info=logger.isEnabledFor(logging.DEBUG))

            if self.is_running:
                time.sleep(self.poll_interval)

        self._cleanup()
        logger.info("Simagic Wheel Daemon stopped cleanly.")

    def stop(self):
        """Stops the daemon."""
        self.is_running = False

    def _check_simpro_status(self) -> bool:
        """Verifies if SimPro Manager REST API is reachable."""
        if self.client.is_api_running():
            logger.info("[SimPro] Connected to SimPro Manager v3 REST server on port 4010.")
            return True
        else:
            logger.warning("[SimPro] Warning: SimPro Manager v3 REST API is not reachable on 127.0.0.1:4010.")
            logger.warning("[SimPro] Please ensure SimPro Manager v3 is running in the background.")
            return False

    def poll_once(self) -> Optional[Dict[str, Any]]:
        """
        Executes a single polling iteration.
        Returns vehicle info dict if a vehicle is detected, else None.
        """
        veh_info = self.lmu_reader.get_active_vehicle()

        if veh_info:
            if not self.lmu_was_online:
                logger.info("🎮 Le Mans Ultimate detected online!")
                self.lmu_was_online = True

            ident = veh_info.get("identifier", "").strip()
            if ident and ident != self.current_vehicle_identifier:
                self._on_vehicle_detected(ident, veh_info)
            return veh_info
        else:
            if self.lmu_was_online:
                logger.info("🏁 LMU session ended or vehicle unloaded.")
                self._on_vehicle_unloaded()
                self.lmu_was_online = False
            return None

    def _on_vehicle_detected(self, vehicle_id: str, veh_info: Dict[str, Any]):
        """Triggered when a new vehicle is selected or loaded in LMU."""
        model_name, target_preset_uuid, preset_name = resolve_vehicle_to_preset(vehicle_id)
        source = veh_info.get("source", "UNKNOWN")

        logger.info(f"🚘 [CAR LOADED] '{model_name}' (Raw: '{vehicle_id}', Source: {source})")
        logger.info(f"   Target GT NEO Preset : '{preset_name}' [{target_preset_uuid}]")

        # 1. Switch GT NEO Steering Wheel Preset
        if target_preset_uuid != self.active_wheel_preset_uuid:
            if self.dry_run:
                logger.info(f"   [DRY RUN] Would switch GT NEO profile to '{preset_name}'")
                self.active_wheel_preset_uuid = target_preset_uuid
            else:
                ok = self.client.select_wheel_preset(target_preset_uuid)
                if ok:
                    logger.info(f"   ✅ [SWITCHED] GT NEO profile set to '{preset_name}' via CAN-FD")
                    self.active_wheel_preset_uuid = target_preset_uuid
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

        self.current_vehicle_identifier = vehicle_id

    def _on_vehicle_unloaded(self):
        """Triggered when exiting the track or closing LMU."""
        if self.revert_on_exit and self.default_wheel_preset_uuid:
            if self.active_wheel_preset_uuid != self.default_wheel_preset_uuid:
                logger.info("   Reverting GT NEO profile to default profile...")
                if not self.dry_run:
                    self.client.select_wheel_preset(self.default_wheel_preset_uuid)
                self.active_wheel_preset_uuid = self.default_wheel_preset_uuid

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
        revert_on_exit=args.revert_on_exit
    )

    if args.once:
        logger.info("Simagic Wheel Daemon single poll cycle:")
        daemon._check_simpro_status()
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
