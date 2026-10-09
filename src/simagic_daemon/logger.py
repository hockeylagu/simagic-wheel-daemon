"""
Centralized Logging Configuration
Provides unified console and rotating file-based debug logging for Simagic Wheel Daemon.
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional

# Safe UTF-8 encoding on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_LOG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "logs"))
DEFAULT_LOG_FILE = os.path.join(DEFAULT_LOG_DIR, "daemon.log")


def get_log_file_path(custom_path: Optional[str] = None) -> str:
    """Returns the absolute path to the active log file."""
    if custom_path:
        return os.path.abspath(custom_path)
    return DEFAULT_LOG_FILE


def setup_logging(
    log_level: int = logging.INFO,
    log_file: Optional[str] = None,
    include_console: bool = True
) -> logging.Logger:
    """
    Configures standard logging with rotating file handler and console output.
    - Max file size: 5 MB (retains 3 backups)
    - Thread-safe and UTF-8 encoded
    """
    active_log_file = get_log_file_path(log_file)
    os.makedirs(os.path.dirname(active_log_file), exist_ok=True)

    root_logger = logging.getLogger("simagic_daemon")
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers on re-initialization
    if root_logger.handlers:
        root_logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)-7s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 1. Rotating File Handler
    try:
        file_handler = RotatingFileHandler(
            active_log_file,
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
            encoding="utf-8"
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Failed to initialize file logger at {active_log_file}: {e}")

    # 2. Console Handler
    if include_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    root_logger.debug(f"Logging initialized at level: {logging.getLevelName(log_level)}. Log file: {active_log_file}")
    return root_logger


def open_log_file():
    """Opens the daemon log file in Windows default text editor (Notepad)."""
    log_path = get_log_file_path()
    if sys.platform == "win32" and os.path.exists(log_path):
        os.startfile(log_path)
    elif os.path.exists(log_path):
        import subprocess
        subprocess.Popen(["notepad.exe", log_path])


if __name__ == "__main__":
    logger = setup_logging(logging.DEBUG)
    logger.debug("Debug logging test message.")
    logger.info("Info logging test message.")
    logger.warning("Warning logging test message.")
    print(f"Log file successfully written to: {get_log_file_path()}")
