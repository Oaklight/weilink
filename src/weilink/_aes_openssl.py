"""AES-128-ECB via OpenSSL libcrypto (ctypes).

Provides the same interface as _aes.py but delegates to the system
OpenSSL library for native-C performance.  Raises OSError at import
time if libcrypto cannot be located or loaded.

Not part of the public API.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import sys
from ctypes import POINTER, byref, c_int, c_void_p, create_string_buffer

# ---------------------------------------------------------------------------
# Locate and load libcrypto
# ---------------------------------------------------------------------------

_CANDIDATES: dict[str, list[str]] = {
    "linux": ["libcrypto.so.3", "libcrypto.so.1.1", "libcrypto.so"],
    "darwin": [
        "/opt/homebrew/lib/libcrypto.dylib",
        "/usr/local/lib/libcrypto.dylib",
        "libcrypto.dylib",
    ],
    "win32": [
        "libcrypto-3-x64.dll",
        "libcrypto-3.dll",
        "libcrypto-1_1-x64.dll",
        "libcrypto-1_1.dll",
    ],
}


def _load_libcrypto() -> ctypes.CDLL:
    # Prefer the canonical name via find_library (works cross-platform).
    path = ctypes.util.find_library("crypto")
    if path:
        return ctypes.CDLL(path)

    # Platform-specific fallback names / absolute paths.
    for candidate in _CANDIDATES.get(sys.platform, []):
        try:
            return ctypes.CDLL(candidate)
        except OSError:
            continue

    raise OSError("libcrypto not found")


_lib = _load_libcrypto()

# ---------------------------------------------------------------------------
# Declare EVP function signatures
# ---------------------------------------------------------------------------

_lib.EVP_CIPHER_CTX_new.restype = c_void_p
_lib.EVP_CIPHER_CTX_new.argtypes = []

_lib.EVP_CIPHER_CTX_free.restype = None
_lib.EVP_CIPHER_CTX_free.argtypes = [c_void_p]

_lib.EVP_aes_128_ecb.restype = c_void_p
_lib.EVP_aes_128_ecb.argtypes = []

for _fn_name in (
    "EVP_EncryptInit_ex",
    "EVP_DecryptInit_ex",
):
    fn = getattr(_lib, _fn_name)
    # (ctx, type, engine, key, iv) -> int
    fn.restype = c_int
    fn.argtypes = [c_void_p, c_void_p, c_void_p, ctypes.c_char_p, ctypes.c_char_p]

for _fn_name in (
    "EVP_EncryptUpdate",
    "EVP_DecryptUpdate",
):
    fn = getattr(_lib, _fn_name)
    # (ctx, out, outl, in, inl) -> int
    fn.restype = c_int
    fn.argtypes = [c_void_p, ctypes.c_char_p, POINTER(c_int), ctypes.c_char_p, c_int]

for _fn_name in (
    "EVP_EncryptFinal_ex",
    "EVP_DecryptFinal_ex",
):
    fn = getattr(_lib, _fn_name)
    # (ctx, out, outl) -> int
    fn.restype = c_int
    fn.argtypes = [c_void_p, ctypes.c_char_p, POINTER(c_int)]

_AES_128_ECB = _lib.EVP_aes_128_ecb()

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_BLOCK = 16


def aes128_ecb_encrypt(data: bytes, key: bytes) -> bytes:
    """Encrypt *data* with AES-128-ECB and PKCS7 padding.

    Args:
        data: Plaintext bytes.
        key: 16-byte AES key.

    Returns:
        Ciphertext bytes.
    """
    ctx = _lib.EVP_CIPHER_CTX_new()
    if not ctx:
        raise RuntimeError("EVP_CIPHER_CTX_new failed")
    try:
        if _lib.EVP_EncryptInit_ex(ctx, _AES_128_ECB, None, key, None) != 1:
            raise RuntimeError("EVP_EncryptInit_ex failed")

        # PKCS7 padding is enabled by default in OpenSSL EVP.
        out_len = c_int(0)
        buf = create_string_buffer(len(data) + _BLOCK)  # max with padding

        if _lib.EVP_EncryptUpdate(ctx, buf, byref(out_len), data, len(data)) != 1:
            raise RuntimeError("EVP_EncryptUpdate failed")
        written = out_len.value

        final_buf = create_string_buffer(_BLOCK)
        if _lib.EVP_EncryptFinal_ex(ctx, final_buf, byref(out_len)) != 1:
            raise RuntimeError("EVP_EncryptFinal_ex failed")

        return buf.raw[:written] + final_buf.raw[: out_len.value]
    finally:
        _lib.EVP_CIPHER_CTX_free(ctx)


def aes128_ecb_decrypt(data: bytes, key: bytes) -> bytes:
    """Decrypt AES-128-ECB ciphertext and remove PKCS7 padding.

    Args:
        data: Ciphertext bytes (must be a multiple of 16).
        key: 16-byte AES key.

    Returns:
        Plaintext bytes.
    """
    ctx = _lib.EVP_CIPHER_CTX_new()
    if not ctx:
        raise RuntimeError("EVP_CIPHER_CTX_new failed")
    try:
        if _lib.EVP_DecryptInit_ex(ctx, _AES_128_ECB, None, key, None) != 1:
            raise RuntimeError("EVP_DecryptInit_ex failed")

        out_len = c_int(0)
        buf = create_string_buffer(len(data))

        if _lib.EVP_DecryptUpdate(ctx, buf, byref(out_len), data, len(data)) != 1:
            raise RuntimeError("EVP_DecryptUpdate failed")
        written = out_len.value

        final_buf = create_string_buffer(_BLOCK)
        if _lib.EVP_DecryptFinal_ex(ctx, final_buf, byref(out_len)) != 1:
            raise RuntimeError("EVP_DecryptFinal_ex failed")

        return buf.raw[:written] + final_buf.raw[: out_len.value]
    finally:
        _lib.EVP_CIPHER_CTX_free(ctx)
