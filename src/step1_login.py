"""Step 1: ask for the student id / password, verify the login, store them with DPAPI."""
import getpass
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _boot  # noqa: E402
import creds  # noqa: E402
import login as L  # noqa: E402
from util import banner, log  # noqa: E402


def main() -> int:
    banner("北航博雅选课助手 · 首次登录")

    if creds.exists():
        log("检测到已保存过凭据，本次输入会覆盖它。")

    log("请输入统一身份认证的账号密码。密码输入时不会显示，也不会写入日志。")
    log("")
    username = input("学工号：").strip()
    if not username:
        log("学工号为空，已取消。")
        return 1
    password = getpass.getpass("密码（不显示）：")
    if not password:
        log("密码为空，已取消。")
        return 1

    from playwright.sync_api import sync_playwright

    log("")
    log("即将打开 Edge 窗口，登录成功后会自动关闭。请稍候…")

    ok = False
    with sync_playwright() as p:
        try:
            ctx, page = L.launch(p, headless=False)
        except Exception as exc:
            log(f"浏览器启动失败：{exc}")
            log("如果是因为浏览器已经在运行，请先关掉所有 Edge 窗口再试。")
            return 1
        try:
            ok = L.ensure_login(page, username, password)
        except Exception:
            log("登录过程出现异常：")
            log(traceback.format_exc(limit=3))
        finally:
            try:
                ctx.close()
            except Exception:
                pass

    if not ok:
        log("")
        log("登录失败，凭据没有保存。请重新运行本脚本再试一次。")
        return 1

    creds.save(username, password)
    log("")
    log("凭据已用 Windows DPAPI 加密保存（secrets/cred.bin）。")
    log("只有当前 Windows 用户在这台机器上能解密，拷走文件也没用。")
    log("")
    log("下一步：双击  2-抓取探查.bat")
    return 0


if __name__ == "__main__":
    sys.exit(main())
