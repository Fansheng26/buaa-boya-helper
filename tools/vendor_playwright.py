"""离线安装 Playwright：不经过 pip，直接从清华镜像下载 wheel 解包到 .deps/

适用场景：pip 装不上（网络受限、公司代理、沙箱权限等）。
用法：python tools/vendor_playwright.py
"""
import io
import pathlib
import re
import sys
import time
import urllib.request
import zipfile
from urllib.parse import urljoin

MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple/"
ROOT = pathlib.Path(__file__).resolve().parent.parent
DEPS = ROOT / ".deps"
PKGS = ["playwright", "greenlet", "pyee", "typing_extensions"]


def vkey(filename):
    stem = filename.rsplit("/", 1)[-1].split("-")
    return tuple(int(n) for n in re.findall(r"\d+", stem[1]))


def compatible(pkg, filename):
    name = filename.rsplit("/", 1)[-1]
    if not ("win_amd64" in name or "none-any" in name):
        return False
    if pkg == "playwright":
        return "py3-none-win_amd64" in name
    if pkg == "greenlet":
        return "cp3" in name and "win_amd64" in name
    return "none-any" in name


def main() -> int:
    DEPS.mkdir(exist_ok=True)
    for pkg in PKGS:
        base = MIRROR + pkg + "/"
        html = urllib.request.urlopen(base, timeout=30).read().decode()
        hrefs = re.findall(r'href="([^"#]+\.whl)', html)
        cands = [h for h in hrefs if compatible(pkg, h)]
        if not cands:
            print(f"!! 没有找到 {pkg} 的可用 wheel")
            return 1
        url = urljoin(base, max(cands, key=vkey))
        t = time.time()
        blob = urllib.request.urlopen(url, timeout=120).read()
        print(f"{pkg}: {url.rsplit('/', 1)[-1]}  {len(blob)//1024} KiB  {time.time()-t:.1f}s")
        zipfile.ZipFile(io.BytesIO(blob)).extractall(DEPS)
    print("完成，依赖在 .deps/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
