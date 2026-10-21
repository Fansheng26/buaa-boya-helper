"""Bootstrap: put the vendored dependencies on sys.path and keep temp files inside the project."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPS = ROOT / ".deps"
TMP = ROOT / ".tmp"
DATA = ROOT / "data"
OUT = ROOT / "out"
SECRETS = ROOT / "secrets"

for d in (TMP, DATA, OUT, SECRETS):
    d.mkdir(parents=True, exist_ok=True)

# Playwright's driver needs a writable temp dir it can mkdtemp in.
os.environ["TMP"] = str(TMP)
os.environ["TEMP"] = str(TMP)

if str(DEPS) not in sys.path:
    sys.path.insert(0, str(DEPS))
