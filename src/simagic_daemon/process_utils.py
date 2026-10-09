"""
Windows Process & Application Utilities
Monitors and manages processes for SimPro Manager v3 and Le Mans Ultimate (LMU).
"""

import subprocess
import os
import sys
import logging
from typing import Optional, List

logger = logging.getLogger("simagic_daemon.process")

KNOWN_SIMPRO_PATHS = [
    r"C:\Program Files (x86)\Simagic\Simpro3\bin\simpro3.exe",
    r"C:\Program Files\Simagic\Simpro3\bin\simpro3.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Simagic\Simpro3\bin\simpro3.exe"),
]

SIMPRO_PROCESS_NAMES = ["simpro3.exe", "simpro3"]
LMU_PROCESS_NAMES = ["lemansultimate.exe", "lemansultimate", "rfactor2.exe"]


def is_process_running(process_names: List[str]) -> bool:
    """Checks whether any of the given process names are currently running on Windows."""
    if sys.platform != "win32":
        return False

    try:
        # Use tasklist with CREATE_NO_WINDOW
        cmd = ["tasklist", "/FO", "CSV", "/NH"]
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            creationflags=0x08000000,
            timeout=3.0
        )
        output_lower = res.stdout.lower()
        for name in process_names:
            if name.lower() in output_lower:
                return True
        return False
    except Exception as e:
        logger.debug(f"Process check error: {e}")
        return False


def is_simpro_running() -> bool:
    """Returns True if SimPro Manager v3 is currently running."""
    return is_process_running(SIMPRO_PROCESS_NAMES)


def is_lmu_running() -> bool:
    """Returns True if Le Mans Ultimate is currently running."""
    return is_process_running(LMU_PROCESS_NAMES)


def find_simpro_executable() -> Optional[str]:
    """Finds the installed simpro3.exe executable on disk."""
    for path in KNOWN_SIMPRO_PATHS:
        if os.path.isfile(path):
            return path
    return None


def launch_simpro() -> bool:
    """Launches SimPro Manager v3 if not already running."""
    if is_simpro_running():
        logger.info("SimPro Manager is already running.")
        return True

    exe = find_simpro_executable()
    if not exe:
        logger.warning("Could not locate simpro3.exe on disk.")
        return False

    try:
        logger.info(f"Launching SimPro Manager from: {exe}")
        subprocess.Popen(
            [exe],
            creationflags=0x00000008 if sys.platform == "win32" else 0, # DETACHED_PROCESS
            close_fds=True
        )
        return True
    except Exception as e:
        logger.error(f"Failed to launch SimPro Manager: {e}")
        return False


if __name__ == "__main__":
    print(f"SimPro running: {is_simpro_running()}")
    print(f"LMU running:    {is_lmu_running()}")
    print(f"SimPro exe:     {find_simpro_executable()}")
