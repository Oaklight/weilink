"""Tests for the _cdn module (AES encryption/decryption and helpers)."""

from __future__ import annotations

import os


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


class TestPaddedSize:
    """Tests for aes_ecb_padded_size."""

    def test_not_aligned(self) -> None:
        from weilink._cdn import _aes_ecb_padded_size as aes_ecb_padded_size

        assert aes_ecb_padded_size(10) == 16

    def test_exact_block(self) -> None:
        from weilink._cdn import _aes_ecb_padded_size as aes_ecb_padded_size

        # Exact block size gets a full padding block
        assert aes_ecb_padded_size(16) == 32

    def test_zero(self) -> None:
        from weilink._cdn import _aes_ecb_padded_size as aes_ecb_padded_size

        assert aes_ecb_padded_size(0) == 16


class TestAesEncryptDecrypt:
    """Tests for AES-128-ECB encrypt/decrypt via the _crypto facade."""

    def test_roundtrip(self) -> None:
        from weilink._cdn import (
            aes_ecb_decrypt as aes128_ecb_decrypt,
            aes_ecb_encrypt as aes128_ecb_encrypt,
        )

        key = b"\x42" * 16
        data = b"secret message for testing AES"
        encrypted = aes128_ecb_encrypt(data, key)
        assert encrypted != data
        decrypted = aes128_ecb_decrypt(encrypted, key)
        assert decrypted == data

    def test_large_data(self) -> None:
        from weilink._cdn import (
            aes_ecb_decrypt as aes128_ecb_decrypt,
            aes_ecb_encrypt as aes128_ecb_encrypt,
        )

        key = os.urandom(16)
        data = os.urandom(1024)
        encrypted = aes128_ecb_encrypt(data, key)
        decrypted = aes128_ecb_decrypt(encrypted, key)
        assert decrypted == data


class TestUploadedMedia:
    """Tests for UploadedMedia dataclass."""

    def test_creation(self) -> None:
        from weilink.models import UploadedMedia, UploadMediaType

        um = UploadedMedia(
            media_type=UploadMediaType.IMAGE,
            filekey="abc123",
            download_param="param",
            aes_key_hex="0" * 32,
            file_size=100,
            cipher_size=112,
        )
        assert um.filekey == "abc123"
        assert um.file_size == 100
        assert um.media_type == UploadMediaType.IMAGE


class TestMediaInfoFullUrl:
    """Tests for MediaInfo.full_url field."""

    def test_default_empty(self) -> None:
        from weilink.models import MediaInfo

        mi = MediaInfo()
        assert mi.full_url == ""

    def test_with_full_url(self) -> None:
        from weilink.models import MediaInfo

        mi = MediaInfo(
            encrypt_query_param="param",
            aes_key="0" * 32,
            full_url="https://cdn.example.com/download?id=123",
        )
        assert mi.full_url == "https://cdn.example.com/download?id=123"
        assert mi.encrypt_query_param == "param"
