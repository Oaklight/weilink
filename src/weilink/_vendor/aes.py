# /// zerodep
# version = "0.3.0"
# deps = []
# tier = "medium"
# category = "crypto"
# ///

"""Pure-Python AES encryption: ECB, CBC, CTR, and GCM modes for 128/192/256-bit keys.

Part of zerodep: https://github.com/Oaklight/zerodep
Copyright (c) 2026 Peng Ding. MIT License.

Based on bozhu/AES-Python (MIT License):
    Copyright (C) 2012 Bo Zhu http://about.bozhu.me
    https://github.com/bozhu/AES-Python
"""

from __future__ import annotations

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

# fmt: off
_SBOX = (
    0x63, 0x7C, 0x77, 0x7B, 0xF2, 0x6B, 0x6F, 0xC5, 0x30, 0x01, 0x67, 0x2B, 0xFE, 0xD7, 0xAB, 0x76,
    0xCA, 0x82, 0xC9, 0x7D, 0xFA, 0x59, 0x47, 0xF0, 0xAD, 0xD4, 0xA2, 0xAF, 0x9C, 0xA4, 0x72, 0xC0,
    0xB7, 0xFD, 0x93, 0x26, 0x36, 0x3F, 0xF7, 0xCC, 0x34, 0xA5, 0xE5, 0xF1, 0x71, 0xD8, 0x31, 0x15,
    0x04, 0xC7, 0x23, 0xC3, 0x18, 0x96, 0x05, 0x9A, 0x07, 0x12, 0x80, 0xE2, 0xEB, 0x27, 0xB2, 0x75,
    0x09, 0x83, 0x2C, 0x1A, 0x1B, 0x6E, 0x5A, 0xA0, 0x52, 0x3B, 0xD6, 0xB3, 0x29, 0xE3, 0x2F, 0x84,
    0x53, 0xD1, 0x00, 0xED, 0x20, 0xFC, 0xB1, 0x5B, 0x6A, 0xCB, 0xBE, 0x39, 0x4A, 0x4C, 0x58, 0xCF,
    0xD0, 0xEF, 0xAA, 0xFB, 0x43, 0x4D, 0x33, 0x85, 0x45, 0xF9, 0x02, 0x7F, 0x50, 0x3C, 0x9F, 0xA8,
    0x51, 0xA3, 0x40, 0x8F, 0x92, 0x9D, 0x38, 0xF5, 0xBC, 0xB6, 0xDA, 0x21, 0x10, 0xFF, 0xF3, 0xD2,
    0xCD, 0x0C, 0x13, 0xEC, 0x5F, 0x97, 0x44, 0x17, 0xC4, 0xA7, 0x7E, 0x3D, 0x64, 0x5D, 0x19, 0x73,
    0x60, 0x81, 0x4F, 0xDC, 0x22, 0x2A, 0x90, 0x88, 0x46, 0xEE, 0xB8, 0x14, 0xDE, 0x5E, 0x0B, 0xDB,
    0xE0, 0x32, 0x3A, 0x0A, 0x49, 0x06, 0x24, 0x5C, 0xC2, 0xD3, 0xAC, 0x62, 0x91, 0x95, 0xE4, 0x79,
    0xE7, 0xC8, 0x37, 0x6D, 0x8D, 0xD5, 0x4E, 0xA9, 0x6C, 0x56, 0xF4, 0xEA, 0x65, 0x7A, 0xAE, 0x08,
    0xBA, 0x78, 0x25, 0x2E, 0x1C, 0xA6, 0xB4, 0xC6, 0xE8, 0xDD, 0x74, 0x1F, 0x4B, 0xBD, 0x8B, 0x8A,
    0x70, 0x3E, 0xB5, 0x66, 0x48, 0x03, 0xF6, 0x0E, 0x61, 0x35, 0x57, 0xB9, 0x86, 0xC1, 0x1D, 0x9E,
    0xE1, 0xF8, 0x98, 0x11, 0x69, 0xD9, 0x8E, 0x94, 0x9B, 0x1E, 0x87, 0xE9, 0xCE, 0x55, 0x28, 0xDF,
    0x8C, 0xA1, 0x89, 0x0D, 0xBF, 0xE6, 0x42, 0x68, 0x41, 0x99, 0x2D, 0x0F, 0xB0, 0x54, 0xBB, 0x16,
)

