# Changelog

## v0.3.0b2 (2026-03-25)

- Multi-session support — register one bot with multiple WeChat accounts via `login(name="...")`; `recv()` polls all sessions concurrently, `send()` auto-routes to the correct session
- CDN pre-upload API — `upload()` uploads media to CDN without sending, returns reusable `UploadedMedia` reference
- `send()` now accepts `UploadedMedia` for sending pre-uploaded media without re-uploading
- Add `MediaContent` type alias for cleaner media parameter annotations

## v0.2.0 (2026-03-24)

- Multimodal messaging — send and receive images, voice, files, and videos
- Proactive messaging — context_tokens persist across restarts
- Fix CDN upload reliability

## v0.1.0 (2026-03-23)

- Initial release
- QR code login with credential persistence
- Long-polling message receive
- Text message send with auto context_token management
- Typing indicator support
