"""Step 3: collect every page of the 博雅 course list, then log into 教务 and dump its menu."""
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
BYXT_MENUS = "https://byxt.buaa.edu.cn/jwapp/sys/homeapp/api/home/menus.do?userType=undefined"

READ_JS = """() => {
  const rows = [...document.querySelectorAll('table tbody tr')].map(tr =>
    [...tr.querySelectorAll('td')].map(td => td.innerText.trim()));
  let info = null, list = null;
  try {
    const el = document.querySelector('[ng-controller]');
    const s = angular.element(el).scope();
    info = s.vm && s.vm.pageInfo ? JSON.parse(angular.toJson(s.vm.pageInfo)) : null;
    const d = s.vm && s.vm.data;
    const raw = (d && (d.coursePageList || d.courseSrcList)) || null;
    list = raw ? JSON.parse(angular.toJson(raw)) : null;
  } catch (e) {}
  return {rows, info, list};
}"""

SELECT_JS = """(n) => {
  const el = document.querySelector('[ng-controller]');
  const s = angular.element(el).scope();
  s.$apply(() => s.vm.selectPage(n));
  return true;
}"""


def collect(page):
    data = page.evaluate(READ_JS)
    rows = [r for r in data["rows"] if len(r) >= 10]
    return rows, data.get("info"), data.get("list")


def open_course_page(page):
    js = """() => {
        const li = document.querySelector('li[ui-sref="system.course-select"]');
        if (li) { li.click(); return 'li'; }
        const a = document.querySelector('a[href="/system/course-select"]');
        if (a) { a.click(); return 'a'; }
        return 'none';
    }"""
    log("  通过侧边栏进入选课页：" + page.evaluate(js))
    page.wait_for_timeout(7000)
    try:
        page.wait_for_selector("table tbody tr", timeout=20000)
        return True
    except Exception:
        log("  没等到课程表格")
        return False


def main() -> int:
    banner("采集博雅课程列表")

    c = creds.load()
    if not c:
        log("没有凭据，请先运行 1-首次登录.bat")
        return 1

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx, page = L.launch(p, headless=False)
        try:
            if not L.ensure_login(page, c["username"], c["password"]):
                log("博雅登录失败，停止。")
                return 1

            # ---------------- 博雅 ----------------
            log("")
            log("[1/2] 博雅课程列表")
            if not open_course_page(page):
                return 1

            rows, info, scope_list = collect(page)
            total = (info or {}).get("totalPages") or 1
            log(f"  页码信息：{info}")
            log(f"  第 1 页 {len(rows)} 行，共 {total} 页")

            all_rows = list(rows)
            all_scope = [scope_list]

            for pg in range(2, min(total, 60) + 1):
                try:
                    page.evaluate(SELECT_JS, pg)
                except Exception as exc:
                    log(f"  翻到第 {pg} 页失败：{exc}")
                    break
                page.wait_for_timeout(1200)
                rows2, info2, lst2 = collect(page)
                if not rows2:
                    log(f"  第 {pg} 页没数据，停止")
                    break
                all_rows.extend(rows2)
                all_scope.append(lst2)
                log(f"  第 {pg}/{total} 页：{len(rows2)} 行")

            (_boot.DATA / "boya_rows.json").write_text(
                json.dumps(all_rows, ensure_ascii=False, indent=1), encoding="utf-8")
            (_boot.DATA / "boya_scope.json").write_text(
                json.dumps(all_scope, ensure_ascii=False, indent=1), encoding="utf-8")
            log(f"  合计 {len(all_rows)} 行 -> boya_rows.json")

            if all_scope and all_scope[0]:
                sample = all_scope[0][0]
                log("  scope 对象字段：" + ", ".join(sorted(sample.keys())))
                (_boot.DATA / "boya_scope_sample.json").write_text(
                    json.dumps(sample, ensure_ascii=False, indent=1), encoding="utf-8")

            # ---------------- 教务 ----------------
            log("")
            log("[2/2] 教务系统")
            ok = L.ensure_login(page, c["username"], c["password"],
                                entry=BYXT_API, label="教务系统")
            if not ok:
                log("  教务登录没成功，先保存现场")
                snapshot(page, "byxt_fail")
            else:
                try:
                    body = page.inner_text("body")
                    (_boot.DATA / "byxt_currentuser.json").write_text(body[:20000], encoding="utf-8")
                    log("  当前用户：" + " ".join(body.split())[:160])
                except Exception:
                    pass

                try:
                    page.goto(BYXT_MENUS, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(1500)
                    body = page.inner_text("body")
                    (_boot.DATA / "byxt_menus.json").write_text(body[:200000], encoding="utf-8")
                    log(f"  菜单 JSON {len(body)} 字节 -> byxt_menus.json")
                except Exception:
                    log("  菜单接口读取失败")

                try:
                    page.goto(L.BYXT, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(10000)
                    snapshot(page, "byxt_home3")
                    log("  首页快照已保存")
                except Exception:
                    log("  首页打开失败")

        except Exception:
            log("采集异常：")
            log(traceback.format_exc(limit=4))
            return 1
        finally:
            try:
                ctx.close()
            except Exception:
                pass

    log("")
    log("采集完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