_INV_SBOX = (
    0x52, 0x09, 0x6A, 0xD5, 0x30, 0x36, 0xA5, 0x38, 0xBF, 0x40, 0xA3, 0x9E, 0x81, 0xF3, 0xD7, 0xFB,
    0x7C, 0xE3, 0x39, 0x82, 0x9B, 0x2F, 0xFF, 0x87, 0x34, 0x8E, 0x43, 0x44, 0xC4, 0xDE, 0xE9, 0xCB,
    0x54, 0x7B, 0x94, 0x32, 0xA6, 0xC2, 0x23, 0x3D, 0xEE, 0x4C, 0x95, 0x0B, 0x42, 0xFA, 0xC3, 0x4E,
    0x08, 0x2E, 0xA1, 0x66, 0x28, 0xD9, 0x24, 0xB2, 0x76, 0x5B, 0xA2, 0x49, 0x6D, 0x8B, 0xD1, 0x25,
    0x72, 0xF8, 0xF6, 0x64, 0x86, 0x68, 0x98, 0x16, 0xD4, 0xA4, 0x5C, 0xCC, 0x5D, 0x65, 0xB6, 0x92,
    0x6C, 0x70, 0x48, 0x50, 0xFD, 0xED, 0xB9, 0xDA, 0x5E, 0x15, 0x46, 0x57, 0xA7, 0x8D, 0x9D, 0x84,
    0x90, 0xD8, 0xAB, 0x00, 0x8C, 0xBC, 0xD3, 0x0A, 0xF7, 0xE4, 0x58, 0x05, 0xB8, 0xB3, 0x45, 0x06,
    0xD0, 0x2C, 0x1E, 0x8F, 0xCA, 0x3F, 0x0F, 0x02, 0xC1, 0xAF, 0xBD, 0x03, 0x01, 0x13, 0x8A, 0x6B,
    0x3A, 0x91, 0x11, 0x41, 0x4F, 0x67, 0xDC, 0xEA, 0x97, 0xF2, 0xCF, 0xCE, 0xF0, 0xB4, 0xE6, 0x73,
    0x96, 0xAC, 0x74, 0x22, 0xE7, 0xAD, 0x35, 0x85, 0xE2, 0xF9, 0x37, 0xE8, 0x1C, 0x75, 0xDF, 0x6E,
    0x47, 0xF1, 0x1A, 0x71, 0x1D, 0x29, 0xC5, 0x89, 0x6F, 0xB7, 0x62, 0x0E, 0xAA, 0x18, 0xBE, 0x1B,
    0xFC, 0x56, 0x3E, 0x4B, 0xC6, 0xD2, 0x79, 0x20, 0x9A, 0xDB, 0xC0, 0xFE, 0x78, 0xCD, 0x5A, 0xF4,
    0x1F, 0xDD, 0xA8, 0x33, 0x88, 0x07, 0xC7, 0x31, 0xB1, 0x12, 0x10, 0x59, 0x27, 0x80, 0xEC, 0x5F,
    0x60, 0x51, 0x7F, 0xA9, 0x19, 0xB5, 0x4A, 0x0D, 0x2D, 0xE5, 0x7A, 0x9F, 0x93, 0xC9, 0x9C, 0xEF,
    0xA0, 0xE0, 0x3B, 0x4D, 0xAE, 0x2A, 0xF5, 0xB0, 0xC8, 0xEB, 0xBB, 0x3C, 0x83, 0x53, 0x99, 0x61,
    0x17, 0x2B, 0x04, 0x7E, 0xBA, 0x77, 0xD6, 0x26, 0xE1, 0x69, 0x14, 0x63, 0x55, 0x21, 0x0C, 0x7D,
)

_RCON = (
    0x00, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40,
    0x80, 0x1B, 0x36, 0x6C, 0xD8, 0xAB, 0x4D, 0x9A,
    0x2F, 0x5E, 0xBC, 0x63, 0xC6, 0x97, 0x35, 0x6A,
    0xD4, 0xB3, 0x7D, 0xFA, 0xEF, 0xC5, 0x91, 0x39,
)
# fmt: on

_BLOCK = 16
_KEY_PARAMS = {16: (4, 10), 24: (6, 12), 32: (8, 14)}  # key_len -> (nk, nr)


# ── Helpers ────────────────────────────────────────────────────────────────


def _validate_key(key: bytes) -> None:
    if len(key) not in _KEY_PARAMS:
        raise ValueError(f"key must be 16, 24, or 32 bytes, got {len(key)}")


def _validate_iv(iv: bytes) -> None:
    if len(iv) != _BLOCK:
        raise ValueError(f"IV must be {_BLOCK} bytes, got {len(iv)}")


def _pkcs7_pad(data: bytes) -> bytes:
    pad_len = _BLOCK - (len(data) % _BLOCK)
    return data + bytes([pad_len] * pad_len)


