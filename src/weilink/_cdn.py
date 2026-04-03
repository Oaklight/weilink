"""CDN media operations for iLink Bot protocol.

Handles AES-128-ECB encryption/decryption and CDN upload/download.

Not part of the public API.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from weilink.models import UploadMediaType, UploadedMedia

# AES backend: prefer OpenSSL for performance, fall back to pure Python.
try:
    from weilink._vendor.aes_openssl import aes_ecb_decrypt, aes_ecb_encrypt
except (ImportError, OSError):
    from weilink._vendor.aes import aes_ecb_decrypt, aes_ecb_encrypt

_BLOCK = 16


def _aes_ecb_padded_size(plaintext_size: int) -> int:
    """Calculate the ciphertext size after AES-ECB + PKCS7 padding."""
    return plaintext_size + (_BLOCK - plaintext_size % _BLOCK)


CDN_BASE = "https://novac2c.cdn.weixin.qq.com/c2c"
UPLOAD_MAX_RETRIES = 3
# Match JS encodeURIComponent: unreserved chars that should NOT be percent-encoded
_URI_SAFE = "-_.!~*'()"

logger = logging.getLogger(__name__)


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


def download_media(encrypt_query_param: str, aes_key: str) -> bytes:
    """Download and decrypt a media file from CDN.

    Args:
        encrypt_query_param: CDN download query parameter.
        aes_key: AES key string (hex or base64).

    Returns:
        Decrypted file bytes.

    Raises:
        urllib.error.URLError: If the download fails.
    """
    key = _decode_aes_key(aes_key)

    url = f"{CDN_BASE}/download?encrypted_query_param={urllib.parse.quote(encrypt_query_param, safe=_URI_SAFE)}"
    req = urllib.request.Request(url, method="GET")

    with urllib.request.urlopen(req, timeout=60) as resp:
        encrypted = resp.read()

    return aes_ecb_decrypt(encrypted, key)


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

    """
    # Generate random AES key and filekey
    aes_key = os.urandom(16)
    aes_key_hex = aes_key.hex()
    filekey = os.urandom(16).hex()

    # Compute file metadata
    file_md5 = hashlib.md5(file_data).hexdigest()
    file_size = len(file_data)
    cipher_size = _aes_ecb_padded_size(file_size)

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
        f"?encrypted_query_param={urllib.parse.quote(upload_param, safe=_URI_SAFE)}"
        f"&filekey={urllib.parse.quote(filekey, safe=_URI_SAFE)}"
    )
    logger.debug("CDN upload: url=%s ciphertext=%d bytes", upload_url, len(encrypted))
    req = urllib.request.Request(
        upload_url,
        data=encrypted,
        method="POST",
        headers={"Content-Type": "application/octet-stream"},
    )

    download_param: str | None = None
    last_error: Exception | None = None

    for attempt in range(1, UPLOAD_MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                download_param = resp.headers.get("x-encrypted-param") or None
            if not download_param:
                raise RuntimeError("CDN response missing x-encrypted-param header")
            logger.debug("CDN upload success attempt=%d", attempt)
            break
        except urllib.error.HTTPError as e:
            err_msg = e.headers.get("x-error-message") or f"status {e.code}"
            if 400 <= e.code < 500:
                logger.error(
                    "CDN upload client error attempt=%d status=%d msg=%s",
                    attempt,
                    e.code,
                    err_msg,
                )
                raise
            logger.error(
                "CDN upload server error attempt=%d status=%d msg=%s",
                attempt,
                e.code,
                err_msg,
            )
            last_error = e
        except Exception as e:
            logger.error("CDN upload error attempt=%d: %s", attempt, e)
            last_error = e

        if attempt < UPLOAD_MAX_RETRIES:
            logger.debug(
                "Retrying CDN upload (%d/%d)...", attempt + 1, UPLOAD_MAX_RETRIES
            )

    if not download_param:
        raise last_error or RuntimeError(
            f"CDN upload failed after {UPLOAD_MAX_RETRIES} attempts"
        )

    return UploadedMedia(
        media_type=UploadMediaType(media_type),
        filekey=filekey,
        download_param=download_param,
        aes_key_hex=aes_key_hex,
        file_size=file_size,
        cipher_size=cipher_size,
    )
