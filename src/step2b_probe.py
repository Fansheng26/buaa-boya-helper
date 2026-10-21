"""Step 2b: reach the real course-select page and figure out byxt auth.

The first probe landed on the notice page because the SPA ignores a cold
navigation to /system/course-select; the route has to be triggered through the
sidebar link (ui-sref). byxt needs a separate SSO handshake, so we check that too.
"""
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _boot  # noqa: E402
import creds  # noqa: E402
import login as L  # noqa: E402
from step2_discover import Recorder, snapshot  # noqa: E402
from util import banner, log  # noqa: E402

BYXT_API = "https://byxt.buaa.edu.cn/jwapp/sys/homeapp/api/home/currentUser.do"


def open_course_select(page):
    """Trigger the ui-sref route from the sidebar (a cold URL load falls back to home)."""
    log("  通过侧边栏路由进入选课页…")
    js = """() => {
        const li = document.querySelector('li[ui-sref="system.course-select"]');
        if (li) { li.click(); return 'li'; }
        const a = document.querySelector('a[ui-sref="system.course-select"], a[href="/system/course-select"]');
        if (a) { a.click(); return 'a'; }
        try {
            angular.element(document.body).injector().get('$state').go('system.course-select');
            return 'state';
        } catch (e) { return 'none'; }
    }"""
    how = page.evaluate(js)
    log(f"  触发方式：{how}")
    page.wait_for_timeout(8000)
    return "course-select" in page.url


def main() -> int:
    banner("深入探查：选课页 + 教务登录")

    c = creds.load()
    if not c:
        log("没有凭据，请先运行 1-首次登录.bat")
        return 1

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx, page = L.launch(p, headless=False)
        try:
            if not L.ensure_login(page, c["username"], c["password"]):
                log("登录失败，停止。")
                return 1

            # ---------- 1. 博雅选课页 ----------
            log("")
            log("[1/2] 博雅选课页")
            rec = Recorder()
            rec.attach(page)
            if not open_course_select(page):
                log(f"  没能切到选课页，当前地址：{page.url}")

            # 等表格出现
            try:
                page.wait_for_selector("table tbody tr", timeout=20000)
                log("  课程表格已出现")
            except Exception:
                log("  20 秒内没等到表格")

            page.wait_for_timeout(2000)
            snapshot(page, "bykc_select")
            rec.dump("bykc_select")

            # 表格结构：表头 + 前几行
            try:
                table = page.evaluate("""() => {
                    const t = document.querySelector('table');
                    if (!t) return null;
                    const head = [...t.querySelectorAll('thead th')].map(x => x.innerText.trim());
                    const rows = [...t.querySelectorAll('tbody tr')].slice(0, 5).map(tr =>
                        [...tr.querySelectorAll('td')].map(td => td.innerText.trim()));
                    return {head, rowCount: t.querySelectorAll('tbody tr').length, rows};
                }""")
                (_boot.DATA / "table_bykc_select.json").write_text(
                    json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")
                if table:
                    log(f"  表头：{table['head']}")
                    log(f"  行数：{table['rowCount']}")
                    for r in table["rows"][:3]:
                        log(f"    {r}")
            except Exception:
                log("  表格结构解析失败（不影响后续）")

            # 页面上所有下拉框/按钮/输入框
            try:
                ctrl = page.evaluate("""() => {
                    const out = [];
                    document.querySelectorAll('select').forEach(s => out.push({
                        kind:'select', model: s.getAttribute('ng-model') || '',
                        value: s.value,
                        options: [...s.options].map(o => o.text.trim()).slice(0, 20)
                    }));
                    document.querySelectorAll('button,a.btn,input').forEach(e => {
                        const t = (e.innerText || e.value || '').trim();
                        if (t) out.push({kind: e.tagName.toLowerCase(), text: t.slice(0, 30)});
                    });
                    return out.slice(0, 80);
                }""")
                (_boot.DATA / "controls_bykc_select.json").write_text(
                    json.dumps(ctrl, ensure_ascii=False, indent=1), encoding="utf-8")
                log(f"  控件 {len(ctrl)} 项")
            except Exception:
                pass

            # ---------- 2. 教务系统 ----------
            log("")
            log("[2/2] 教务系统认证检查")
            rec2 = Recorder()
            rec2.attach(page)
            try:
                resp = page.goto(BYXT_API, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(1500)
                log(f"  最终地址：{page.url}")
                body = ""
                try:
                    body = page.inner_text("body")[:400]
                except Exception:
                    pass
                log(f"  响应预览：{' '.join(body.split())[:300]}")
                if resp:
                    log(f"  状态码：{resp.status}")
            except Exception as exc:
                log(f"  访问接口出错：{exc}")

            if "byxt.buaa.edu.cn" in page.url and "sso" not in page.url:
                log("  → SSO 会话对教务系统同样有效，直接打开首页")
                page.goto(L.BYXT, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(10000)
                snapshot(page, "byxt_home2")
                rec2.dump("byxt_home2")
            else:
                log("  → 教务系统需要单独登录，稍后处理")
                snapshot(page, "byxt_login")
                rec2.dump("byxt_login")

        except Exception:
            log("探查异常：")
            log(traceback.format_exc(limit=4))
            return 1
        finally:
            try:
                ctx.close()
            except Exception:
                pass

    log("")
    log("完成，结果都在 data/ 里。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
