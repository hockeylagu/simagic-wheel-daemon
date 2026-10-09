"""
Windows Process & Application Utilities
Monitors and manages processes for SimPro Manager v3 and Le Mans Ultimate (LMU).
"""

import subprocess
import os
import sys
import time
import threading
import logging
from typing import Optional, List

logger = logging.getLogger("simagic_daemon.process")

KNOWN_SIMPRO_PATHS = [
    r"C:\Program Files (x86)\Simagic\Simpro3\bin\simpro3.exe",
    r"C:\Program Files\Simagic\Simpro3\bin\simpro3.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Simagic\Simpro3\bin\simpro3.exe"),
]

SIMPRO_PROCESS_NAMES = ["simpro3.exe", "simpro3"]
# The game binary is "Le Mans Ultimate.exe" (with spaces); keep the legacy spellings as fallbacks
LMU_PROCESS_NAMES = ["le mans ultimate.exe", "lemansultimate.exe", "rfactor2.exe"]

# tasklist spawns a process; share one snapshot between the daemon loop and the tray menu
_PROCESS_CACHE_TTL = 5.0
_process_cache_lock = threading.Lock()
_process_cache_output = ""
_process_cache_time = 0.0


def _get_process_list_lower(max_age: float = _PROCESS_CACHE_TTL) -> str:
    """Returns the lowercased tasklist output, reusing a cached snapshot younger than max_age."""
    global _process_cache_output, _process_cache_time

    with _process_cache_lock:
        now = time.monotonic()
        if _process_cache_time and (now - _process_cache_time) < max_age:
            return _process_cache_output

        # Use tasklist with CREATE_NO_WINDOW
        cmd = ["tasklist", "/FO", "CSV", "/NH"]
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            creationflags=0x08000000,
            timeout=3.0
        )
        _process_cache_output = res.stdout.lower()
        _process_cache_time = now
        return _process_cache_output


def invalidate_process_cache():
    """Forces the next process check to take a fresh snapshot."""
    global _process_cache_time
    with _process_cache_lock:
        _process_cache_time = 0.0


def is_process_running(process_names: List[str]) -> bool:
    """Checks whether any of the given process names are currently running on Windows."""
    if sys.platform != "win32":
        return False

    try:
        output_lower = _get_process_list_lower()
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


SINGLE_INSTANCE_MUTEX_NAME = "Local\\SimagicWheelDaemon"
_single_instance_handle = None


def acquire_single_instance_lock(name: str = SINGLE_INSTANCE_MUTEX_NAME) -> bool:
    """
    Takes a Windows named mutex so only one daemon (console or tray) drives the wheel at a time.
    Returns False if another instance already holds it. The mutex is released by Windows when
    this process exits, even after a crash.
    """
    global _single_instance_handle
    if sys.platform != "win32" or _single_instance_handle is not None:
        return True

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    ERROR_ALREADY_EXISTS = 183
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        logger.warning(f"Could not create single-instance mutex (error {ctypes.get_last_error()}); continuing")
        return True
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False

    _single_instance_handle = handle
    return True


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
        invalidate_process_cache()
        return True
    except Exception as e:
        logger.error(f"Failed to launch SimPro Manager: {e}")
        return False


if __name__ == "__main__":
    print(f"SimPro running: {is_simpro_running()}")
    print(f"LMU running:    {is_lmu_running()}")
    print(f"SimPro exe:     {find_simpro_executable()}")
