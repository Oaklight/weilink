"""Tests for the _cdn module (AES encryption/decryption and helpers)."""

from __future__ import annotations

import pytest

try:
    from Crypto.Cipher import AES as _AES  # noqa: F401

    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

needs_crypto = pytest.mark.skipif(not HAS_CRYPTO, reason="pycryptodome not installed")


class TestDecodeAesKey:
    """Tests for _decode_aes_key."""

    def test_hex_key(self) -> None:
        from weilink._cdn import _decode_aes_key

        hex_key = "0123456789abcdef0123456789abcdef"
        result = _decode_aes_key(hex_key)
        assert result == bytes.fromhex(hex_key)
        assert len(result) == 16

    def test_base64_key(self) -> None:
        import base64

        from weilink._cdn import _decode_aes_key

        raw = b"\x00" * 16
        b64 = base64.b64encode(raw).decode()
        result = _decode_aes_key(b64)
        assert result == raw


class TestPkcs7:
    """Tests for PKCS7 padding/unpadding."""

    def test_pad_unpad_roundtrip(self) -> None:
        from weilink._cdn import _pkcs7_pad, _pkcs7_unpad

        data = b"hello world"
        padded = _pkcs7_pad(data)
        assert len(padded) % 16 == 0
        assert _pkcs7_unpad(padded) == data

    def test_pad_exact_block(self) -> None:
        from weilink._cdn import _pkcs7_pad, _pkcs7_unpad

        data = b"x" * 16
        padded = _pkcs7_pad(data)
        # Full block of padding added
        assert len(padded) == 32
        assert _pkcs7_unpad(padded) == data

    def test_unpad_empty(self) -> None:
        from weilink._cdn import _pkcs7_unpad

        assert _pkcs7_unpad(b"") == b""


class TestPaddedSize:
    """Tests for aes_ecb_padded_size."""

    def test_not_aligned(self) -> None:
        from weilink._cdn import aes_ecb_padded_size

        assert aes_ecb_padded_size(10) == 16

    def test_exact_block(self) -> None:
        from weilink._cdn import aes_ecb_padded_size

        # Exact block size gets a full padding block
        assert aes_ecb_padded_size(16) == 32

    def test_zero(self) -> None:
        from weilink._cdn import aes_ecb_padded_size

        assert aes_ecb_padded_size(0) == 16


@needs_crypto
class TestAesEncryptDecrypt:
    """Tests for AES-128-ECB encrypt/decrypt."""

    def test_roundtrip(self) -> None:
        from weilink._cdn import aes_ecb_decrypt, aes_ecb_encrypt

        key = b"\x42" * 16
        data = b"secret message for testing AES"
        encrypted = aes_ecb_encrypt(data, key)
        assert encrypted != data
        decrypted = aes_ecb_decrypt(encrypted, key)
        assert decrypted == data

    def test_large_data(self) -> None:
        import os

        from weilink._cdn import aes_ecb_decrypt, aes_ecb_encrypt

        key = os.urandom(16)
        data = os.urandom(1024)
        encrypted = aes_ecb_encrypt(data, key)
        decrypted = aes_ecb_decrypt(encrypted, key)
        assert decrypted == data


@needs_crypto
class TestUploadedMedia:
    """Tests for UploadedMedia dataclass."""

    def test_creation(self) -> None:
        from weilink._cdn import UploadedMedia

        um = UploadedMedia(
            filekey="abc123",
            download_param="param",
            aes_key_hex="0" * 32,
            file_size=100,
            cipher_size=112,
        )
        assert um.filekey == "abc123"
        assert um.file_size == 100
