"""Windows DPAPI wrapper (ctypes, no pywin32 needed).

Encrypts/decrypts bytes with the current Windows user's credentials, so the
stored password can only be read by this user on this machine.
"""
import ctypes
from ctypes import wintypes

_CRYPTPROTECT_UI_FORBIDDEN = 0x1


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


_crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_crypt32.CryptProtectData.restype = wintypes.BOOL
_crypt32.CryptProtectData.argtypes = [
    ctypes.POINTER(_DataBlob),
    wintypes.LPCWSTR,
    ctypes.POINTER(_DataBlob),
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(_DataBlob),
]

_crypt32.CryptUnprotectData.restype = wintypes.BOOL
_crypt32.CryptUnprotectData.argtypes = [
    ctypes.POINTER(_DataBlob),
    ctypes.POINTER(wintypes.LPWSTR),
    ctypes.POINTER(_DataBlob),
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(_DataBlob),
]

_kernel32.LocalFree.argtypes = [ctypes.c_void_p]
_kernel32.LocalFree.restype = ctypes.c_void_p


def _make_blob(data):
    buf = ctypes.create_string_buffer(data, len(data))
    blob = _DataBlob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    return blob, buf  # keep buf alive


def _read_blob(blob):
    return ctypes.string_at(blob.pbData, blob.cbData)


def protect(data: bytes, entropy: bytes | None = None) -> bytes:
    src, _keep1 = _make_blob(data)
    ent, _keep2 = _make_blob(entropy) if entropy else (None, None)
    out = _DataBlob()
    ok = _crypt32.CryptProtectData(
        ctypes.byref(src),
        None,
        ctypes.byref(ent) if ent is not None else None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out),
    )
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return _read_blob(out)
    finally:
        _kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


def unprotect(data: bytes, entropy: bytes | None = None) -> bytes:
    src, _keep1 = _make_blob(data)
    ent, _keep2 = _make_blob(entropy) if entropy else (None, None)
    out = _DataBlob()
    ok = _crypt32.CryptUnprotectData(
        ctypes.byref(src),
        None,
        ctypes.byref(ent) if ent is not None else None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out),
    )
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return _read_blob(out)
    finally:
        _kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))
