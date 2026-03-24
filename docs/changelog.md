# Changelog

## v0.2.0 (2026-03-24)

- Add multimodal message support — `send()` now accepts `image`, `voice`, `file`, `video` parameters (single or batch via list)
- Add media download — `download()` retrieves received image/voice/file/video content
- Add `pycryptodome` as core dependency for AES-128-ECB media encryption
- Persist context_tokens across restarts for proactive messaging
- Fix CDN upload: retry on 5xx, correct response header, URL encoding aligned with JS `encodeURIComponent`
- Fix image decryption key selection
- Add examples: `media_echo.py`, `test_proactive_send.py`, `test_proactive_media.py`

## v0.1.0 (2026-03-23)

- Initial release
- QR code login with credential persistence
- Long-polling message receive
- Text message send with auto context_token management
- Typing indicator support
