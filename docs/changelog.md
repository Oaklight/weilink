# Changelog

## Unreleased

### Breaking Changes

- **Rename server tools to match SDK** ([#6](https://github.com/Oaklight/weilink/issues/6)) — `recv_messages` → `recv`, `send_message` → `send`, `download_media` → `download`, `get_message_history` → `history`, `list_sessions` → `sessions`; tool names now mirror the SDK method names for consistency across all three API layers
- **Merge `login` + `check_login` into single `login` tool** — the `login` tool is now stateful: first call starts a QR flow, subsequent calls poll with a configurable timeout (default 30s) until status changes; `check_login` has been removed

### New Features

- **SQLite message persistence** — new `MessageStore` (`_store.py`) backed by SQLite WAL mode stores all received and sent messages to `messages.db`; enables message history queries, prevents message loss across restarts, and provides a `download` fallback after server restart; opt-in via `WeiLink(message_store=True)`, enabled by default in MCP/OpenAPI server mode
- **`history` server tool** — query past messages by user, bot, type, direction, time range, or text content; supports pagination with `limit`/`offset`
- **`logout` server tool** — log out a session and remove persisted credentials
- **`rename_session` server tool** — rename a session
- **`set_default` server tool** — set a session as the default
- **Route C cooperative polling** — when `message_store` is enabled and the poll lock is held by another process, `recv()` reads recent messages from SQLite instead of returning an empty list; enables multi-client access without a central server
- **CLI bot commands** — new subcommands `login`, `logout`, `status`, `recv`, `send`, `download`, `history`, and `sessions` (with `rename`/`default` sub-subcommands); all commands support `--json` for machine-readable output and `-d, --base-path` for custom data directories
- **Atomic file writes** — `token.json`, `contexts.json`, and `.default_session` are now written via temp-file + `os.replace()` to prevent corruption on crash

## v0.4.3 (2026-03-30)

### Bug Fixes

- **Fix admin panel login not saving `user_id`** — `_handle_poll_login` now extracts `ilink_user_id` from the QR confirmation response and stores it in `BotInfo`, matching the SDK `login()` behaviour
- **Consolidate admin panel User ID display** — replaced the redundant "Users" column with a unified "User ID" column showing the bot owner's WeChat user ID and active/expired badge; added `user_id` field to the `/api/sessions` response

### Improvements

- **Add debug logging to protocol layer** — `_protocol.py` now logs all HTTP requests/responses, `get_updates` message counts, cursor changes, and error details at DEBUG/INFO level for easier troubleshooting
- **Add debug logging to MCP `recv`** — `server/app.py` logs polling start, message counts, and individual message details
- **Add Docker entrypoint with PUID/PGID support** — new `entrypoint.sh` fixes `/data/weilink` ownership at runtime via `su-exec`, allowing bind-mounted volumes to match host user permissions

## v0.4.2 (2026-03-28)

### New Features

- **Cross-process profile locking** ([#5](https://github.com/Oaklight/weilink/issues/5)) — multiple WeiLink instances sharing the same data directory (`~/.weilink/`) are now coordinated via `fcntl.flock()`-based file locks; a non-blocking **poll lock** (`.poll.lock`) ensures only one process polls iLink at a time, while a short-lived **data lock** (`.data.lock`) serializes read-modify-write cycles on `token.json` / `contexts.json`; prevents cursor divergence, send_count corruption, and file corruption across SDK scripts, stdio MCP, and admin panel processes

## v0.4.1 (2026-03-27)

### Bug Fixes

- **Fix session rename leaving stale directory** — add per-session `_io_lock` to serialize file I/O operations (rename, save, load, logout) on `_Session`; rename now uses `shutil.rmtree` instead of `rmdir` to force-clean the old directory; prevents race condition where a background thread could recreate the old directory between file move and path update

## v0.4.0 (2026-03-27)

### Breaking Changes

- **Rename `weilink.mcp` module to `weilink.server`** — internal server module moved from `weilink.mcp.server` to `weilink.server.app`; use `python -m weilink.server` instead of `python -m weilink.mcp`; CLI subcommands (`weilink mcp`, `weilink openapi`, `weilink admin`) and install extras (`weilink[mcp]`, `weilink[server]`) are unchanged

### New Features

- **Credential migration CLI** *(experimental)* — `weilink migrate openclaw` imports sessions from the OpenClaw weixin plugin (`@tencent-weixin/openclaw-weixin`) without re-scanning the QR code; supports `--dry-run` and `--source` to customize the OpenClaw state directory
- **Send quota tracking** ([`58de18b`](https://github.com/Oaklight/weilink/commit/58de18b)) — SDK tracks per-user send count against the 10-message context_token quota; raises `QuotaExhaustedError` when exhausted; `SendResult.remaining` shows the countdown
- **`TextTooLongError`** ([`58de18b`](https://github.com/Oaklight/weilink/commit/58de18b)) — `send()` raises `TextTooLongError` with actual byte length when text exceeds the 16 KiB UTF-8 limit, instead of silently splitting
- **`BotInfo.user_id`** ([`3772776`](https://github.com/Oaklight/weilink/commit/3772776)) — login now captures the WeChat user ID that authorized the bot; accessible via `Session.user_id`
- **Additional model fields** ([`a2759bc`](https://github.com/Oaklight/weilink/commit/a2759bc)) — `ImageInfo.hd_size`, `VoiceInfo.encode_type` / `bits_per_sample` / `sample_rate`
- **Session expiry recovery** ([`b44181b`](https://github.com/Oaklight/weilink/commit/b44181b)) — automatically clears cursor and context tokens on `errcode: -14`, so re-login can start fresh
- **Recv robustness** ([`c000f8a`](https://github.com/Oaklight/weilink/commit/c000f8a), [`ddcb0f0`](https://github.com/Oaklight/weilink/commit/ddcb0f0)) — retry backoff on consecutive `recv()` failures; honors server-provided `longpolling_timeout_ms`

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
