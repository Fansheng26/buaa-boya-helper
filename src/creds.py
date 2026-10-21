"""Credential storage: JSON payload encrypted with Windows DPAPI."""
import json

import _boot
from dpapi_store import protect, unprotect

CRED_FILE = _boot.SECRETS / "cred.bin"
_ENTROPY = b"buaa-boya-panel-v1"


def exists() -> bool:
    return CRED_FILE.exists()


def save(username: str, password: str) -> None:
    payload = json.dumps({"username": username, "password": password}).encode("utf-8")
    CRED_FILE.write_bytes(protect(payload, _ENTROPY))


def load() -> dict | None:
    if not CRED_FILE.exists():
        return None
    try:
        raw = unprotect(CRED_FILE.read_bytes(), _ENTROPY)
        return json.loads(raw.decode("utf-8"))
    except OSError:
        return None


def clear() -> None:
    CRED_FILE.unlink(missing_ok=True)
