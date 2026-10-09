"""
Tool: Create Windows Desktop, Start Menu, and Startup Shortcuts
Generates Windows .lnk shortcuts configured with the project icon and silent pythonw launcher.
"""

import os
import sys
import subprocess
import argparse

# Safe UTF-8 encoding on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


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


def create_lnk(shortcut_dest: str, vbs_launcher: str, repo_dir: str, icon_path: str, description: str):
    """Creates a Windows .lnk shortcut targeting wscript.exe with the .vbs launcher."""
    dest_dir = os.path.dirname(shortcut_dest)
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir, exist_ok=True)

    ps_cmd = f"""
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut('{shortcut_dest}')
    $Shortcut.TargetPath = 'wscript.exe'
    $Shortcut.Arguments = '`"{vbs_launcher}`"'
    $Shortcut.WorkingDirectory = '{repo_dir}'
    $Shortcut.IconLocation = '{icon_path},0'
    $Shortcut.Description = '{description}'
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
    args = parser.parse_args()

    repo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    vbs_launcher = os.path.join(repo_dir, "SimagicWheelDaemon.vbs")
    icon_path = os.path.join(repo_dir, "assets", "icon.ico")

    # Dynamic localized / OneDrive folder paths
    desktop_dir = get_windows_folder("Desktop")
    start_menu_dir = get_windows_folder("Programs")
    startup_dir = get_windows_folder("Startup")

    print("=" * 65)
    print("      CREATING SIMAGIC WHEEL DAEMON WINDOWS SHORTCUTS         ")
    print("=" * 65)
    print(f"Target Launcher: {vbs_launcher}")
    print(f"Icon Location  : {icon_path}")
    print(f"Desktop Dir    : {desktop_dir}\n")

    # 1. Desktop Shortcut
    if desktop_dir:
        desktop_shortcut = os.path.join(desktop_dir, "Simagic Wheel Daemon.lnk")
        create_lnk(desktop_shortcut, vbs_launcher, repo_dir, icon_path, "Simagic Wheel Daemon - Automatic LMU Profile Switching")

    # 2. Start Menu Shortcut
    if start_menu_dir:
        start_menu_shortcut = os.path.join(start_menu_dir, "Simagic Wheel Daemon.lnk")
        create_lnk(start_menu_shortcut, vbs_launcher, repo_dir, icon_path, "Simagic Wheel Daemon - Automatic LMU Profile Switching")

    # 3. Optional Startup Shortcut
    if args.startup and startup_dir:
        startup_shortcut = os.path.join(startup_dir, "Simagic Wheel Daemon.lnk")
        create_lnk(startup_shortcut, vbs_launcher, repo_dir, icon_path, "Simagic Wheel Daemon - Auto-Start with Windows")

    print("\n" + "=" * 65)
    print("Shortcuts created successfully!")
    print("You can now double-click 'Simagic Wheel Daemon' on your Desktop")
    print("to launch it directly as a Windows System Tray app.")
    print("=" * 65)


if __name__ == "__main__":
    main()
