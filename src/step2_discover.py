"""Step 2 (temporary recon): log in, then dump page structure + network traffic.

The output of this script is what tells us the real API/field names, so that
the collectors can be written against facts instead of guesses.
"""
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _boot  # noqa: E402
import creds  # noqa: E402
import login as L  # noqa: E402
from util import banner, log  # noqa: E402


class Recorder:
    """Collect xhr/fetch traffic so we can see what the page actually calls."""

    def __init__(self):
        self.items = []

    def attach(self, page):
        page.on("response", self._on)

    def _on(self, resp):
        try:
            req = resp.request
            if req.resource_type not in ("xhr", "fetch"):
                return
            item = {
                "status": resp.status,
                "method": req.method,
                "url": resp.url,
                "content_type": resp.headers.get("content-type", ""),
                "post_data": (req.post_data or "")[:3000],
            }
            if "json" in item["content_type"]:
                try:
                    item["body"] = resp.text()[:150000]
                except Exception:
                    pass
            self.items.append(item)
        except Exception:
            pass

    def dump(self, name):
        path = _boot.DATA / f"net_{name}.json"
        path.write_text(json.dumps(self.items, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"  抓到 {len(self.items)} 个接口请求 -> {path.name}")
        return self.items


def snapshot(page, name):
    """Save DOM + screenshot + visible text for later inspection."""
    ( _boot.DATA / f"dom_{name}.html" ).write_text(page.content(), encoding="utf-8")
    L.shot(page, name)
    try:
        text = page.inner_text("body")
    except Exception:
        text = ""
    ( _boot.DATA / f"text_{name}.txt" ).write_text(text[:20000], encoding="utf-8")
    log(f"  页面快照 -> dom_{name}.html / shot_{name}.png")


def main() -> int:
    banner("抓取探查（只读，不选课）")

    c = creds.load()
    if not c:
        log("没有找到凭据，请先运行  1-首次登录.bat")
        return 1

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            ctx, page = L.launch(p, headless=False)
        except Exception as exc:
            log(f"浏览器启动失败：{exc}")
            return 1

        try:
            if not L.ensure_login(page, c["username"], c["password"]):
                log("登录失败，停止。")
                return 1

            # ---------- 博雅选课页 ----------
            log("")
            log("[1/2] 打开博雅选课页面…")
            rec = Recorder()
            rec.attach(page)
            page.goto(L.BYKC_COURSE, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(8000)
            snapshot(page, "bykc_course")
            rec.dump("bykc_course")

            # 顺便看看页面上的表格/下拉框，便于定位筛选控件
            try:
                controls = page.evaluate("""() => {
                    const out = [];
                    document.querySelectorAll('table').forEach((t,i) =>
                        out.push({kind:'table', idx:i, rows:t.rows.length,
                                  head:(t.rows[0]?t.rows[0].innerText:'').slice(0,300)}));
                    document.querySelectorAll('select,button,input').forEach(e =>
                        out.push({kind:e.tagName.toLowerCase(), text:(e.innerText||'').slice(0,40),
                                  ph:e.placeholder||'', cls:(e.className||'').toString().slice(0,50)}));
                    return out.slice(0, 120);
                }""")
                (_boot.DATA / "controls_bykc.json").write_text(
                    json.dumps(controls, ensure_ascii=False, indent=1), encoding="utf-8")
                log(f"  控件清单 {len(controls)} 项 -> controls_bykc.json")
            except Exception:
                log("  控件清单抓取失败（不影响后续）")

            # ---------- 教务系统 ----------
            log("")
            log("[2/2] 打开教务系统首页…")
            rec2 = Recorder()
            rec2.attach(page)
            page.goto(L.BYXT, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(9000)
            snapshot(page, "byxt_home")
            rec2.dump("byxt_home")

            # 尝试点开“课表”
            log("")
            log("尝试进入课表页面…")
            clicked = False
            for label in ("我的课表", "课表查询", "课表", "我的课程"):
                try:
                    loc = page.get_by_text(label, exact=False)
                    if loc.count() > 0:
                        loc.first.click(timeout=4000)
                        clicked = True
                        log(f"  点击了「{label}」")
                        break
                except Exception:
                    continue
            if clicked:
                page.wait_for_timeout(7000)
                rec3 = Recorder()
                rec3.attach(page)
                snapshot(page, "byxt_kb")
                rec3.dump("byxt_kb")
            else:
                log("  没找到课表入口，先只保存首页。")

        except Exception:
            log("探查过程出现异常：")
            log(traceback.format_exc(limit=4))
            return 1
        finally:
            try:
                ctx.close()
            except Exception:
                pass

    log("")
    log("探查完成。把 data/ 目录下的文件给我就行（不含密码，只有页面结构和接口返回）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
