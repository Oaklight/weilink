# CLI Reference

The `weilink` command provides three subcommands for different deployment scenarios:

```bash
# Admin panel only
weilink admin --host 0.0.0.0 -p 8080

# MCP server (stdio, for AI agents)
weilink mcp

# MCP server (SSE) + admin panel in one process
weilink mcp -t sse --host 0.0.0.0 -p 8000 --admin-port 8080

# OpenAPI server (REST API)
weilink openapi --host 0.0.0.0 -p 8000

# OpenAPI server + admin panel in one process
weilink openapi --host 0.0.0.0 -p 8000 --admin-port 8080
```

## Global Options

| Option | Description |
|--------|-------------|
| `-V, --version` | Show version and check for updates |

## `weilink admin`

Start the web admin panel for session management and QR login.

| Option | Description | Default |
|--------|-------------|---------|
| `--host` | Host address to bind to | `127.0.0.1` |
| `-p, --port` | Port number | `8080` |
| `-d, --base-path` | Data directory (profile path) | `~/.weilink/` |
| `--log-level` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |
| `--no-banner` | Suppress the ASCII banner on startup | *(off)* |

## `weilink mcp`

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

## `weilink openapi`

Start the OpenAPI (REST) server. See [OpenAPI Server](openapi.md) for endpoint details.

| Option | Description | Default |
|--------|-------------|---------|
| `--host` | Host address to bind to | `127.0.0.1` |
| `-p, --port` | Port number | `8000` |
| `-d, --base-path` | Data directory (profile path) | `~/.weilink/` |
| `--admin-port` | Also start admin panel on this port (same host) | *(disabled)* |
| `--log-level` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |
| `--no-banner` | Suppress the ASCII banner on startup | *(off)* |

## Multiple Profiles

Run multiple instances with different profiles to manage separate bot accounts:

```bash
weilink admin -d ~/.weilink/personal -p 8080 &
weilink admin -d ~/.weilink/work     -p 8081 &
```

Each profile maintains its own `token.json` and session data independently.
