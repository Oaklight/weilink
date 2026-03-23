"""Head-to-head comparison: vendored _aes.py vs pycryptodome.

This test ensures our pure-Python AES-128-ECB implementation produces
bit-identical results to pycryptodome across various inputs.
"""

from __future__ import annotations

import os

import pytest

from Crypto.Cipher import AES as PyCryptoAES

from weilink._aes import aes128_ecb_decrypt, aes128_ecb_encrypt


def _pycrypto_encrypt(data: bytes, key: bytes) -> bytes:
    """Encrypt with pycryptodome AES-128-ECB + PKCS7."""
    pad_len = 16 - (len(data) % 16)
    padded = data + bytes([pad_len] * pad_len)
    cipher = PyCryptoAES.new(key, PyCryptoAES.MODE_ECB)
    return cipher.encrypt(padded)


def _pycrypto_decrypt(data: bytes, key: bytes) -> bytes:
    """Decrypt with pycryptodome AES-128-ECB + PKCS7 unpad."""
    cipher = PyCryptoAES.new(key, PyCryptoAES.MODE_ECB)
    plaintext = cipher.decrypt(data)
    pad_len = plaintext[-1]
    if 1 <= pad_len <= 16 and plaintext[-pad_len:] == bytes([pad_len] * pad_len):
        plaintext = plaintext[:-pad_len]
    return plaintext


class TestAesH2H:
    """Head-to-head: _aes.py vs pycryptodome."""

    @pytest.mark.parametrize("size", [0, 1, 15, 16, 17, 31, 32, 100, 255, 1024])
    def test_encrypt_matches(self, size: int) -> None:
        """Vendored encrypt must produce identical ciphertext."""
        key = os.urandom(16)
        data = os.urandom(size)
        assert aes128_ecb_encrypt(data, key) == _pycrypto_encrypt(data, key)

    @pytest.mark.parametrize("size", [0, 1, 15, 16, 17, 31, 32, 100, 255, 1024])
    def test_decrypt_matches(self, size: int) -> None:
        """Vendored decrypt must produce identical plaintext."""
        key = os.urandom(16)
        data = os.urandom(size)
        ciphertext = _pycrypto_encrypt(data, key)
        assert aes128_ecb_decrypt(ciphertext, key) == data

    def test_cross_encrypt_decrypt(self) -> None:
        """Encrypt with one, decrypt with the other, both directions."""
        key = os.urandom(16)
        data = b"cross-compatibility test payload!"

        # vendored encrypt -> pycrypto decrypt
        ct_vendored = aes128_ecb_encrypt(data, key)
        assert _pycrypto_decrypt(ct_vendored, key) == data

        # pycrypto encrypt -> vendored decrypt
        ct_pycrypto = _pycrypto_encrypt(data, key)
        assert aes128_ecb_decrypt(ct_pycrypto, key) == data

    def test_large_random_data(self) -> None:
        """64KB random data, both directions."""
        key = os.urandom(16)
        data = os.urandom(65536)

        ct_v = aes128_ecb_encrypt(data, key)
        ct_p = _pycrypto_encrypt(data, key)
        assert ct_v == ct_p

        assert aes128_ecb_decrypt(ct_v, key) == data
        assert _pycrypto_decrypt(ct_v, key) == data

    def test_known_vector(self) -> None:
        """NIST AES-128 test vector (single block, no padding needed for raw block)."""
        # FIPS 197 Appendix B
        key = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
        plaintext = bytes.fromhex("3243f6a8885a308d313198a2e0370734")

        # For ECB with PKCS7, a full 16-byte block gets 16 bytes of padding appended,
        # so we test the first 16 bytes of ciphertext match the NIST expected output.
        expected_block = bytes.fromhex("3925841d02dc09fbdc118597196a0b32")

        ct_v = aes128_ecb_encrypt(plaintext, key)
        ct_p = _pycrypto_encrypt(plaintext, key)

        # Both should have 32 bytes (16 data + 16 padding)
        assert len(ct_v) == 32
        assert ct_v[:16] == expected_block
        assert ct_v == ct_p

    @pytest.mark.parametrize("_run", range(20))
    def test_random_stress(self, _run: int) -> None:
        """20 random key+data pairs, sizes 0-4096."""
        key = os.urandom(16)
        size = int.from_bytes(os.urandom(2), "big") % 4097
        data = os.urandom(size)

        ct_v = aes128_ecb_encrypt(data, key)
        ct_p = _pycrypto_encrypt(data, key)
        assert ct_v == ct_p, f"Mismatch at size={size}"

        assert aes128_ecb_decrypt(ct_v, key) == data
