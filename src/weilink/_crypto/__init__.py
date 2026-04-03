"""AES-128-ECB crypto backend selection.

Prefers OpenSSL via ctypes for performance, falls back to the
vendored pure-Python implementation when libcrypto is unavailable.

Not part of the public API.
"""

from __future__ import annotations

_BLOCK = 16

try:
    from ._aes_openssl import aes128_ecb_decrypt, aes128_ecb_encrypt

    backend = "openssl"
except (ImportError, OSError):
    from ._aes import aes128_ecb_decrypt, aes128_ecb_encrypt

    backend = "python"


def aes_ecb_padded_size(plaintext_size: int) -> int:
    """Calculate the ciphertext size after AES-ECB + PKCS7 padding.

    Args:
        plaintext_size: Size of the original data.

    Returns:
        Size of the encrypted data.
    """
    pad_len = _BLOCK - (plaintext_size % _BLOCK)
    return plaintext_size + pad_len


__all__ = [
    "aes128_ecb_decrypt",
    "aes128_ecb_encrypt",
    "aes_ecb_padded_size",
    "backend",
]
