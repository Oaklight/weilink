# Changelog

## Unreleased

- Fix `recv()` crash on Python 3.10 when multiple sessions are active (`concurrent.futures.TimeoutError` was not caught)
- OpenAPI server — expose bot tools as REST API endpoints via `weilink openapi` subcommand
- `get_updates()` now accepts a `timeout` parameter
- Unified CLI — single `weilink` command with `admin`, `mcp`, and `openapi` subcommands
- MCP multi-transport — support `stdio`, `sse`, and `streamable-http` transports
- Web admin panel — browser UI for session management, QR login, and status monitoring
- Docker deployment — container image with MCP SSE + admin panel, `docker-compose.yaml` included
- `--admin-port` flag on `weilink mcp` to run admin panel and MCP server in one process
- Startup banner with PyPI version check (`--no-banner` to suppress)
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
