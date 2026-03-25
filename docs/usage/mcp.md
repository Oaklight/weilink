# MCP Server

WeiLink provides an optional [MCP](https://modelcontextprotocol.io/) (Model Context Protocol) server that exposes bot capabilities as tools for AI agents.

## Install

```bash
pip install weilink[mcp]
```

This installs [toolregistry-server](https://github.com/Oaklight/toolregistry) with MCP support alongside the core package.

!!! tip "MCP + OpenAPI"
    To install both MCP and OpenAPI server support in one go:

    ```bash
    pip install weilink[server]
    ```

    See [OpenAPI Server](openapi.md) for details on the REST API mode.

## Run

```bash
# CLI entry point
weilink-mcp

# Or via Python module
python -m weilink.mcp
```

The server uses **stdio** transport — it is launched by an MCP client (Claude Desktop, Cursor, etc.) rather than run standalone.

## Client Configuration

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "weilink": {
      "command": "weilink-mcp"
    }
  }
}
```

### Claude Code

```bash
claude mcp add weilink weilink-mcp
```

### Cursor / VS Code

Add to MCP settings:

```json
{
  "mcpServers": {
    "weilink": {
      "command": "python",
      "args": ["-m", "weilink.mcp"]
    }
  }
}
```

## Available Tools

### `recv_messages`

Poll for new messages from WeChat users.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `timeout` | float | 5.0 | Max wait time in seconds |

Returns a JSON array of messages. Each message includes `message_id`, `from_user`, `msg_type`, `text`, `timestamp`, `bot_id`, and media metadata if applicable.

### `send_message`

Send text and/or media to a WeChat user.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `to` | str | *(required)* | Target user ID |
| `text` | str | `""` | Text content |
| `image_path` | str | `""` | Local image file path |
| `file_path` | str | `""` | Local file path |
| `file_name` | str | `""` | Display name for the file |
| `video_path` | str | `""` | Local video file path |
| `voice_path` | str | `""` | Local voice file path |

### `download_media`

Download media from a previously received message.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `message_id` | str | *(required)* | Message ID from `recv_messages` |
| `save_dir` | str | `~/.weilink/downloads/` | Directory to save the file |

Returns the saved file path and size.

### `list_sessions`

List all sessions with their connection status. No parameters.

### `login` / `check_login`

Two-step login flow for QR code authentication:

1. Call `login(session_name="")` — returns a QR code URL for the user to scan.
2. Call `check_login()` repeatedly — returns the scan status (`pending`, `scanned`, `confirmed`, or `expired`).

!!! note "Pre-login recommended"
    The server auto-discovers existing sessions from `~/.weilink/` on startup. If you have already logged in via the SDK, the MCP server picks up your sessions automatically — no need to call the login tools.

## Architecture

```mermaid
graph LR
    A[AI Agent] -->|MCP protocol| B[weilink-mcp]
    B -->|WeiLink SDK| C[iLink API]
    C --> D[WeChat]
```

The MCP server wraps a `WeiLink` instance internally. Messages received via `recv_messages` are cached (up to 1000) so their media can be downloaded later via `download_media`.

## Skills Metadata

WeiLink ships two metadata files for registry discovery:

- **`server.json`** — [Official MCP standard](https://modelcontextprotocol.io/), used by MCP registries and package managers.
- **`smithery.yaml`** — [Smithery](https://smithery.ai/) registry format for auto-configuration.
