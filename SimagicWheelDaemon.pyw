"""
Silent launcher for the Simagic Wheel Daemon system tray app (no console window, no VBScript).

Run it with pythonw.exe (that is what the shortcuts and SimagicWheelDaemon.bat do):
    pythonw.exe SimagicWheelDaemon.pyw

It always runs the code in this folder's src/, whatever other copy pip may have installed.
"""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.chdir(ROOT)  # logs/ and local/ are resolved relative to the repository

from simagic_daemon.tray import main  # noqa: E402

main()
