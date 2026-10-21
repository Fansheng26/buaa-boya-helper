"""桌面小组件：无边框、置顶、可拖动的小窗，展示可报名 / 即将开抢的博雅课。

- 每分钟重算倒计时，窗口高度随内容自适应
- 没有可报名名额时每 20 分钟静默刷新一次，有名额后放宽到 6 小时
- 支持手动刷新、提醒/提示音开关（设置存 data/settings.json）
"""
import atexit
import json
import os
import subprocess
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _boot  # noqa: E402
import desktop_layer  # noqa: E402

OUT = _boot.OUT
PANEL = OUT / "panel.json"
HTML = OUT / "boya.html"
SETTINGS = _boot.DATA / "settings.json"
REFRESH = Path(__file__).resolve().parent / "refresh.py"
ALERT = Path(__file__).resolve().parent / "alert_popup.py"
COURSE_URL = "https://bykc.buaa.edu.cn/system/course-select"
LOCK = _boot.DATA / "widget.lock"

_last_good = {"generated": "—", "items": []}

W = 340
BG = "#151a24"
CARD = "#1f2634"
INK = "#eef1f7"
SUB = "#8d97ab"
ACCENT = "#4c8dff"
GREEN = "#3ddc84"
AMBER = "#ffb020"

FONT = "Microsoft YaHei UI"
INTERVAL = 3600 * 1000               # 每小时刷新一次
ALERT_COOLDOWN = 1800                # 两次弹窗至少间隔 30 分钟


def load_settings():
    try:
        s = json.loads(SETTINGS.read_text(encoding="utf-8"))
    except Exception:
        s = {}
    s.setdefault("notify", True)
    s.setdefault("sound", True)
    s.setdefault("last_alert", 0)
    return s


def save_settings(s):
    try:
        SETTINGS.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def load_panel():
    """读失败（比如正好在写文件）时沿用上一次的好数据，避免界面闪成空列表。"""
    global _last_good
    try:
        d = json.loads(PANEL.read_text(encoding="utf-8"))
        if isinstance(d, dict) and "items" in d:
            _last_good = d
        return d
    except Exception:
        return _last_good


def _pid_alive(pid: int) -> bool:
    import ctypes
    SYNCHRONIZE = 0x00100000
    h = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if not h:
        return False
    try:
        return ctypes.windll.kernel32.WaitForSingleObject(h, 0) == 0x102  # WAIT_TIMEOUT
    finally:
        ctypes.windll.kernel32.CloseHandle(h)


def claim_single_instance() -> bool:
    """已经有小组件在跑就直接退出，避免两个窗口互相抢层级导致闪烁。"""
    try:
        pid = int(LOCK.read_text(encoding="utf-8").strip())
        if pid != os.getpid() and _pid_alive(pid):
            return False
    except Exception:
        pass
    try:
        LOCK.write_text(str(os.getpid()), encoding="utf-8")
        atexit.register(lambda: LOCK.unlink(missing_ok=True))
    except Exception:
        pass
    return True


