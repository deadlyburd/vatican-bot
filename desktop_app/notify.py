"""Cross-platform desktop notifications (best-effort, never raises)."""
from __future__ import annotations

import shutil
import subprocess
import sys
from typing import List, Optional


def build_command(title: str, message: str, platform: Optional[str] = None) -> Optional[List[str]]:
    """Return the argv to show a desktop notification on the given platform."""
    p = platform or sys.platform
    if p == "darwin":
        script = f'display notification "{message}" with title "{title}"'
        return ["osascript", "-e", script]
    if p.startswith("linux"):
        if shutil.which("notify-send"):
            return ["notify-send", title, message]
        return None
    if p == "win32":
        ps = (
            "[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,"
            "ContentType=WindowsRuntime]|Out-Null;"
            "$t=[Windows.UI.Notifications.ToastTemplateType]::ToastText02;"
            "$x=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent($t);"
            f"$x.GetElementsByTagName('text')[0].AppendChild($x.CreateTextNode('{title}'))|Out-Null;"
            f"$x.GetElementsByTagName('text')[1].AppendChild($x.CreateTextNode('{message}'))|Out-Null;"
            "$n=New-Object Windows.UI.Notifications.ToastNotification($x);"
            "[Windows.UI.Notifications.ToastNotificationManager]"
            "::CreateToastNotifier('Vatican Sniper').Show($n)"
        )
        return ["powershell", "-NoProfile", "-Command", ps]
    return None


def notify(title: str, message: str, platform: Optional[str] = None) -> bool:
    """Show a notification. Returns False if unsupported/failed (never raises)."""
    cmd = build_command(title, message, platform)
    if not cmd:
        return False
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False