def _pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        return data
    pad_len = data[-1]
    if not (1 <= pad_len <= _BLOCK):
        raise ValueError("invalid PKCS7 padding")
    if data[-pad_len:] != bytes([pad_len] * pad_len):
        raise ValueError("invalid PKCS7 padding")
    return data[:-pad_len]


def _xtime(a: int) -> int:
    return ((a << 1) ^ 0x1B) & 0xFF if (a & 0x80) else (a << 1)


def _bytes_to_matrix(b: bytes) -> list[list[int]]:
    return [list(b[i : i + 4]) for i in range(0, 16, 4)]


def _matrix_to_bytes(m: list[list[int]]) -> bytes:
    return bytes(b for row in m for b in row)


# ── Key Expansion (AES-128/192/256) ────────────────────────────────────────


def _expand_key(key: bytes) -> list[list[list[int]]]:
    nk, nr = _KEY_PARAMS[len(key)]
    total_words = 4 * (nr + 1)

    rk: list[list[int]] = [list(key[i : i + 4]) for i in range(0, len(key), 4)]

    for i in range(nk, total_words):
        prev = rk[i - 1]
        if i % nk == 0:
            # RotWord + SubWord + Rcon
            row = [
                rk[i - nk][0] ^ _SBOX[prev[1]] ^ _RCON[i // nk],
                rk[i - nk][1] ^ _SBOX[prev[2]],
                rk[i - nk][2] ^ _SBOX[prev[3]],
                rk[i - nk][3] ^ _SBOX[prev[0]],
            ]
        elif nk > 6 and i % nk == 4:
            # AES-256 special case: SubWord only
            row = [rk[i - nk][j] ^ _SBOX[prev[j]] for j in range(4)]
        else:
            row = [rk[i - nk][j] ^ prev[j] for j in range(4)]
        rk.append(row)

    return [rk[4 * r : 4 * (r + 1)] for r in range(nr + 1)]


# ── AES Round Transformations ──────────────────────────────────────────────


def _add_round_key(s: list[list[int]], k: list[list[int]]) -> None:
    for i in range(4):
        for j in range(4):
            s[i][j] ^= k[i][j]


def _sub_bytes(s: list[list[int]]) -> None:
    for i in range(4):
        for j in range(4):
            s[i][j] = _SBOX[s[i][j]]


def _inv_sub_bytes(s: list[list[int]]) -> None:
    for i in range(4):
        for j in range(4):
            s[i][j] = _INV_SBOX[s[i][j]]


def _shift_rows(s: list[list[int]]) -> None:
    s[0][1], s[1][1], s[2][1], s[3][1] = s[1][1], s[2][1], s[3][1], s[0][1]
    s[0][2], s[1][2], s[2][2], s[3][2] = s[2][2], s[3][2], s[0][2], s[1][2]
    s[0][3], s[1][3], s[2][3], s[3][3] = s[3][3], s[0][3], s[1][3], s[2][3]


def _inv_shift_rows(s: list[list[int]]) -> None:
    s[0][1], s[1][1], s[2][1], s[3][1] = s[3][1], s[0][1], s[1][1], s[2][1]
    s[0][2], s[1][2], s[2][2], s[3][2] = s[2][2], s[3][2], s[0][2], s[1][2]
    s[0][3], s[1][3], s[2][3], s[3][3] = s[1][3], s[2][3], s[3][3], s[0][3]


def _mix_single_column(a: list[int]) -> None:
    t = a[0] ^ a[1] ^ a[2] ^ a[3]
    u = a[0]
    a[0] ^= t ^ _xtime(a[0] ^ a[1])
    a[1] ^= t ^ _xtime(a[1] ^ a[2])
    a[2] ^= t ^ _xtime(a[2] ^ a[3])
    a[3] ^= t ^ _xtime(a[3] ^ u)


def _mix_columns(s: list[list[int]]) -> None:
    for i in range(4):
        _mix_single_column(s[i])


def _inv_mix_columns(s: list[list[int]]) -> None:
    for i in range(4):
        u = _xtime(_xtime(s[i][0] ^ s[i][2]))
        v = _xtime(_xtime(s[i][1] ^ s[i][3]))
        s[i][0] ^= u
        s[i][1] ^= v
        s[i][2] ^= u
        s[i][3] ^= v
    _mix_columns(s)


# ── Block Encrypt / Decrypt (any key size) ─────────────────────────────────


def _encrypt_block(block: bytes, round_keys: list[list[list[int]]]) -> bytes:
    nr = len(round_keys) - 1
    s = _bytes_to_matrix(block)
    _add_round_key(s, round_keys[0])
    for i in range(1, nr):
        _sub_bytes(s)
        _shift_rows(s)
        _mix_columns(s)
        _add_round_key(s, round_keys[i])
    _sub_bytes(s)
    _shift_rows(s)
    _add_round_key(s, round_keys[nr])
    return _matrix_to_bytes(s)


def _decrypt_block(block: bytes, round_keys: list[list[list[int]]]) -> bytes:
    nr = len(round_keys) - 1
    s = _bytes_to_matrix(block)
    _add_round_key(s, round_keys[nr])
    _inv_shift_rows(s)
    _inv_sub_bytes(s)
    for i in range(nr - 1, 0, -1):
        _add_round_key(s, round_keys[i])
        _inv_mix_columns(s)
        _inv_shift_rows(s)
        _inv_sub_bytes(s)
    _add_round_key(s, round_keys[0])
    return _matrix_to_bytes(s)


# ── ECB Mode + PKCS7 Padding ───────────────────────────────────────────────


def aes_ecb_encrypt(data: bytes, key: bytes) -> bytes:
    """Encrypt data with AES-ECB and PKCS7 padding.

    Args:
        data: Plaintext bytes.
        key: 16, 24, or 32-byte AES key.

    Returns:
        Ciphertext bytes (length is a multiple of 16).
    """
    _validate_key(key)
    padded = _pkcs7_pad(data)
    rk = _expand_key(key)
    out = bytearray()
    for i in range(0, len(padded), _BLOCK):
        out.extend(_encrypt_block(padded[i : i + _BLOCK], rk))
    return bytes(out)


def aes_ecb_decrypt(data: bytes, key: bytes) -> bytes:
    """Decrypt AES-ECB ciphertext and remove PKCS7 padding.

    Args:
        data: Ciphertext bytes (must be a multiple of 16).
        key: 16, 24, or 32-byte AES key.

    Returns:
        Plaintext bytes.

    Raises:
        ValueError: If padding is invalid.
    """
    _validate_key(key)
    rk = _expand_key(key)
    out = bytearray()
    for i in range(0, len(data), _BLOCK):
        out.extend(_decrypt_block(data[i : i + _BLOCK], rk))
    return _pkcs7_unpad(bytes(out))


# Backward compatibility
aes128_ecb_encrypt = aes_ecb_encrypt
aes128_ecb_decrypt = aes_ecb_decrypt


# ── CBC Mode + PKCS7 Padding ───────────────────────────────────────────────


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
    padded = _pkcs7_pad(data)
    rk = _expand_key(key)
    out = bytearray()
    prev = iv
    for i in range(0, len(padded), _BLOCK):
        block = padded[i : i + _BLOCK]
        xored = bytes(a ^ b for a, b in zip(block, prev))
        encrypted = _encrypt_block(xored, rk)
        out.extend(encrypted)
        prev = encrypted
    return bytes(out)


def aes_cbc_decrypt(data: bytes, key: bytes, iv: bytes) -> bytes:
    """Decrypt AES-CBC ciphertext and remove PKCS7 padding.

    Args:
        data: Ciphertext bytes (must be a multiple of 16).
        key: 16, 24, or 32-byte AES key.
        iv: 16-byte initialization vector.

    Returns:
        Plaintext bytes.

    Raises:
        ValueError: If padding is invalid.
    """
    _validate_key(key)
    _validate_iv(iv)
    rk = _expand_key(key)
    out = bytearray()
    prev = iv
    for i in range(0, len(data), _BLOCK):
        block = data[i : i + _BLOCK]
        decrypted = _decrypt_block(block, rk)
        out.extend(a ^ b for a, b in zip(decrypted, prev))
        prev = block
    return _pkcs7_unpad(bytes(out))


# ── CTR Mode (no padding) ──────────────────────────────────────────────────


def _inc_counter(counter: bytes) -> bytes:
    """Increment a 16-byte counter block as a 128-bit big-endian integer."""
    val = int.from_bytes(counter, "big") + 1
    return (val & ((1 << 128) - 1)).to_bytes(16, "big")


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
    rk = _expand_key(key)
    out = bytearray()
    ctr = nonce
    for i in range(0, len(data), _BLOCK):
        keystream = _encrypt_block(ctr, rk)
        chunk = data[i : i + _BLOCK]
        out.extend(b ^ k for b, k in zip(chunk, keystream))
        ctr = _inc_counter(ctr)
    return bytes(out)


aes_ctr_decrypt = aes_ctr_encrypt


# ── GCM Mode (authenticated encryption) ────────────────────────────────────

_GF128_R = 0xE1000000000000000000000000000000


def _gf128_mul(x: int, y: int) -> int:
    """Multiply two elements in GF(2^128) with NIST bit ordering."""
    z = 0
    v = x
    for i in range(127, -1, -1):
        if (y >> i) & 1:
            z ^= v
        carry = v & 1
        v >>= 1
        if carry:
            v ^= _GF128_R
    return z


def _ghash(h: int, aad: bytes, ciphertext: bytes) -> int:
    """Compute GHASH per NIST SP 800-38D."""

    def _process(data: bytes, tag: int) -> int:
        # Pad data to block boundary
        padded = data
        remainder = len(data) % _BLOCK
        if remainder:
            padded = data + b"\x00" * (_BLOCK - remainder)
        for i in range(0, len(padded), _BLOCK):
            block = int.from_bytes(padded[i : i + _BLOCK], "big")
            tag = _gf128_mul(tag ^ block, h)
        return tag

    tag = _process(aad, 0)
    tag = _process(ciphertext, tag)
    # Length block: len(A) || len(C) in bits, each 64-bit big-endian
    lengths = (len(aad) * 8).to_bytes(8, "big") + (len(ciphertext) * 8).to_bytes(
        8, "big"
    )
    tag ^= int.from_bytes(lengths, "big")
    tag = _gf128_mul(tag, h)
    return tag


def _inc32(block: bytes) -> bytes:
    """Increment the last 32 bits of a 16-byte block (GCM counter)."""
    ctr = int.from_bytes(block[12:], "big")
    ctr = (ctr + 1) & 0xFFFFFFFF
    return block[:12] + ctr.to_bytes(4, "big")


def _gcm_j0(rk: list[list[list[int]]], nonce: bytes) -> bytes:
    """Compute initial counter block J0 per NIST SP 800-38D."""
    if len(nonce) == 12:
        return nonce + b"\x00\x00\x00\x01"
    h_block = _encrypt_block(b"\x00" * _BLOCK, rk)
    h = int.from_bytes(h_block, "big")
    padded = nonce
    remainder = len(nonce) % _BLOCK
    if remainder:
        padded = nonce + b"\x00" * (_BLOCK - remainder)
    padded += b"\x00" * 8 + (len(nonce) * 8).to_bytes(8, "big")
    j0_int = 0
    for i in range(0, len(padded), _BLOCK):
        block = int.from_bytes(padded[i : i + _BLOCK], "big")
        j0_int = _gf128_mul(j0_int ^ block, h)
    return j0_int.to_bytes(16, "big")


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

    rk = _expand_key(key)
    h_block = _encrypt_block(b"\x00" * _BLOCK, rk)
    h = int.from_bytes(h_block, "big")

    j0 = _gcm_j0(rk, nonce)

    # GCTR: encrypt data with counter starting at inc32(J0)
    ctr = _inc32(j0)
    ct = bytearray()
    for i in range(0, len(data), _BLOCK):
        keystream = _encrypt_block(ctr, rk)
        chunk = data[i : i + _BLOCK]
        ct.extend(b ^ k for b, k in zip(chunk, keystream))
        ctr = _inc32(ctr)
    ct = bytes(ct)

    # Compute authentication tag
    tag_int = _ghash(h, aad, ct)
    e_j0 = _encrypt_block(j0, rk)
    tag_int ^= int.from_bytes(e_j0, "big")
    tag = tag_int.to_bytes(16, "big")[:tag_length]

    return ct, tag


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

    rk = _expand_key(key)
    h_block = _encrypt_block(b"\x00" * _BLOCK, rk)
    h = int.from_bytes(h_block, "big")

    j0 = _gcm_j0(rk, nonce)

    # Verify authentication tag before decrypting
    expected_int = _ghash(h, aad, data)
    e_j0 = _encrypt_block(j0, rk)
    expected_int ^= int.from_bytes(e_j0, "big")
    expected_tag = expected_int.to_bytes(16, "big")[:tag_length]

    if expected_tag != tag:
        raise ValueError("authentication failed")

    # GCTR: decrypt data
    ctr = _inc32(j0)
    pt = bytearray()
    for i in range(0, len(data), _BLOCK):
        keystream = _encrypt_block(ctr, rk)
        chunk = data[i : i + _BLOCK]
        pt.extend(b ^ k for b, k in zip(chunk, keystream))
        ctr = _inc32(ctr)

    return bytes(pt)
