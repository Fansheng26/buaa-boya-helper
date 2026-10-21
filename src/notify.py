"""Windows 通知（Toast），走 PowerShell 5.1 的 WinRT 接口，不需要装任何第三方库。"""
import subprocess
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

# 用 PowerShell 自己的 AUMID，这样通知能正常显示归属，不用注册应用
AUMID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"

_PS = """$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xml = @"
<toast activationType="protocol" launch="{launch}">
  <visual><binding template="ToastGeneric">
    <text>{title}</text>
    <text>{body}</text>
  </binding></visual>
</toast>
"@
$doc = New-Object Windows.Data.Xml.Dom.XmlDocument
$doc.LoadXml($xml)
$toast = New-Object Windows.UI.Notifications.ToastNotification $doc
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{aumid}').Show($toast)
"""


def toast(title: str, body: str, launch: str = "") -> bool:
    script = (_PS
              .replace("{title}", escape(title))
              .replace("{body}", escape(body))
              .replace("{launch}", escape(launch or ""))
              .replace("{aumid}", AUMID))
    path = Path(tempfile.gettempdir()) / "boya_toast.ps1"
    # PowerShell 5.1 读 UTF-8 需要 BOM，否则中文乱码
    path.write_text(script, encoding="utf-8-sig")
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        return r.returncode == 0
    except Exception:
        return False


if __name__ == "__main__":
    ok = toast("博雅选课助手", "通知测试：如果你看到这条，说明提醒功能可用。")
    print("toast ok" if ok else "toast failed")
