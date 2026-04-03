"""Head-to-head comparison: pure-Python AES vs OpenSSL ctypes backend.

Ensures both backends produce bit-identical results across various inputs.
"""

from __future__ import annotations

import os

import pytest

from weilink._crypto._aes import aes128_ecb_decrypt as py_decrypt
from weilink._crypto._aes import aes128_ecb_encrypt as py_encrypt

try:
    from weilink._crypto._aes_openssl import aes128_ecb_decrypt as ossl_decrypt
    from weilink._crypto._aes_openssl import aes128_ecb_encrypt as ossl_encrypt

    HAS_OPENSSL = True
except (ImportError, OSError):
    HAS_OPENSSL = False

needs_openssl = pytest.mark.skipif(not HAS_OPENSSL, reason="libcrypto not available")


class TestKnownVectors:
    """NIST / deterministic tests — always run (pure Python)."""

    def test_nist_aes128(self) -> None:
        """NIST FIPS 197 Appendix B test vector."""
        key = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
        plaintext = bytes.fromhex("3243f6a8885a308d313198a2e0370734")
        expected_block = bytes.fromhex("3925841d02dc09fbdc118597196a0b32")

        ct = py_encrypt(plaintext, key)
        assert len(ct) == 32  # 16 data + 16 PKCS7 padding
        assert ct[:16] == expected_block

    @needs_openssl
    def test_nist_aes128_openssl(self) -> None:
        """Same NIST vector via OpenSSL backend."""
        key = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
        plaintext = bytes.fromhex("3243f6a8885a308d313198a2e0370734")
        expected_block = bytes.fromhex("3925841d02dc09fbdc118597196a0b32")

        ct = ossl_encrypt(plaintext, key)
        assert len(ct) == 32
        assert ct[:16] == expected_block


class TestPythonRoundtrip:
    """Pure-Python backend roundtrip — always run."""

    @pytest.mark.parametrize("size", [0, 1, 15, 16, 17, 31, 32, 100, 255, 1024])
    def test_roundtrip(self, size: int) -> None:
        key = os.urandom(16)
        data = os.urandom(size)
        assert py_decrypt(py_encrypt(data, key), key) == data


@needs_openssl
class TestH2H:
    """Head-to-head: pure Python vs OpenSSL."""

    @pytest.mark.parametrize("size", [0, 1, 15, 16, 17, 31, 32, 100, 255, 1024])
    def test_encrypt_matches(self, size: int) -> None:
        """Both backends must produce identical ciphertext."""
        key = os.urandom(16)
        data = os.urandom(size)
        assert py_encrypt(data, key) == ossl_encrypt(data, key)

    @pytest.mark.parametrize("size", [0, 1, 15, 16, 17, 31, 32, 100, 255, 1024])
    def test_decrypt_matches(self, size: int) -> None:
        """Both backends must produce identical plaintext."""
        key = os.urandom(16)
        data = os.urandom(size)
        ct = ossl_encrypt(data, key)
        assert py_decrypt(ct, key) == data

    def test_cross_encrypt_decrypt(self) -> None:
        """Encrypt with one, decrypt with the other, both directions."""
        key = os.urandom(16)
        data = b"cross-compatibility test payload!"

        ct_py = py_encrypt(data, key)
        assert ossl_decrypt(ct_py, key) == data

        ct_ossl = ossl_encrypt(data, key)
        assert py_decrypt(ct_ossl, key) == data

    def test_large_random_data(self) -> None:
        """64KB random data, both directions."""
        key = os.urandom(16)
        data = os.urandom(65536)

        ct_py = py_encrypt(data, key)
        ct_ossl = ossl_encrypt(data, key)
        assert ct_py == ct_ossl

        assert py_decrypt(ct_ossl, key) == data
        assert ossl_decrypt(ct_py, key) == data

    @pytest.mark.parametrize("_run", range(20))
    def test_random_stress(self, _run: int) -> None:
        """20 random key+data pairs, sizes 0-4096."""
        key = os.urandom(16)
        size = int.from_bytes(os.urandom(2), "big") % 4097
        data = os.urandom(size)

        ct_py = py_encrypt(data, key)
        ct_ossl = ossl_encrypt(data, key)
        assert ct_py == ct_ossl, f"Mismatch at size={size}"

        assert ossl_decrypt(ct_py, key) == data
