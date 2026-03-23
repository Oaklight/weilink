"""CDN media operations for iLink Bot protocol.

Handles AES-128-ECB encryption/decryption and CDN upload/download.
Requires pycryptodome for AES operations: pip install weilink[media]

Not part of the public API.
"""

from __future__ import annotations

import base64
import hashlib
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any
from collections.abc import Callable

import logging

CDN_BASE = "https://novac2c.cdn.weixin.qq.com/c2c"
AES_BLOCK_SIZE = 16

logger = logging.getLogger(__name__)


def _require_crypto() -> Any:
    """Lazy-import AES from pycryptodome.

    Returns:
        The Crypto.Cipher.AES module.

    Raises:
        ImportError: If pycryptodome is not installed.
    """
    try:
        from Crypto.Cipher import AES

        return AES
    except ImportError:
        raise ImportError(
            "Media support requires pycryptodome. "
            "Install it with: pip install weilink[media]"
        ) from None


def _decode_aes_key(aes_key: str) -> bytes:
    """Decode an AES key from hex or base64 format.

    Args:
        aes_key: Key string, either 32-char hex or base64 encoded.

    Returns:
        16-byte AES key.
    """
    if len(aes_key) == 32:
        try:
            return bytes.fromhex(aes_key)
        except ValueError:
            pass
    return base64.b64decode(aes_key)


def _pkcs7_pad(data: bytes) -> bytes:
    """Apply PKCS7 padding to data."""
    pad_len = AES_BLOCK_SIZE - (len(data) % AES_BLOCK_SIZE)
    return data + bytes([pad_len] * pad_len)


def _pkcs7_unpad(data: bytes) -> bytes:
    """Remove PKCS7 padding from data."""
    if not data:
        return data
    pad_len = data[-1]
    if pad_len < 1 or pad_len > AES_BLOCK_SIZE:
        return data
    if data[-pad_len:] != bytes([pad_len] * pad_len):
        return data
    return data[:-pad_len]


def aes_ecb_encrypt(data: bytes, key: bytes) -> bytes:
    """Encrypt data with AES-128-ECB and PKCS7 padding.

    Args:
        data: Plaintext bytes.
        key: 16-byte AES key.

    Returns:
        Ciphertext bytes.
    """
    AES = _require_crypto()
    cipher = AES.new(key, AES.MODE_ECB)
    return cipher.encrypt(_pkcs7_pad(data))


def aes_ecb_decrypt(data: bytes, key: bytes) -> bytes:
    """Decrypt AES-128-ECB ciphertext and remove PKCS7 padding.

    Args:
        data: Ciphertext bytes.
        key: 16-byte AES key.

    Returns:
        Plaintext bytes.
    """
    AES = _require_crypto()
    cipher = AES.new(key, AES.MODE_ECB)
    return _pkcs7_unpad(cipher.decrypt(data))


def aes_ecb_padded_size(plaintext_size: int) -> int:
    """Calculate the ciphertext size after AES-ECB + PKCS7 padding.

    Args:
        plaintext_size: Size of the original data.

    Returns:
        Size of the encrypted data.
    """
    pad_len = AES_BLOCK_SIZE - (plaintext_size % AES_BLOCK_SIZE)
    return plaintext_size + pad_len


def download_media(encrypt_query_param: str, aes_key: str) -> bytes:
    """Download and decrypt a media file from CDN.

    Args:
        encrypt_query_param: CDN download query parameter.
        aes_key: AES key string (hex or base64).

    Returns:
        Decrypted file bytes.

    Raises:
        ImportError: If pycryptodome is not installed.
        urllib.error.URLError: If the download fails.
    """
    key = _decode_aes_key(aes_key)

    url = f"{CDN_BASE}/download?encrypted_query_param={urllib.parse.quote(encrypt_query_param, safe='')}"
    req = urllib.request.Request(url, method="GET")

    with urllib.request.urlopen(req, timeout=60) as resp:
        encrypted = resp.read()

    return aes_ecb_decrypt(encrypted, key)


