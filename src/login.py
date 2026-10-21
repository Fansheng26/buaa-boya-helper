"""Browser helpers: launch Edge and log in through the BUAA unified auth (CAS)."""
from urllib.parse import urlparse

import _boot  # noqa: F401  -- must run before importing playwright
from util import log

BYKC = "https://bykc.buaa.edu.cn/"
BYKC_COURSE = "https://bykc.buaa.edu.cn/system/course-select"
BYXT = "https://byxt.buaa.edu.cn/jwapp/sys/homeapp/home/index.html?contextPath=/jwapp"
PROFILE = _boot.ROOT / ".browser-profile"
SHOTS = _boot.DATA / "shots"

SHOTS.mkdir(parents=True, exist_ok=True)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0")

# Edge flags: keep it looking like a normal browser (the site 403s headless UAs).
LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
]


def launch(p, headless: bool = False):
    """Start a persistent Edge profile so the login session survives between runs.

    无头模式必须换掉 User-Agent：站点 WAF 会对 ...HeadlessChrome 直接回 403。
    """
    kwargs = {}
    if headless:
        kwargs["user_agent"] = UA
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE),
        channel="msedge",
        headless=headless,
        viewport={"width": 1440, "height": 900},
        args=LAUNCH_ARGS,
        **kwargs,
    )
    ctx.set_default_timeout(30000)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return ctx, page


def shot(page, name: str) -> None:
    try:
        page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=False)
    except Exception:
        pass


def _find_login_frame(page):
    """The visible account/password form lives in an iframe (cas/login-normal.html)."""
    for f in page.frames:
        if "login-normal" in (f.url or ""):
            return f
    return None


def ensure_login(page, username: str, password: str,
                 entry: str = BYKC, label: str = "博雅选课系统") -> bool:
    """Open `entry`; if it bounces to SSO, fill the CAS form. True when the entry host answers."""
    expect_host = urlparse(entry).netloc

    log(f"正在打开{label}…")
    page.goto(entry, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2000)

    if "sso.buaa.edu.cn" not in page.url:
        log("  已有有效会话，跳过登录。")
        shot(page, "00_already_logged_in")
        return True

    log("  跳到统一身份认证…")
    frame = None
    for _ in range(40):
        frame = _find_login_frame(page)
        if frame is not None:
            break
        page.wait_for_timeout(500)
    if frame is None:
        log("  没有找到登录表单（页面可能改版）。")
        shot(page, "01_no_form")
        return False

    try:
        frame.wait_for_selector("#unPassword", state="visible", timeout=20000)
    except Exception:
        log("  账号输入框不可见（可能默认停在扫码登录）。")
        shot(page, "01_form_hidden")
        return False

    captcha = False
    try:
        captcha = bool(page.evaluate("() => { try { return getPageConfig().captcha } catch (e) { return false } }"))
    except Exception:
        pass

    log("  填写账号密码…")
    frame.fill("#unPassword", username)
    frame.fill("#pwPassword", password)
    shot(page, "01_sso_filled")

    if captcha:
        log("  这次登录要求验证码：请在浏览器窗口里手动填写并点「登录」，")
        input("  完成后再回到本窗口按回车继续…")
    else:
        # 页面自己的登录逻辑：把值交给父窗口的 doLogin，再提交隐藏表单
        frame.evaluate("loginPassword()")

    for _ in range(45):
        page.wait_for_timeout(1000)
        if "sso.buaa.edu.cn" not in page.url:
            break
    else:
        snippet = ""
        try:
            snippet = page.inner_text("body")[:400]
        except Exception:
            pass
        log("  登录没有跳回目标系统。页面提示：" + " ".join(snippet.split())[:200])
        shot(page, "02_sso_stuck")
        return False

    page.wait_for_timeout(1500)

    if urlparse(page.url).netloc != expect_host:
        log(f"  登录后跳到了意外地址：{page.url}")
        shot(page, "03_unexpected")
        return False

    # SPA 还要几秒才会把 main 渲染出来
    page.wait_for_timeout(5000)
    if "sso.buaa.edu.cn" in page.url:
        log("  会话似乎没有建立（又被弹回认证页）。")
        shot(page, "04_bounced")
        return False

    log("  登录成功。")
    shot(page, "05_bykc_home")
    return True
