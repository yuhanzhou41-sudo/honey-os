"""Windows toast notifications for Study reminders, callable from WSL."""

import base64
import logging
import os
import shutil
import subprocess
from xml.sax.saxutils import escape

logger = logging.getLogger(__name__)

_POWERSHELL = (
    "/mnt/c/WINDOWS/System32/WindowsPowerShell/v1.0/powershell.exe",
    "powershell.exe",
)
# A registered Windows shell AppID, so the toast is not suppressed on Win10/11.
_APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"


def _powershell():
    for candidate in _POWERSHELL:
        if candidate.startswith("/"):
            if os.path.exists(candidate):
                return candidate
        elif shutil.which(candidate):
            return candidate
    return None


def available():
    """Whether a Windows PowerShell is reachable from this runtime."""
    return _powershell() is not None


def send(title, message):
    """Show a Windows system notification. Returns True when it was handed off."""
    powershell = _powershell()
    if not powershell:
        logger.info("Study reminder toast skipped: no Windows PowerShell available")
        return False
    title = " ".join(str(title or "").split())[:60] or "HoneyOS"
    message = " ".join(str(message or "").split())[:140]
    if not message:
        return False
    xml = (
        '<toast scenario="reminder"><visual><binding template="ToastGeneric">'
        f"<text>{escape(title)}</text><text>{escape(message)}</text>"
        "</binding></visual></toast>"
    )
    script = (
        "$ErrorActionPreference='Stop';"
        "$ProgressPreference='SilentlyContinue';"
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
        "ContentType=WindowsRuntime] > $null;"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, "
        "ContentType=WindowsRuntime] > $null;"
        "$xmlText=@'\n" + xml + "\n'@;"
        "$xml=New-Object Windows.Data.Xml.Dom.XmlDocument;"
        "$xml.LoadXml($xmlText);"
        "$toast=[Windows.UI.Notifications.ToastNotification]::new($xml);"
        f"$appId='{_APP_ID}';"
        "[Windows.UI.Notifications.ToastNotificationManager]"
        "::CreateToastNotifier($appId).Show($toast);"
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        result = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            capture_output=True, timeout=25,
        )
    except (OSError, subprocess.SubprocessError):
        logger.warning("Study reminder toast failed to start", exc_info=True)
        return False
    if result.returncode != 0:
        stderr = result.stderr.decode("gbk", "replace").strip()[:300]
        logger.warning("Study reminder toast failed (rc=%s): %s", result.returncode, stderr)
        return False
    return True