@dataclass
class UploadedMedia:
    """Result of a CDN media upload.

    Attributes:
        filekey: Random hex filekey used for this upload.
        download_param: CDN download parameter (x-encrypted-param header).
        aes_key_hex: Hex-encoded AES key used for encryption.
        file_size: Original plaintext file size.
        cipher_size: Encrypted file size.
    """

    filekey: str
    download_param: str
    aes_key_hex: str
    file_size: int
    cipher_size: int


def upload_media(
    file_data: bytes,
    media_type: int,
    to_user_id: str,
    get_upload_url_fn: Callable[..., dict[str, Any]],
) -> UploadedMedia:
    """Encrypt and upload a media file to CDN.

    Args:
        file_data: Raw file bytes.
        media_type: Upload media type (1=IMAGE, 2=VIDEO, 3=FILE, 4=VOICE).
        to_user_id: Target user ID.
        get_upload_url_fn: Callable that calls proto.get_upload_url().

    Returns:
        UploadedMedia with CDN reference info.

    Raises:
        ImportError: If pycryptodome is not installed.
    """
    # Generate random AES key and filekey
    aes_key = os.urandom(AES_BLOCK_SIZE)
    aes_key_hex = aes_key.hex()
    filekey = os.urandom(AES_BLOCK_SIZE).hex()

    # Compute file metadata
    file_md5 = hashlib.md5(file_data).hexdigest()
    file_size = len(file_data)
    cipher_size = aes_ecb_padded_size(file_size)

    # Get upload authorisation
    logger.debug(
        "getuploadurl: md5=%s size=%d cipher=%d type=%d to=%s filekey=%s",
        file_md5,
        file_size,
        cipher_size,
        media_type,
        to_user_id,
        filekey,
    )
    url_resp = get_upload_url_fn(
        file_md5=file_md5,
        file_size=file_size,
        cipher_size=cipher_size,
        media_type=media_type,
        to_user_id=to_user_id,
        filekey=filekey,
        aes_key_hex=aes_key_hex,
    )
    logger.debug("getuploadurl response: %s", url_resp)
    upload_param = url_resp.get("upload_param", "")
    if not upload_param:
        raise RuntimeError(f"No upload_param in response: {url_resp}")

    # Encrypt and upload to CDN
    encrypted = aes_ecb_encrypt(file_data, aes_key)

    upload_url = (
        f"{CDN_BASE}/upload"
        f"?encrypted_query_param={urllib.parse.quote(upload_param, safe='')}"
        f"&filekey={urllib.parse.quote(filekey, safe='')}"
    )
    logger.debug("CDN upload: url=%s ciphertext=%d bytes", upload_url, len(encrypted))
    req = urllib.request.Request(
        upload_url,
        data=encrypted,
        method="POST",
        headers={"Content-Type": "application/octet-stream"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            download_param = (
                resp.headers.get("x-encrypted-query-param")
                or resp.headers.get("x-encrypted-param")
                or ""
            )
    except urllib.error.HTTPError as e:
        # CDN may return 500 for preview errors while the upload itself
        # succeeded — the download param is still in the response headers.
        download_param = (
            e.headers.get("x-encrypted-query-param")
            or e.headers.get("x-encrypted-param")
            or ""
        )
        if download_param:
            logger.debug(
                "CDN upload returned %s but download_param present (%d chars), continuing",
                e.code,
                len(download_param),
            )
        else:
            body = e.read().decode(errors="replace")
            logger.error(
                "CDN upload failed: %s %s headers=%s body=%s",
                e.code,
                e.reason,
                dict(e.headers),
                body[:500],
            )
            raise

    return UploadedMedia(
        filekey=filekey,
        download_param=download_param,
        aes_key_hex=aes_key_hex,
        file_size=file_size,
        cipher_size=cipher_size,
    )
