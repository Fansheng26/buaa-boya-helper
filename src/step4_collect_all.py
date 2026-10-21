"""Step 4: paginate the whole 博雅 list, then capture the 教务 timetable (API + grid + 学期课表)."""
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

READ_ROWS = """() => [...document.querySelectorAll('table tbody tr')].map(tr =>
    [...tr.querySelectorAll('td')].map(td => td.innerText.trim()))"""

GRID_JS = """() => {
  const cols = [...document.querySelectorAll('[class*="kbappTimetableDayColumnRoot"]')];
  return cols.map((c, i) => ({
    idx: i,
    text: c.innerText.trim().slice(0, 60),
    courses: [...c.querySelectorAll('[class*="kbappTimetableCourseRenderRoot"]')]
                .map(x => x.innerText.trim())
  }));
}"""


def read_rows(page):
    try:
        rows = page.evaluate(READ_ROWS)
    except Exception:
        return []
    return [r for r in rows if len(r) >= 10]


def sig(row):
    return (row[1] + "|" + row[3][:30]) if row else ""


def collect_boya(page):
    log("")
    log("[1/2] 博雅课程：翻页采集")
    js = """() => {
        const li = document.querySelector('li[ui-sref="system.course-select"]');
        if (li) { li.click(); return true; }
        return false;
    }"""
    page.evaluate(js)
    page.wait_for_timeout(7000)
    try:
        page.wait_for_selector("table tbody tr", timeout=20000)
    except Exception:
        log("  没等到表格")
        return []

    all_rows = []
    seen = set()
    for page_no in range(1, 61):
        rows = read_rows(page)
        if not rows:
            log(f"  第 {page_no} 页空，结束")
            break
        new = 0
        for r in rows:
            k = tuple(r)
            if k not in seen:
                seen.add(k)
                all_rows.append(r)
                new += 1
        log(f"  第 {page_no} 页：{len(rows)} 行（新增 {new}）")

        prev = sig(rows[0])
        nxt = page.locator('nav.pagination a', has_text="下一页")
        if nxt.count() == 0:
            log("  没有「下一页」，到底了")
            break
        nxt.first.click()
        moved = False
        for _ in range(25):
            page.wait_for_timeout(400)
            rows2 = read_rows(page)
            if rows2 and sig(rows2[0]) != prev:
                moved = True
                break
        if not moved:
            log("  页码没有变化，到底了")
            break

    (_boot.DATA / "boya_rows_all.json").write_text(
        json.dumps(all_rows, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"  合计 {len(all_rows)} 条 -> boya_rows_all.json")
    return all_rows


def collect_byxt(page):
    log("")
    log("[2/2] 教务课表")
    ok = L.ensure_login(page, *_CREDS, entry=BYXT_API, label="教务系统")
    if not ok:
        log("  教务登录失败")
        return

    rec = Recorder()
    rec.attach(page)
    page.goto(L.BYXT, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(12000)
    rec.dump("byxt_home4")
    snapshot(page, "byxt_home4")

    try:
        grid = page.evaluate(GRID_JS)
        (_boot.DATA / "byxt_grid_week.json").write_text(
            json.dumps(grid, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"  周课表列数：{len(grid)}，每列课程数：{[len(g['courses']) for g in grid]}")
    except Exception:
        log("  周课表结构读取失败")

    # 切到学期课表
    log("  切换到学期课表…")
    try:
        page.get_by_text("学期课表", exact=True).first.click(timeout=5000)
        page.wait_for_timeout(9000)
        rec2 = Recorder()
        rec2.attach(page)
        snapshot(page, "byxt_term")
        rec2.dump("byxt_term")
        try:
            grid2 = page.evaluate(GRID_JS)
            (_boot.DATA / "byxt_grid_term.json").write_text(
                json.dumps(grid2, ensure_ascii=False, indent=1), encoding="utf-8")
            log(f"  学期课表列数：{len(grid2)}")
        except Exception:
            pass
        # 表格形式（如果有）
        tables = page.evaluate("""() => [...document.querySelectorAll('table')].map(t => ({
            head: [...t.querySelectorAll('thead th')].map(x => x.innerText.trim()),
            rows: [...t.querySelectorAll('tbody tr')].slice(0,3).map(tr =>
                [...tr.querySelectorAll('td')].map(td => td.innerText.trim())),
            count: t.querySelectorAll('tbody tr').length}))""")
        (_boot.DATA / "byxt_term_tables.json").write_text(
            json.dumps(tables, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"  表格数：{len(tables)}")
    except Exception as exc:
        log(f"  切换学期课表失败：{exc}")


_CREDS = ("", "")


def main() -> int:
    global _CREDS
    banner("采集：博雅全量 + 教务课表")
    c = creds.load()
    if not c:
        log("没有凭据")
        return 1
    _CREDS = (c["username"], c["password"])

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx, page = L.launch(p, headless=False)
        try:
            if not L.ensure_login(page, c["username"], c["password"]):
                log("博雅登录失败")
                return 1
            collect_boya(page)
            collect_byxt(page)
        except Exception:
            log("异常：")
            log(traceback.format_exc(limit=4))
            return 1
        finally:
            try:
                ctx.close()
            except Exception:
                pass
    log("")
    log("完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
