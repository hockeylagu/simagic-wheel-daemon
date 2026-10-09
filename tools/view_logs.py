"""
Tool: View & Tail Simagic Wheel Daemon Logs
Displays recent debug logs or opens the log file in Windows Notepad.
"""

import os
import sys
import time
import argparse

# Safe UTF-8 encoding on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add src to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from simagic_daemon.logger import get_log_file_path, open_log_file


def tail_file(filepath: str, lines: int = 30, follow: bool = False):
    """Prints the tail of a file and optionally follows for new lines."""
    if not os.path.exists(filepath):
        print(f"  [!] Log file does not exist yet at: {filepath}")
        print("  Run the daemon first (python -m simagic_daemon) to generate logs.")
        return

    print(f"Log File Location: {filepath}")
    file_size_kb = os.path.getsize(filepath) / 1024
    print(f"Log File Size    : {file_size_kb:.1f} KB\n" + "-" * 75)

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()
        tail_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
        for line in tail_lines:
            print(line, end="")

        if follow:
            print("\n" + "-" * 75 + "\nFollowing log (Press Ctrl+C to stop)...")
            try:
                while True:
                    line = f.readline()
                    if line:
                        print(line, end="")
                    else:
                        time.sleep(0.5)
            except KeyboardInterrupt:
                print("\nStopped log follow.")


def main():
    parser = argparse.ArgumentParser(description="View Simagic Wheel Daemon Debug Logs")
    parser.add_argument("--lines", "-n", type=int, default=35, help="Number of recent lines to display (default: 35)")
    parser.add_argument("--follow", "-f", action="store_true", help="Continuously follow/tail new log lines")
    parser.add_argument("--open", "-o", action="store_true", help="Open the log file directly in Windows Notepad")
    args = parser.parse_args()

    log_path = get_log_file_path()

    if args.open:
        print(f"Opening log file in Notepad: {log_path}")
        open_log_file()
        return

    tail_file(log_path, lines=args.lines, follow=args.follow)


if __name__ == "__main__":
    main()
