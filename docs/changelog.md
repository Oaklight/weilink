# Changelog

## v0.3.0 (2026-03-25)

### New Features

- **Multi-session support** — register one bot with multiple WeChat accounts via `login(name="...")`; `recv()` polls all sessions concurrently, `send()` auto-routes to the correct session
- **CDN pre-upload API** — `upload()` uploads media to CDN without sending, returns reusable `UploadedMedia` reference
- **`send()` accepts `UploadedMedia`** for sending pre-uploaded media without re-uploading
- **`auto_recv` on `send()`** — refresh context tokens before sending; returns `SendResult` (bool-compatible) with any messages received during auto-recv; MCP server enables this by default
- **Quoted message support** — `Message.ref_msg` field exposes the referenced (quoted) message when a user replies to a previous message
- **OpenAPI server** — expose bot tools as REST API endpoints via `weilink openapi` subcommand
- **Web admin panel** — browser UI for session management, QR login, and status monitoring
- **MCP multi-transport** — support `stdio`, `sse`, and `streamable-http` transports
- **Docker deployment** — container image with MCP SSE + admin panel, `docker-compose.yaml` included
- **Unified CLI** — single `weilink` command with `admin`, `mcp`, and `openapi` subcommands
- `--admin-port` flag on `weilink mcp` to run admin panel and MCP server in one process
- Startup banner with PyPI version check (`--no-banner` to suppress)
- `get_updates()` now accepts a `timeout` parameter
- Add `MediaContent` type alias for cleaner media parameter annotations

### Bug Fixes

- Fix `recv()` crash on Python 3.10 when multiple sessions are active (`concurrent.futures.TimeoutError` was not caught)

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
