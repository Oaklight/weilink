# /// zerodep
# version = "0.3.0"
# deps = []
# tier = "medium"
# category = "crypto"
# ///

"""AES encryption via OpenSSL libcrypto (ctypes): ECB, CBC, CTR, and GCM modes.

Part of zerodep: https://github.com/Oaklight/zerodep
Copyright (c) 2026 Peng Ding. MIT License.

Requires system OpenSSL (libcrypto) at runtime.
Provides the same interface as aes.py but delegates to the system
OpenSSL library for native-C performance.  Raises OSError at import
time if libcrypto cannot be located or loaded.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import sys
from ctypes import POINTER, byref, c_int, c_void_p, create_string_buffer

__all__ = [
    "aes_ecb_encrypt",
    "aes_ecb_decrypt",
    "aes_cbc_encrypt",
    "aes_cbc_decrypt",
    "aes_ctr_encrypt",
    "aes_ctr_decrypt",
    "aes_gcm_encrypt",
    "aes_gcm_decrypt",
    # Backward compatibility
    "aes128_ecb_encrypt",
    "aes128_ecb_decrypt",
]

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

_lib.EVP_CIPHER_CTX_set_padding.restype = c_int
_lib.EVP_CIPHER_CTX_set_padding.argtypes = [c_void_p, c_int]

_lib.EVP_CIPHER_CTX_ctrl.restype = c_int
_lib.EVP_CIPHER_CTX_ctrl.argtypes = [c_void_p, c_int, c_int, c_void_p]

for _fn_name in (
    "EVP_EncryptInit_ex",
    "EVP_DecryptInit_ex",
):
    _fn = getattr(_lib, _fn_name)
    _fn.restype = c_int
    _fn.argtypes = [c_void_p, c_void_p, c_void_p, ctypes.c_char_p, ctypes.c_char_p]

for _fn_name in (
    "EVP_EncryptUpdate",
    "EVP_DecryptUpdate",
):
    _fn = getattr(_lib, _fn_name)
    _fn.restype = c_int
    _fn.argtypes = [c_void_p, ctypes.c_char_p, POINTER(c_int), ctypes.c_char_p, c_int]

for _fn_name in (
    "EVP_EncryptFinal_ex",
    "EVP_DecryptFinal_ex",
):
    _fn = getattr(_lib, _fn_name)
    _fn.restype = c_int
    _fn.argtypes = [c_void_p, ctypes.c_char_p, POINTER(c_int)]

# Cipher descriptor functions
for _fn_name in (
    "EVP_aes_128_ecb",
    "EVP_aes_192_ecb",
    "EVP_aes_256_ecb",
    "EVP_aes_128_cbc",
    "EVP_aes_192_cbc",
    "EVP_aes_256_cbc",
    "EVP_aes_128_ctr",
    "EVP_aes_192_ctr",
    "EVP_aes_256_ctr",
    "EVP_aes_128_gcm",
    "EVP_aes_192_gcm",
    "EVP_aes_256_gcm",
):
    _fn = getattr(_lib, _fn_name)
    _fn.restype = c_void_p
    _fn.argtypes = []

# Cipher lookup: (key_length, mode) -> cipher descriptor
_CIPHER_MAP: dict[tuple[int, str], int] = {
    (16, "ecb"): _lib.EVP_aes_128_ecb(),
    (24, "ecb"): _lib.EVP_aes_192_ecb(),
    (32, "ecb"): _lib.EVP_aes_256_ecb(),
    (16, "cbc"): _lib.EVP_aes_128_cbc(),
    (24, "cbc"): _lib.EVP_aes_192_cbc(),
    (32, "cbc"): _lib.EVP_aes_256_cbc(),
    (16, "ctr"): _lib.EVP_aes_128_ctr(),
    (24, "ctr"): _lib.EVP_aes_192_ctr(),
    (32, "ctr"): _lib.EVP_aes_256_ctr(),
    (16, "gcm"): _lib.EVP_aes_128_gcm(),
    (24, "gcm"): _lib.EVP_aes_192_gcm(),
    (32, "gcm"): _lib.EVP_aes_256_gcm(),
}

# GCM ctrl constants
_EVP_CTRL_GCM_SET_IVLEN = 0x9
_EVP_CTRL_GCM_GET_TAG = 0x10
_EVP_CTRL_GCM_SET_TAG = 0x11

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BLOCK = 16


def _validate_key(key: bytes) -> None:
    if len(key) not in (16, 24, 32):
        raise ValueError(f"key must be 16, 24, or 32 bytes, got {len(key)}")


def _validate_iv(iv: bytes) -> None:
    if len(iv) != _BLOCK:
        raise ValueError(f"IV must be {_BLOCK} bytes, got {len(iv)}")


# ---------------------------------------------------------------------------
# Generic EVP encrypt / decrypt (for ECB, CBC, CTR)
# ---------------------------------------------------------------------------


def _evp_encrypt(
    data: bytes, key: bytes, mode: str, iv: bytes | None = None, *, padding: bool = True
) -> bytes:
    cipher = _CIPHER_MAP[(len(key), mode)]
    ctx = _lib.EVP_CIPHER_CTX_new()
    if not ctx:
        raise RuntimeError("EVP_CIPHER_CTX_new failed")
    try:
        iv_arg = iv if iv is not None else None
        if _lib.EVP_EncryptInit_ex(ctx, cipher, None, key, iv_arg) != 1:
            raise RuntimeError("EVP_EncryptInit_ex failed")

        if not padding:
            _lib.EVP_CIPHER_CTX_set_padding(ctx, 0)

        out_len = c_int(0)
        buf = create_string_buffer(len(data) + _BLOCK)

        if _lib.EVP_EncryptUpdate(ctx, buf, byref(out_len), data, len(data)) != 1:
            raise RuntimeError("EVP_EncryptUpdate failed")
        written = out_len.value

        final_buf = create_string_buffer(_BLOCK)
        if _lib.EVP_EncryptFinal_ex(ctx, final_buf, byref(out_len)) != 1:
            raise RuntimeError("EVP_EncryptFinal_ex failed")

        return buf.raw[:written] + final_buf.raw[: out_len.value]
    finally:
        _lib.EVP_CIPHER_CTX_free(ctx)


def _evp_decrypt(
    data: bytes, key: bytes, mode: str, iv: bytes | None = None, *, padding: bool = True
) -> bytes:
    cipher = _CIPHER_MAP[(len(key), mode)]
    ctx = _lib.EVP_CIPHER_CTX_new()
    if not ctx:
        raise RuntimeError("EVP_CIPHER_CTX_new failed")
    try:
        iv_arg = iv if iv is not None else None
        if _lib.EVP_DecryptInit_ex(ctx, cipher, None, key, iv_arg) != 1:
            raise RuntimeError("EVP_DecryptInit_ex failed")

        if not padding:
            _lib.EVP_CIPHER_CTX_set_padding(ctx, 0)

        out_len = c_int(0)
        buf = create_string_buffer(len(data) + _BLOCK)

        if _lib.EVP_DecryptUpdate(ctx, buf, byref(out_len), data, len(data)) != 1:
            raise RuntimeError("EVP_DecryptUpdate failed")
        written = out_len.value

        final_buf = create_string_buffer(_BLOCK)
        if _lib.EVP_DecryptFinal_ex(ctx, final_buf, byref(out_len)) != 1:
            raise RuntimeError("EVP_DecryptFinal_ex failed")

        return buf.raw[:written] + final_buf.raw[: out_len.value]
    finally:
        _lib.EVP_CIPHER_CTX_free(ctx)


# ---------------------------------------------------------------------------
# ECB mode + PKCS7 padding
# ---------------------------------------------------------------------------


def aes_ecb_encrypt(data: bytes, key: bytes) -> bytes:
    """Encrypt data with AES-ECB and PKCS7 padding.

    Args:
        data: Plaintext bytes.
        key: 16, 24, or 32-byte AES key.

    Returns:
        Ciphertext bytes (length is a multiple of 16).
    """
    _validate_key(key)
    return _evp_encrypt(data, key, "ecb")


def aes_ecb_decrypt(data: bytes, key: bytes) -> bytes:
    """Decrypt AES-ECB ciphertext and remove PKCS7 padding.

    Args:
        data: Ciphertext bytes (must be a multiple of 16).
        key: 16, 24, or 32-byte AES key.

    Returns:
        Plaintext bytes.

    Raises:
        RuntimeError: If padding is invalid.
    """
    _validate_key(key)
    return _evp_decrypt(data, key, "ecb")


# Backward compatibility
aes128_ecb_encrypt = aes_ecb_encrypt
aes128_ecb_decrypt = aes_ecb_decrypt


# ---------------------------------------------------------------------------
# CBC mode + PKCS7 padding
# ---------------------------------------------------------------------------


def aes_cbc_encrypt(data: bytes, key: bytes, iv: bytes) -> bytes:
    """Encrypt data with AES-CBC and PKCS7 padding.

    Args:
        data: Plaintext bytes.
        key: 16, 24, or 32-byte AES key.
        iv: 16-byte initialization vector.

    Returns:
        Ciphertext bytes (length is a multiple of 16).
    """
    _validate_key(key)
    _validate_iv(iv)
    return _evp_encrypt(data, key, "cbc", iv)


def aes_cbc_decrypt(data: bytes, key: bytes, iv: bytes) -> bytes:
    """Decrypt AES-CBC ciphertext and remove PKCS7 padding.

    Args:
        data: Ciphertext bytes (must be a multiple of 16).
        key: 16, 24, or 32-byte AES key.
        iv: 16-byte initialization vector.

    Returns:
        Plaintext bytes.

    Raises:
        RuntimeError: If padding is invalid.
    """
    _validate_key(key)
    _validate_iv(iv)
    return _evp_decrypt(data, key, "cbc", iv)


# ---------------------------------------------------------------------------
# CTR mode (no padding)
# ---------------------------------------------------------------------------


def aes_ctr_encrypt(data: bytes, key: bytes, nonce: bytes) -> bytes:
    """Encrypt data with AES-CTR (no padding).

    Args:
        data: Plaintext bytes (any length).
        key: 16, 24, or 32-byte AES key.
        nonce: 16-byte initial counter block.

    Returns:
        Ciphertext bytes (same length as input).
    """
    _validate_key(key)
    if len(nonce) != _BLOCK:
        raise ValueError(f"nonce must be {_BLOCK} bytes, got {len(nonce)}")
    return _evp_encrypt(data, key, "ctr", nonce, padding=False)


aes_ctr_decrypt = aes_ctr_encrypt


# ---------------------------------------------------------------------------
# GCM mode (authenticated encryption)
# ---------------------------------------------------------------------------


def aes_gcm_encrypt(
    data: bytes,
    key: bytes,
    nonce: bytes,
    aad: bytes = b"",
    tag_length: int = 16,
) -> tuple[bytes, bytes]:
    """Encrypt data with AES-GCM (authenticated encryption).

    Args:
        data: Plaintext bytes.
        key: 16, 24, or 32-byte AES key.
        nonce: Nonce bytes (12 bytes recommended).
        aad: Additional authenticated data.
        tag_length: Authentication tag length in bytes (4-16).

    Returns:
        Tuple of (ciphertext, authentication_tag).
    """
    _validate_key(key)
    if not nonce:
        raise ValueError("nonce must not be empty")
    if not (4 <= tag_length <= 16):
        raise ValueError(f"tag_length must be 4-16, got {tag_length}")

    cipher = _CIPHER_MAP[(len(key), "gcm")]
    ctx = _lib.EVP_CIPHER_CTX_new()
    if not ctx:
        raise RuntimeError("EVP_CIPHER_CTX_new failed")
    try:
        # Phase 1: set cipher (key=NULL, iv=NULL)
        if _lib.EVP_EncryptInit_ex(ctx, cipher, None, None, None) != 1:
            raise RuntimeError("EVP_EncryptInit_ex failed (cipher)")

        # Set IV length if not 12 bytes
        if len(nonce) != 12:
            if (
                _lib.EVP_CIPHER_CTX_ctrl(ctx, _EVP_CTRL_GCM_SET_IVLEN, len(nonce), None)
                != 1
            ):
                raise RuntimeError("EVP_CIPHER_CTX_ctrl SET_IVLEN failed")

        # Phase 2: set key and IV
        if _lib.EVP_EncryptInit_ex(ctx, None, None, key, nonce) != 1:
            raise RuntimeError("EVP_EncryptInit_ex failed (key/iv)")

        out_len = c_int(0)

        # Pass AAD (output pointer is not used for AAD)
        if aad:
            if _lib.EVP_EncryptUpdate(ctx, None, byref(out_len), aad, len(aad)) != 1:
                raise RuntimeError("EVP_EncryptUpdate AAD failed")

        # Encrypt plaintext
        buf = create_string_buffer(len(data) + _BLOCK)
        if _lib.EVP_EncryptUpdate(ctx, buf, byref(out_len), data, len(data)) != 1:
            raise RuntimeError("EVP_EncryptUpdate failed")
        written = out_len.value

        # Finalize
        final_buf = create_string_buffer(_BLOCK)
        if _lib.EVP_EncryptFinal_ex(ctx, final_buf, byref(out_len)) != 1:
            raise RuntimeError("EVP_EncryptFinal_ex failed")
        written += out_len.value

        # Get authentication tag
        tag_buf = create_string_buffer(tag_length)
        if (
            _lib.EVP_CIPHER_CTX_ctrl(ctx, _EVP_CTRL_GCM_GET_TAG, tag_length, tag_buf)
            != 1
        ):
            raise RuntimeError("EVP_CIPHER_CTX_ctrl GET_TAG failed")

        return buf.raw[:written], tag_buf.raw[:tag_length]
    finally:
        _lib.EVP_CIPHER_CTX_free(ctx)


def aes_gcm_decrypt(
    data: bytes,
    key: bytes,
    nonce: bytes,
    tag: bytes,
    aad: bytes = b"",
) -> bytes:
    """Decrypt AES-GCM ciphertext and verify authentication tag.

    Args:
        data: Ciphertext bytes.
        key: 16, 24, or 32-byte AES key.
        nonce: Nonce bytes (must match the one used for encryption).
        tag: Authentication tag to verify.
        aad: Additional authenticated data.

    Returns:
        Plaintext bytes.

    Raises:
        ValueError: If authentication fails (tag mismatch).
    """
    _validate_key(key)
    if not nonce:
        raise ValueError("nonce must not be empty")
    tag_length = len(tag)
    if not (4 <= tag_length <= 16):
        raise ValueError(f"tag must be 4-16 bytes, got {tag_length}")

    cipher = _CIPHER_MAP[(len(key), "gcm")]
    ctx = _lib.EVP_CIPHER_CTX_new()
    if not ctx:
        raise RuntimeError("EVP_CIPHER_CTX_new failed")
    try:
        # Phase 1: set cipher
        if _lib.EVP_DecryptInit_ex(ctx, cipher, None, None, None) != 1:
            raise RuntimeError("EVP_DecryptInit_ex failed (cipher)")

        # Set IV length if not 12 bytes
        if len(nonce) != 12:
            if (
                _lib.EVP_CIPHER_CTX_ctrl(ctx, _EVP_CTRL_GCM_SET_IVLEN, len(nonce), None)
                != 1
            ):
                raise RuntimeError("EVP_CIPHER_CTX_ctrl SET_IVLEN failed")

        # Phase 2: set key and IV
        if _lib.EVP_DecryptInit_ex(ctx, None, None, key, nonce) != 1:
            raise RuntimeError("EVP_DecryptInit_ex failed (key/iv)")

        out_len = c_int(0)

        # Pass AAD
        if aad:
            if _lib.EVP_DecryptUpdate(ctx, None, byref(out_len), aad, len(aad)) != 1:
                raise RuntimeError("EVP_DecryptUpdate AAD failed")

        # Decrypt ciphertext
        buf = create_string_buffer(len(data) + _BLOCK)
        if _lib.EVP_DecryptUpdate(ctx, buf, byref(out_len), data, len(data)) != 1:
            raise RuntimeError("EVP_DecryptUpdate failed")
        written = out_len.value

        # Set expected tag before finalization
        tag_buf = create_string_buffer(tag, tag_length)
        if (
            _lib.EVP_CIPHER_CTX_ctrl(ctx, _EVP_CTRL_GCM_SET_TAG, tag_length, tag_buf)
            != 1
        ):
            raise RuntimeError("EVP_CIPHER_CTX_ctrl SET_TAG failed")

        # Finalize -- returns 0 if tag verification fails
        final_buf = create_string_buffer(_BLOCK)
        if _lib.EVP_DecryptFinal_ex(ctx, final_buf, byref(out_len)) != 1:
            raise ValueError("authentication failed")
        written += out_len.value

        return buf.raw[:written]
    finally:
        _lib.EVP_CIPHER_CTX_free(ctx)
