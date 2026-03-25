# Changelog

## v0.3.0 (2026-03-25)

### New Features

- **Multi-session support** ([`7dbb23d`](https://github.com/Oaklight/weilink/commit/7dbb23d)) — register one bot with multiple WeChat accounts via `login(name="...")`; `recv()` polls all sessions concurrently, `send()` auto-routes to the correct session
- **CDN pre-upload** ([`20f660e`](https://github.com/Oaklight/weilink/commit/20f660e)) — `upload()` pre-uploads media to CDN, returns reusable `UploadedMedia` reference; `send()` accepts it to avoid re-uploading
- **`auto_recv` on `send()`** ([#4](https://github.com/Oaklight/weilink/issues/4), [`c72099a`](https://github.com/Oaklight/weilink/commit/c72099a)) — optionally refresh context tokens before sending; returns `SendResult` (bool-compatible) carrying any messages received during the refresh
- **Quoted message support** ([#3](https://github.com/Oaklight/weilink/issues/3), [`c984f72`](https://github.com/Oaklight/weilink/commit/c984f72)) — `Message.ref_msg` exposes the referenced message when a user replies to a previous message
- **MCP server** ([`837997f`](https://github.com/Oaklight/weilink/commit/837997f)) — `stdio`, `sse`, and `streamable-http` transports; `--admin-port` flag to co-host admin panel
- **OpenAPI server** ([`e40c126`](https://github.com/Oaklight/weilink/commit/e40c126)) — expose bot tools as REST API endpoints via `weilink openapi`
- **Web admin panel** ([`c65a28a`](https://github.com/Oaklight/weilink/commit/c65a28a)) — browser UI for session management, QR login, and status monitoring
- **Docker deployment** ([`e1450dd`](https://github.com/Oaklight/weilink/commit/e1450dd)) — container image with MCP SSE + admin panel, `docker-compose.yaml` included
- **Unified CLI** ([`9a48774`](https://github.com/Oaklight/weilink/commit/9a48774)) — single `weilink` command with `admin`, `mcp`, and `openapi` subcommands

### Bug Fixes

- Fix `recv()` crash on Python 3.10 when multiple sessions are active ([`4625f34`](https://github.com/Oaklight/weilink/commit/4625f34))

## v0.2.0 (2026-03-24)

### New Features

- **Multimodal messaging** — send and receive images, voice, files, and videos
- **Proactive messaging** — context_tokens persist across restarts

### Bug Fixes

- Fix CDN upload reliability

## v0.1.0 (2026-03-23)

- Initial release
- QR code login with credential persistence
- Long-polling message receive
- Text message send with auto context_token management
- Typing indicator support
