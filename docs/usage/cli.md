# CLI Reference

The `weilink` command provides subcommands for bot interaction, server management, and credential migration:

```bash
# Bot commands
weilink login                                    # QR code login
weilink status                                   # Show session status
weilink recv --timeout 5                         # Receive messages
weilink send USER_ID --text "hello"              # Send a message
weilink download 42 -o ./media                   # Download media
weilink history --user USER_ID --limit 20        # Query message history
weilink sessions                                 # List sessions
weilink sessions rename old_name new_name        # Rename a session
weilink sessions default work                    # Set default session

# Server commands
weilink admin --host 0.0.0.0 -p 8080
weilink mcp -t sse --host 0.0.0.0 -p 8000 --admin-port 8080
weilink openapi --host 0.0.0.0 -p 8000

# Other commands
weilink migrate openclaw
```

All bot commands support `--json` for machine-readable output and `-d, --base-path` for custom data directories.

## Global Options

| Option | Description |
|--------|-------------|
| `-V, --version` | Show version and check for updates |

## Bot Commands

### `weilink login`

Login via QR code scan. Displays a QR code in the terminal for WeChat scanning.

```bash
weilink login                    # Login default session
weilink login work               # Login a named session
weilink login --force            # Force new login even if credentials exist
weilink login --json             # Output JSON result
```

| Option | Description | Default |
|--------|-------------|---------|
| `session_name` | Session name (positional, optional) | default session |
| `-f, --force` | Force new login even if credentials exist | *(off)* |
| `-d, --base-path` | Data directory | `~/.weilink/` |
| `--json` | Output machine-readable JSON | *(off)* |
| `--log-level` | Logging level | `INFO` |

### `weilink logout`

Log out a session and remove persisted credentials.

```bash
weilink logout                   # Logout default session
weilink logout work              # Logout a named session
```

| Option | Description | Default |
|--------|-------------|---------|
| `session_name` | Session name (positional, optional) | default session |
| `-d, --base-path` | Data directory | `~/.weilink/` |
| `--json` | Output machine-readable JSON | *(off)* |
| `--log-level` | Logging level | `INFO` |

### `weilink status`

Show session connection status.

```bash
weilink status                   # Human-readable status
weilink status --json            # JSON output
```

| Option | Description | Default |
|--------|-------------|---------|
| `-d, --base-path` | Data directory | `~/.weilink/` |
| `--json` | Output machine-readable JSON | *(off)* |
| `--log-level` | Logging level | `INFO` |

### `weilink recv`

Receive messages from all connected sessions.

```bash
weilink recv                     # Default 5s timeout
weilink recv --timeout 30        # Wait up to 30 seconds
weilink recv --json              # JSON output (for scripting)
```

| Option | Description | Default |
|--------|-------------|---------|
| `-t, --timeout` | Max wait time in seconds | `5` |
| `-d, --base-path` | Data directory | `~/.weilink/` |
| `--json` | Output machine-readable JSON | *(off)* |
| `--log-level` | Logging level | `INFO` |

### `weilink send`

Send a message to a user. At least one content option is required.

```bash
weilink send USER_ID --text "Hello!"
weilink send USER_ID --image ./photo.jpg
weilink send USER_ID --file ./doc.pdf --file-name "Report.pdf"
weilink send USER_ID --text "See attached" --image ./photo.jpg  # multimodal
```

| Option | Description | Default |
|--------|-------------|---------|
| `to` | Target user ID (positional, required) | — |
| `--text` | Text content | — |
| `--image` | Image file path | — |
| `--file` | File attachment path | — |
| `--file-name` | Display name for file | file's basename |
| `--video` | Video file path | — |
| `--voice` | Voice file path | — |
| `-d, --base-path` | Data directory | `~/.weilink/` |
| `--json` | Output machine-readable JSON | *(off)* |
| `--log-level` | Logging level | `INFO` |

### `weilink download`

Download media from a message by message ID. Requires message store (enabled by default).

```bash
weilink download 42                       # Save to ~/.weilink/downloads/
weilink download 42 -o ./media            # Save to custom directory
weilink download 42 --json                # Output path and size as JSON
```

| Option | Description | Default |
|--------|-------------|---------|
| `message_id` | Message ID (positional, required) | — |
| `-o, --output` | Output directory | `~/.weilink/downloads/` |
| `-d, --base-path` | Data directory | `~/.weilink/` |
| `--json` | Output machine-readable JSON | *(off)* |
| `--log-level` | Logging level | `INFO` |

### `weilink history`

Query message history from the SQLite store. Requires message store (enabled by default).

```bash
weilink history                                  # Recent 50 messages
weilink history --user USER_ID --limit 20        # Filter by user
weilink history --type IMAGE --direction received # Filter by type/direction
weilink history --since 2026-03-30 --text "hello" --json
```

