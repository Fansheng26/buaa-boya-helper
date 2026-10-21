"""把窗口挂到桌面层（WorkerW），让它只出现在桌面上、不挡任何应用。

这是壁纸/桌面挂件类程序常用的做法：向 Progman 发 0x052C 让系统生成 WorkerW，
再把窗口 SetParent 到承载桌面图标的那一层。失败就返回 False，调用方自行降级。
"""
import ctypes
from ctypes import wintypes

WM_SPAWN_WORKER = 0x052C

_u = ctypes.windll.user32
_u.FindWindowW.restype = wintypes.HWND
_u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
_u.FindWindowExW.restype = wintypes.HWND
_u.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
_u.SetParent.restype = wintypes.HWND
_u.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
_u.GetParent.restype = wintypes.HWND
_u.GetParent.argtypes = [wintypes.HWND]
_u.SendMessageTimeoutW.restype = wintypes.LPARAM
_u.SendMessageTimeoutW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    wintypes.UINT, wintypes.UINT, ctypes.POINTER(wintypes.DWORD),
]


def _find_workerw():
    progman = _u.FindWindowW("Progman", None)
    if progman:
        result = wintypes.DWORD()
        _u.SendMessageTimeoutW(progman, WM_SPAWN_WORKER, 0, 0, 0, 1000, ctypes.byref(result))

    found = []

    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(top, _):
        view = _u.FindWindowExW(top, 0, "SHELLDLL_DefView", None)
        if view:
            worker = _u.FindWindowExW(0, top, "WorkerW", None)
            if worker:
                found.append(worker)
        return True

    _u.EnumWindows(EnumProc(cb), 0)
    return found[0] if found else None


def attach(hwnd: int) -> dict:
    """返回 {'ok': bool, 'host': 'workerw'|'progman', 'parent': int, 'err': str}

    Win10 有独立的 WorkerW 承载壁纸；Win11 24H2 之后 SHELLDLL_DefView 直接挂在
    Progman 下，没有可用的 WorkerW，此时退化为挂到 Progman。
    """
    info = {"ok": False, "host": None, "parent": 0, "err": ""}
    try:
        target = _find_workerw()
        info["host"] = "workerw" if target else "progman"
        if not target:
            target = _u.FindWindowW("Progman", None)
        if not target:
            info["err"] = "no desktop window"
            return info

        _u.SetParent(wintypes.HWND(hwnd), wintypes.HWND(target))
        parent = _u.GetParent(wintypes.HWND(hwnd))
        info["parent"] = int(parent) if parent else 0
        info["ok"] = info["parent"] == int(target)
        if not info["ok"]:
            info["err"] = "SetParent failed"
    except Exception as exc:  # pragma: no cover
        info["err"] = repr(exc)
    return info
