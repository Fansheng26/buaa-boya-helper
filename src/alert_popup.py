"""独立进程弹出顶部提醒框。单独跑是为了不受桌面层挂载影响，能真正浮到最上层。"""
import json
import sys
import tkinter as tk

FONT = "Microsoft YaHei UI"
BG = "#0b3d2e"
GREEN = "#3ddc84"
INK = "#eef1f7"


def main() -> int:
    payload = json.loads(sys.argv[1])
    names = payload.get("items", [])
    count = payload.get("count", len(names))

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(bg=BG)

    h = 78 + 22 * min(len(names), 4)
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"300x{h}+{sw - 330}+{sh - h - 120}")

    tk.Label(root, text=f"新放出 {count} 门可报名", bg=BG, fg=GREEN,
             font=(FONT, 11, "bold"), anchor="w").pack(fill="x", padx=14, pady=(12, 4))
    for n in names[:4]:
        tk.Label(root, text=n, bg=BG, fg=INK, font=(FONT, 8), anchor="w").pack(fill="x", padx=14)
    tk.Label(root, text="点击关闭", bg=BG, fg="#6f8f82", font=(FONT, 7), anchor="w").pack(
        fill="x", padx=14, pady=(6, 0))

    root.bind("<Button-1>", lambda e: root.destroy())
    root.after(9000, root.destroy)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
