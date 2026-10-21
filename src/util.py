"""Tiny logging helper: prints to console and appends to data/run.log (UTF-8)."""
import sys

import _boot  # noqa: F401  (sets up paths)


def log(msg=""):
    line = str(msg)
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "utf-8"
        print(line.encode(enc, "replace").decode(enc, "replace"), flush=True)
    path = _boot.DATA / "run.log"
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def banner(title):
    log("")
    log("=" * 62)
    log(title)
    log("=" * 62)