| Option | Description | Default |
|--------|-------------|---------|
| `--user` | Filter by user ID | — |
| `--bot` | Filter by bot ID | — |
| `--type` | Filter by type: `TEXT`, `IMAGE`, `VOICE`, `FILE`, `VIDEO` | — |
| `--direction` | Filter: `received` or `sent` | — |
| `--since` | Start time (ISO 8601 or unix ms) | — |
| `--until` | End time (ISO 8601 or unix ms) | — |
| `--text` | Text substring search | — |
| `--limit` | Max results | `50` |
| `--offset` | Pagination offset | `0` |
| `-d, --base-path` | Data directory | `~/.weilink/` |
| `--json` | Output machine-readable JSON | *(off)* |
| `--log-level` | Logging level | `INFO` |

### `weilink sessions`

Session management: list, rename, and set default session.

```bash
weilink sessions                             # List all sessions
weilink sessions rename old_name new_name    # Rename a session
weilink sessions default work                # Set default session
```

#### `weilink sessions` (no subcommand)

Lists all sessions with their connection status, same as `weilink status`.

#### `weilink sessions rename`

| Option | Description |
|--------|-------------|
| `old_name` | Current session name (positional) |
| `new_name` | New session name (positional) |
| `--json` | Output machine-readable JSON |

#### `weilink sessions default`

| Option | Description |
|--------|-------------|
| `session_name` | Session name to set as default (positional) |
| `--json` | Output machine-readable JSON |

## Server Commands

### `weilink admin`

Start the web admin panel for session management and QR login.

| Option | Description | Default |
|--------|-------------|---------|
| `--host` | Host address to bind to | `127.0.0.1` |
| `-p, --port` | Port number | `8080` |
| `-d, --base-path` | Data directory (profile path) | `~/.weilink/` |
| `--log-level` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |
| `--no-banner` | Suppress the ASCII banner on startup | *(off)* |

### `weilink mcp`

Start the MCP server for AI agent integration. See [MCP Server](mcp.md) for details on transports and client configuration.

| Option | Description | Default |
|--------|-------------|---------|
| `-t, --transport` | MCP transport (`stdio`, `sse`, `streamable-http`, `http`) | `stdio` |
| `--host` | Host address for SSE/streamable-http | `127.0.0.1` |
| `-p, --port` | Port for SSE/streamable-http | `8000` |
| `-d, --base-path` | Data directory (profile path) | `~/.weilink/` |
| `--admin-port` | Also start admin panel on this port (same host) | *(disabled)* |
| `--log-level` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |
| `--no-banner` | Suppress the ASCII banner on startup | *(off)* |

!!! note
    `http` is an alias for `streamable-http`.

### `weilink openapi`

Start the OpenAPI (REST) server. See [OpenAPI Server](openapi.md) for endpoint details.

| Option | Description | Default |
|--------|-------------|---------|
| `--host` | Host address to bind to | `127.0.0.1` |
| `-p, --port` | Port number | `8000` |
| `-d, --base-path` | Data directory (profile path) | `~/.weilink/` |
| `--admin-port` | Also start admin panel on this port (same host) | *(disabled)* |
| `--log-level` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |
| `--no-banner` | Suppress the ASCII banner on startup | *(off)* |

## Other Commands

### `weilink migrate`

!!! warning "Experimental"
    This subcommand is experimental and its interface may change in future releases.

Import credentials from another iLink Bot tool so you can switch to WeiLink without re-scanning the QR code.

#### `weilink migrate openclaw`

Migrate sessions from the OpenClaw weixin plugin (`@tencent-weixin/openclaw-weixin`).

```bash
# Preview what will be migrated
weilink migrate openclaw --dry-run

# Run the migration (reads ~/.openclaw, writes to ~/.weilink/)
weilink migrate openclaw

# Custom paths
weilink migrate openclaw --source /path/to/openclaw --base-path /path/to/weilink
```

| Option | Description | Default |
|--------|-------------|---------|
| `--source` | OpenClaw state directory | `~/.openclaw` |
| `-d, --base-path` | WeiLink data directory | `~/.weilink/` |
| `--dry-run` | Show what would be migrated without writing files | *(off)* |

The migration converts each OpenClaw account into a named WeiLink session. Existing sessions are never overwritten — if a session with the same name already exists, it is skipped.

!!! tip
    After migrating, verify with `weilink status` or `weilink admin` that your sessions appear and are connected.

## `--json` Output

All bot commands support `--json` for machine-readable output. This is useful for scripting and integration with other tools:

```bash
# Get sessions as JSON
weilink status --json

# Receive messages as JSON
weilink recv --json | jq '.[] | .text'

# Send and check result
weilink send USER_ID --text "hello" --json | jq '.success'
```

On error, JSON output contains an `error` field:

```json
{"error": "Not connected"}
```

## Multiple Profiles

Run multiple instances with different profiles to manage separate bot accounts:

```bash
weilink admin -d ~/.weilink/personal -p 8080 &
weilink admin -d ~/.weilink/work     -p 8081 &
```

Each profile maintains its own `token.json` and session data independently.
