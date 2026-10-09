"""
Tool: Create Windows Desktop, Start Menu, and Startup Shortcuts
Generates Windows .lnk shortcuts that start the tray app silently with pythonw.exe and the
SimagicWheelDaemon.pyw launcher (no VBScript, no console window).

Usage:
    python tools/create_windows_shortcuts.py [--startup] [--no-desktop]
    python tools/create_windows_shortcuts.py --remove
"""

import os
import sys
import subprocess
import argparse

# Safe UTF-8 encoding on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SHORTCUT_NAME = "Simagic Wheel Daemon.lnk"


def get_windows_folder(folder_name: str) -> str:
    """Gets real Windows special folder path via .NET Environment, respecting localization and OneDrive."""
    ps_cmd = f"[Environment]::GetFolderPath('{folder_name}')"
    res = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
        capture_output=True,
        text=True,
        creationflags=0x08000000
    )
    return res.stdout.strip()


def find_pythonw() -> str:
    """pythonw.exe of the interpreter running this tool (the one with pystray/pillow installed)."""
    candidate = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return candidate if os.path.isfile(candidate) else "pythonw.exe"


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def create_lnk(shortcut_dest: str, pythonw: str, launcher: str, repo_dir: str, icon_path: str, description: str):
    """Creates a Windows .lnk shortcut: pythonw.exe "<repo>\\SimagicWheelDaemon.pyw"."""
    os.makedirs(os.path.dirname(shortcut_dest), exist_ok=True)

    ps_cmd = f"""
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut({_ps_quote(shortcut_dest)})
    $Shortcut.TargetPath = {_ps_quote(pythonw)}
    $Shortcut.Arguments = {_ps_quote('"' + launcher + '"')}
    $Shortcut.WorkingDirectory = {_ps_quote(repo_dir)}
    $Shortcut.IconLocation = {_ps_quote(icon_path + ',0')}
    $Shortcut.Description = {_ps_quote(description)}
    $Shortcut.Save()
    """
    res = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
        capture_output=True,
        text=True,
        creationflags=0x08000000
    )
    if res.returncode == 0:
        print(f"  [OK] Created shortcut: {shortcut_dest}")
    else:
        print(f"  [ERROR] Failed to create {shortcut_dest}: {res.stderr}")


def main():
    parser = argparse.ArgumentParser(description="Create Windows Shortcuts for Simagic Wheel Daemon")
    parser.add_argument("--startup", action="store_true", help="Also add shortcut to Windows Startup folder")
    parser.add_argument("--no-desktop", action="store_true", help="Do not create the Desktop shortcut")
    parser.add_argument("--remove", action="store_true", help="Remove the Desktop, Start Menu and Startup shortcuts")
    args = parser.parse_args()

    repo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    launcher = os.path.join(repo_dir, "SimagicWheelDaemon.pyw")
    icon_path = os.path.join(repo_dir, "assets", "icon.ico")
    pythonw = find_pythonw()

    # Dynamic localized / OneDrive folder paths
    folders = {
        "Desktop": get_windows_folder("Desktop"),
        "Start Menu": get_windows_folder("Programs"),
        "Startup": get_windows_folder("Startup"),
    }

    if args.remove:
        for label, folder in folders.items():
            path = os.path.join(folder, SHORTCUT_NAME) if folder else ""
            if path and os.path.isfile(path):
                os.remove(path)
                print(f"  [OK] Removed {label} shortcut: {path}")
        return

    print("=" * 65)
    print("      CREATING SIMAGIC WHEEL DAEMON WINDOWS SHORTCUTS         ")
    print("=" * 65)
    print(f"Python (no console): {pythonw}")
    print(f"Launcher           : {launcher}")
    print(f"Icon Location      : {icon_path}\n")

    targets = []
    if not args.no_desktop:
        targets.append(("Desktop", "Simagic Wheel Daemon - Automatic LMU Profile Switching"))
    targets.append(("Start Menu", "Simagic Wheel Daemon - Automatic LMU Profile Switching"))
    if args.startup:
        targets.append(("Startup", "Simagic Wheel Daemon - Auto-Start with Windows"))

    for label, description in targets:
        if folders[label]:
            create_lnk(os.path.join(folders[label], SHORTCUT_NAME), pythonw, launcher, repo_dir, icon_path, description)

    print("\n" + "=" * 65)
    print("Shortcuts created. Launch 'Simagic Wheel Daemon' from the Start Menu")
    print("to run it as a Windows System Tray app.")
    print("=" * 65)


if __name__ == "__main__":
    main()