def parse(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M")
    except Exception:
        return None


def human_delta(delta):
    secs = int(delta.total_seconds())
    if secs < 0:
        secs = -secs
    if secs < 3600:
        return f"{max(1, secs // 60)} 分钟"
    if secs < 86400:
        return f"{secs // 3600} 小时"
    return f"{secs // 86400} 天"


def weekday_cn(dt):
    return "一二三四五六日"[dt.weekday()]


class Widget:
    def __init__(self, root):
        self.root = root
        self._drag = (0, 0)
        self.settings = load_settings()
        self.refreshing = False
        self.proc = None
        self.refresh_start = 0
        self._timer = None
        self._open_count = 0
        self.minimized = False
        self._press = None

        root.title("博雅小组件")
        root.overrideredirect(True)
        root.attributes("-alpha", 0.97)
        root.configure(bg=BG)
        root.attributes("-topmost", False)
        try:
            root.attributes("-toolwindow", True)
        except Exception:
            pass

        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        self.pos = [sw - W - 28, 120]
        root.geometry(f"{W}x400+{self.pos[0]}+{self.pos[1]}")
        root.update_idletasks()

        # 压到 z-order 最底层：只贴在桌面上，永远不挡其它应用
        self.hwnd = int(root.wm_frame(), 16)
        self._raised = True
        root.bind_all("<Button-1>", lambda e: setattr(self, "_raised", True), add="+")
        self.lower_to_bottom()
        try:
            (OUT / "widget_state.json").write_text(
                json.dumps({"mode": "bottom", "hwnd": self.hwnd}, ensure_ascii=False),
                encoding="utf-8")
        except Exception:
            pass

        self.head = tk.Frame(root, bg=BG, height=36)
        self.head.pack(fill="x", padx=14, pady=(10, 0))
        self.title = tk.Label(self.head, text="博雅 · 可报名", bg=BG, fg=INK,
                              font=(FONT, 10, "bold"), anchor="w")
        self.title.pack(side="left")
        close = tk.Label(self.head, text="✕", bg=BG, fg=SUB, font=(FONT, 10), cursor="hand2")
        close.pack(side="right")
        close.bind("<Button-1>", lambda e: root.destroy())

        self.min_btn = tk.Label(self.head, text="—", bg=BG, fg=SUB, font=(FONT, 10), cursor="hand2")
        self.min_btn.pack(side="right", padx=(0, 12))
        self.min_btn.bind("<Button-1>", lambda e: self.toggle_min())

        for w in (self.head, self.title):
            w.bind("<ButtonPress-1>", self.on_press)
            w.bind("<B1-Motion>", self.on_drag)
            w.bind("<ButtonRelease-1>", self.on_release)

        self.body = tk.Frame(root, bg=BG)
        self.body.pack(fill="both", expand=True, padx=14, pady=(2, 0))

        self.foot = tk.Frame(root, bg=BG)
        self.foot.pack(side="bottom", fill="x", padx=14, pady=(4, 10))

        root.bind("<Double-Button-1>", lambda e: self.open_panel())

        self.seen_openable = None
        self.render()
        self.tick()
        self.arm()
        root.after(2500, self.first_check)

    # ---------- window ----------
    def lower_to_bottom(self):
        """被点过（层级被抬起）才重新压回最底层，平时不做无谓的层级调整。"""
        if self._raised:
            self._raised = False
            try:
                import ctypes
                HWND_BOTTOM = 1
                SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010
                ctypes.windll.user32.SetWindowPos(
                    ctypes.c_void_p(self.hwnd), ctypes.c_void_p(HWND_BOTTOM),
                    0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)
            except Exception:
                pass
        self.root.after(1500, self.lower_to_bottom)

    def start_drag(self, e):
        self._drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def on_press(self, e):
        self._press = (e.x_root, e.y_root)
        self.start_drag(e)

    def on_release(self, e):
        # 最小化状态下，轻点（而不是拖动）标题栏就展开
        if self.minimized and self._press:
            if abs(e.x_root - self._press[0]) < 4 and abs(e.y_root - self._press[1]) < 4:
                self.restore()
        self._press = None

    def toggle_min(self):
        if self.minimized:
            self.restore()
        else:
            self.minimize()

    def minimize(self):
        self.minimized = True
        self.body.pack_forget()
        self.foot.pack_forget()
        self.min_btn.config(text="▢")
        self.root.geometry(f"{W}x44+{self.pos[0]}+{self.pos[1]}")

    def restore(self):
        self.minimized = False
        self.min_btn.config(text="—")
        self.body.pack(fill="both", expand=True, padx=14, pady=(2, 0))
        self.foot.pack(side="bottom", fill="x", padx=14, pady=(4, 10))
        self.render()

    def on_drag(self, e):
        self.pos = [e.x_root - self._drag[0], e.y_root - self._drag[1]]
        self.root.geometry(f"+{self.pos[0]}+{self.pos[1]}")

    def fit(self):
        """按内容高度调整窗口，保证底部按钮永远可见。"""
        self.root.update_idletasks()
        need = (self.head.winfo_reqheight() + self.body.winfo_reqheight()
                + self.foot.winfo_reqheight() + 30)
        limit = self.root.winfo_screenheight() - 110
        need = max(280, min(need, limit))
        self.root.geometry(f"{W}x{need}+{self.pos[0]}+{self.pos[1]}")

    def open_panel(self):
        try:
            import os
            os.startfile(str(HTML))
        except Exception:
            pass

    def open_course(self):
        """用系统默认浏览器打开选课页（会停在公告页，再点左侧「我的课程 → 选课」）。"""
        try:
            import webbrowser
            webbrowser.open(COURSE_URL)
        except Exception:
            try:
                import os
                os.startfile(COURSE_URL)
            except Exception:
                pass

    # ---------- refresh ----------
    def first_check(self):
        try:
            age = datetime.now().timestamp() - PANEL.stat().st_mtime
        except OSError:
            age = 1e9
        if age > 3600:
            self.refresh()

    def interval(self):
        return INTERVAL

    def arm(self):
        if self._timer is not None:
            try:
                self.root.after_cancel(self._timer)
            except Exception:
                pass
        self._timer = self.root.after(self.interval(), self.auto_tick)

    def auto_tick(self):
        self._timer = None
        self.refresh()

    def refresh(self):
        if self.refreshing:
            return
        self.refreshing = True
        self.refresh_start = datetime.now().timestamp()
        try:
            self.proc = subprocess.Popen(
                [sys.executable, str(REFRESH)],
                cwd=str(_boot.ROOT),
                creationflags=0x08000000,      # CREATE_NO_WINDOW
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            self.refreshing = False
            self.proc = None
        self.render()
        self.root.after(1500, self.poll_refresh)

    def poll_refresh(self):
        if self.proc is None:
            self.refreshing = False
            self.arm()
            return
        done = self.proc.poll() is not None
        if not done and datetime.now().timestamp() - self.refresh_start > 420:
            try:
                self.proc.kill()
            except Exception:
                pass
            done = True
        if done:
            self.proc = None
            self.refreshing = False
            self.render()
            self.arm()
            return
        self.root.after(1500, self.poll_refresh)

    # ---------- content ----------
    def clear(self):
        for w in self.body.winfo_children():
            w.destroy()
        for w in self.foot.winfo_children():
            w.destroy()

    def section(self, text, color):
        f = tk.Frame(self.body, bg=BG)
        f.pack(fill="x", pady=(7, 3))
        tk.Label(f, text="●", bg=BG, fg=color, font=(FONT, 7)).pack(side="left")
        tk.Label(f, text=text, bg=BG, fg=SUB, font=(FONT, 8, "bold")).pack(side="left", padx=4)

    def row(self, item, note, note_color):
        card = tk.Frame(self.body, bg=CARD)
        card.pack(fill="x", pady=2)
        tk.Frame(card, bg=item.get("color", "#666"), width=3).pack(side="left", fill="y")
        inner = tk.Frame(card, bg=CARD)
        inner.pack(side="left", fill="x", expand=True, padx=8, pady=5)

        s = parse(item["start"])
        e = parse(item["end"])

        # 第一行：课程名 + 倒计时
        l1 = tk.Frame(inner, bg=CARD)
        l1.pack(fill="x")
        name = item["name"]
        if len(name) > 17:
            name = name[:16] + "…"
        tk.Label(l1, text=name, bg=CARD, fg=INK, font=(FONT, 9), anchor="w").pack(side="left")
        if note:
            tk.Label(l1, text=note, bg=CARD, fg=note_color,
                     font=(FONT, 8, "bold")).pack(side="right")

        # 第二行：类型 + 上课时间（含星期）
        l2 = tk.Frame(inner, bg=CARD)
        l2.pack(fill="x", pady=(1, 0))
        tk.Label(l2, text=item["cat"], bg=CARD, fg=item.get("color", "#999"),
                 font=(FONT, 7, "bold")).pack(side="left")
        if s and e:
            tk.Label(l2, text=f'  {item["start"][5:10]} 周{weekday_cn(s)} '
                              f'{item["start"][11:16]}–{item["end"][11:16]}',
                     bg=CARD, fg="#c8d0e0", font=(FONT, 8)).pack(side="left")

        # 第三行：选课窗口
        if item.get("pick_start") and item.get("pick_end"):
            tk.Label(inner, text=f'选课 {item["pick_start"][5:16]} → {item["pick_end"][5:16]}',
                     bg=CARD, fg=SUB, font=(FONT, 7), anchor="w").pack(fill="x")

    def chip(self, parent, text, color, cmd):
        lb = tk.Label(parent, text=text, bg=BG, fg=color, font=(FONT, 8), cursor="hand2")
        lb.pack(side="left", padx=(0, 12))
        lb.bind("<Button-1>", lambda e: cmd())

    def render(self):
        data = load_panel()
        items = data.get("items", [])
        now = datetime.now()

        cand = [d for d in items if d.get("free")]
        openable = [d for d in cand if d["state"] == "可选·未满"]
        upcoming = []
        for d in cand:
            if d["state"] != "预告":
                continue
            ps = parse(d.get("pick_start", ""))
            if ps and ps > now:
                upcoming.append((ps, d))
        upcoming.sort(key=lambda x: x[0])

        self._open_count = len(openable)
        self.title.config(text=f"博雅 · {len(openable)} 门可报名")
        self._track(openable)
        if self.minimized:
            return
        self.clear()

        # 行数预算：优先「可以报名」，剩余给「即将开抢」
        n_open = min(len(openable), 3)
        n_up = min(len(upcoming), 6 - n_open if n_open else 6)

        self.section("可以报名", GREEN)
        if n_open:
            for d in openable[:n_open]:
                pe = parse(d.get("pick_end", ""))
                self.row(d, f"剩 {human_delta(pe - now)}" if pe else "", GREEN)
        else:
            tk.Label(self.body, text="暂时没有余量，都被抢完了", bg=BG, fg=SUB,
                     font=(FONT, 9), anchor="w").pack(fill="x", padx=6, pady=2)

        self.section("即将开抢", AMBER)
        if n_up:
            for ps, d in upcoming[:n_up]:
                self.row(d, f"{human_delta(ps - now)}后开抢", AMBER)
        else:
            tk.Label(self.body, text="暂时没有待开放的预告课", bg=BG, fg=SUB,
                     font=(FONT, 9), anchor="w").pack(fill="x", padx=6, pady=2)

        # ---- footer ----
        row1 = tk.Frame(self.foot, bg=BG)
        row1.pack(fill="x")
        status = "刷新中…" if self.refreshing else f'数据 {data.get("generated", "—")[5:16]}'
        tk.Label(row1, text=status, bg=BG, fg=(AMBER if self.refreshing else SUB),
                 font=(FONT, 8), anchor="w").pack(side="left")
        openb = tk.Label(row1, text="打开面板", bg=BG, fg=ACCENT, font=(FONT, 8), cursor="hand2")
        openb.pack(side="right")
        openb.bind("<Button-1>", lambda e: self.open_panel())

        cb = tk.Label(row1, text="选课页", bg=BG, fg=ACCENT, font=(FONT, 8), cursor="hand2")
        cb.pack(side="right", padx=(0, 12))
        cb.bind("<Button-1>", lambda e: self.open_course())

        row2 = tk.Frame(self.foot, bg=BG)
        row2.pack(fill="x", pady=(5, 0))
        on_off = lambda k: "开" if self.settings[k] else "关"
        self.chip(row2, f'提醒 {on_off("notify")}',
                  GREEN if self.settings["notify"] else SUB, lambda: self.toggle("notify"))
        self.chip(row2, f'声音 {on_off("sound")}',
                  GREEN if self.settings["sound"] else SUB, lambda: self.toggle("sound"))
        self.chip(row2, "立即刷新", SUB if self.refreshing else ACCENT, self.refresh)

        self.fit()

    def _track(self, openable):
        """记录「可报名」集合，出现新增时提醒。"""
        cur = {(d["name"], d["start"]) for d in openable}
        if self.seen_openable is None:
            self.seen_openable = cur
            return
        new = cur - self.seen_openable
        if new:
            self.alert([d for d in openable if (d["name"], d["start"]) in new])
        self.seen_openable = cur

    def toggle(self, key):
        self.settings[key] = not self.settings[key]
        save_settings(self.settings)
        self.render()

    def alert(self, items):
        if not self.settings["notify"]:
            return
        now = datetime.now().timestamp()
        if now - self.settings.get("last_alert", 0) < ALERT_COOLDOWN:
            return
        self.settings["last_alert"] = now
        save_settings(self.settings)

        if self.settings["sound"]:
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass

        # 提醒框用独立进程弹，保证能浮到最上层（小组件本身在桌面层）
        payload = {
            "count": len(items),
            "items": [f'{d["name"][:18]}  {d["start"][5:16]}' for d in items[:4]],
        }
        try:
            subprocess.Popen(
                [sys.executable, str(ALERT), json.dumps(payload, ensure_ascii=False)],
                cwd=str(_boot.ROOT),
                creationflags=0x08000000,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    def tick(self):
        self.root.after(60_000, self._tick)

    def _tick(self):
        self.render()
        self.tick()


def main():
    if not claim_single_instance():
        return 0
    root = tk.Tk()
    Widget(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
