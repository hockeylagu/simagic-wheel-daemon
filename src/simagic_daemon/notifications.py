"""
Windows Native Toast Notification System
Provides non-blocking, native Windows desktop notifications for profile switching,
hardware status, and game session events.
"""

import subprocess
import base64
import sys
import threading
import time
import logging
from typing import Optional

logger = logging.getLogger("simagic_daemon.notifications")

# Cooldown cache to prevent notification flooding
_last_notification_text = ""
_last_notification_time = 0.0
_COOLDOWN_SECONDS = 3.0


def _deliver_toast(title: str, message: str):
    """Executes the WinRT PowerShell notification script in a hidden background process."""
    # Sanitize inputs to prevent PowerShell interpolation issues
    safe_title = title.replace("'", "''").replace('"', '`"')
    safe_message = message.replace("'", "''").replace('"', '`"')

    ps_script = f"""
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $textNodes = $template.GetElementsByTagName('text')
    $null = $textNodes.Item(0).AppendChild($template.CreateTextNode('{safe_title}'))
    $null = $textNodes.Item(1).AppendChild($template.CreateTextNode('{safe_message}'))
    $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Simagic Wheel Daemon')
    $notification = [Windows.UI.Notifications.ToastNotification]::new($template)
    $notifier.Show($notification)
    """

    encoded = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")
    try:
        creation_flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-EncodedCommand", encoded],
            capture_output=True,
            timeout=5.0,
            creationflags=creation_flags
        )
    except Exception as e:
        logger.debug(f"Toast notification failed: {e}")


def send_windows_notification(title: str, message: str, force: bool = False):
    """
    Sends a native Windows Toast notification asynchronously.
    Non-blocking: Spawns a lightweight daemon thread so the main loop is never delayed.
    Includes rate-limiting debounce to prevent repetitive toast popups.
    """
    global _last_notification_text, _last_notification_time

    now = time.time()
    notification_key = f"{title}:{message}"

    if not force:
        if notification_key == _last_notification_text and (now - _last_notification_time) < _COOLDOWN_SECONDS:
            return

    _last_notification_text = notification_key
    _last_notification_time = now

    # Dispatch in worker thread
    t = threading.Thread(target=_deliver_toast, args=(title, message), daemon=True)
    t.start()


if __name__ == "__main__":
    print("Testing Windows toast notification...")
    send_windows_notification(
        "Simagic Wheel Daemon",
        "Ferrari 296 GT3 loaded -> Profile set to 'GT3 296'",
        force=True
    )
    time.sleep(1.0)
    print("Done.")
