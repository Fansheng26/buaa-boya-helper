"""后台刷新：无头抓取博雅列表 + 重新生成面板。供小组件调用，不弹任何窗口。"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _boot  # noqa: E402

# pythonw 下没有 stdout，所有输出落到日志文件
if sys.stdout is None:
    _fh = open(_boot.DATA / "refresh.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = _fh

from util import banner, log  # noqa: E402

LOCK = _boot.DATA / "refresh.lock"
STALE = 900  # 15 分钟内视为还在跑


def main() -> int:
    if LOCK.exists() and (time.time() - LOCK.stat().st_mtime) < STALE:
        log("已有刷新在进行，跳过本次")
        return 0

    LOCK.write_text(str(os.getpid()), encoding="utf-8")
    try:
        banner("后台刷新")
        log(time.strftime("%Y-%m-%d %H:%M:%S"))

        import step5_boya_pages as s5
        if s5.main(headless=True) != 0:
            log("抓取失败")
            return 1

        import make_panel as mp
        return mp.main()
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
