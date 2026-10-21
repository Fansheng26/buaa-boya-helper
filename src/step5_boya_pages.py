"""Step 5 (v2): walk every page of the 博雅 list using the Angular scope directly."""
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _boot  # noqa: E402
import creds  # noqa: E402
import login as L  # noqa: E402
from util import banner, log  # noqa: E402

READ_ROWS = """() => [...document.querySelectorAll('table tbody tr')].map(tr =>
    [...tr.querySelectorAll('td')].map(td => td.innerText.trim()))"""

STATE_JS = """() => {
  try {
    const s = angular.element(document.querySelector('table')).scope();
    const vm = s.vm;
    return {cur: vm.pageInfo.currentPage, total: vm.pageInfo.totalPages,
            size: vm.pageInfo.itemsPerPage, elems: vm.pageInfo.totalElements,
            n: (vm.data.coursePageList || []).length};
  } catch (e) { return {err: String(e)}; }
}"""

SELECT_JS = """(n) => {
  try {
    const s = angular.element(document.querySelector('table')).scope();
    s.$apply(() => s.vm.selectPage(n));
    return 'scope';
  } catch (e) { return 'err:' + e.message; }
}"""

DUMP_ALL_JS = """() => {
  try {
    const s = angular.element(document.querySelector('table')).scope();
    const d = s.vm.data;
    const raw = d.courseSrcList || null;
    return raw ? {len: raw.length, json: angular.toJson(raw)} : null;
  } catch (e) { return {err: String(e)}; }
}"""


def rows(page):
    try:
        r = page.evaluate(READ_ROWS)
    except Exception:
        return []
    return [x for x in r if len(x) >= 10]


def main(headless: bool = False) -> int:
    banner("博雅课程翻页采集 v2")
    c = creds.load()
    if not c:
        log("没有凭据")
        return 1

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx, page = L.launch(p, headless=headless)
        try:
            if not L.ensure_login(page, c["username"], c["password"]):
                return 1

            log("")
            log("[1] 进入选课页")
            page.evaluate("""() => {
                const li = document.querySelector('li[ui-sref="system.course-select"]');
                if (li) li.click();
            }""")
            page.wait_for_timeout(8000)
            page.wait_for_selector("table tbody tr", timeout=25000)

            st = page.evaluate(STATE_JS)
            log(f"  分页状态：{st}")

            # 先试一次性把全量结构化数据取下来
            full = page.evaluate(DUMP_ALL_JS)
            if full and full.get("len"):
                log(f"  courseSrcList 里已有 {full['len']} 条，直接保存")
                (_boot.DATA / "boya_src.json").write_text(full["json"], encoding="utf-8")

            total = (st or {}).get("total") or 1
            log(f"  共 {total} 页，每页 {(st or {}).get('size')} 条，总计 {(st or {}).get('elems')} 条")

            all_rows = []
            seen = set()

            def absorb(rs):
                n = 0
                for r in rs:
                    k = tuple(r)
                    if k not in seen:
                        seen.add(k)
                        all_rows.append(r)
                        n += 1
                return n

            absorb(rows(page))
            log(f"  第 1 页：新增 {len(all_rows)}")

            for page_no in range(2, min(total, 40) + 1):
                before = rows(page)
                before_sig = tuple(before[0]) if before else None
                how = page.evaluate(SELECT_JS, page_no)
                ok = False
                for _ in range(24):
                    page.wait_for_timeout(400)
                    cur = page.evaluate(STATE_JS) or {}
                    if cur.get("cur") == page_no:
                        ok = True
                        break
                if not ok:
                    log(f"  第 {page_no} 页没切换成功（{how}），停止")
                    break

                # 页码变了不代表表格已经重绘，等首行真的变化
                for _ in range(10):
                    now_rows = rows(page)
                    if now_rows and tuple(now_rows[0]) != before_sig:
                        break
                    page.wait_for_timeout(300)

                n = absorb(rows(page))
                log(f"  第 {page_no}/{total} 页：新增 {n}（累计 {len(all_rows)}）")

            (_boot.DATA / "boya_rows_all.json").write_text(
                json.dumps(all_rows, ensure_ascii=False, indent=1), encoding="utf-8")
            log(f"  合计 {len(all_rows)} 条 -> boya_rows_all.json")

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
    sys.exit(main(headless="--headless" in sys.argv))
