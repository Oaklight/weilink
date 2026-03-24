# Changelog

## Unreleased

- **Breaking:** Unified `send()` API — removed `send_image()`, `send_voice()`, `send_file()`, `send_video()` in favor of a single `send(to, text, *, image, voice, file, video, file_name)` method
- `pycryptodome` is now a core dependency (no longer optional)
- Removed lazy-import `_require_crypto()`; AES is now imported directly
- Fix CDN upload failures: retry logic (max 3 attempts on 5xx), correct response header (`x-encrypted-param`), URL encoding matching JS `encodeURIComponent`
- Fix image decryption: prefer `image_item.aeskey` (raw hex) over `media.aes_key` (base64)
- Persist context_tokens across restarts for proactive messaging
- Add proactive messaging examples (`test_proactive_send.py`, `test_proactive_media.py`)
- Support `LOGLEVEL` env var in `media_echo.py` example

## v0.1.0 (2026-03-23)

- Initial release
- QR code login with credential persistence
- Long-polling message receive
- Text message send with auto context_token management
- Typing indicator support
