# Admin Panel

WeiLink includes a built-in web admin panel for managing bot sessions through a browser.

## Getting Started

```bash
pip install weilink[server]
weilink admin -p 8080
```

Open `http://localhost:8080` in your browser. For CLI options, see [CLI Reference](cli.md).

## Features

### Dashboard

The main page shows an overview of all sessions:

- Total sessions, connected count, and active users
- Connection status indicator

![Admin Panel Dashboard](../assets/admin_panel.png)

### Session Management

Each session row displays the session name, bot ID, connection status, and associated users. Available actions:

- **Logout** — Disconnect a session
- **Rename** — Change the session display name
- **Set Default** — Mark a session as the default for tools that don't specify a session name

### QR Code Login

Click **New Login** to start a QR code login flow:

1. Optionally enter a session name (or use the default)
2. Scan the QR code with WeChat
3. The session appears in the table once confirmed

QR codes expire after 5 minutes and can be refreshed manually.

### User Tracking

Expand a session row to see per-user details:

- First seen / last message received / last message sent timestamps
- Token status (active or expired after 24 hours of inactivity)

### Localization

The panel supports English and Chinese. It auto-detects your browser language, and you can switch manually via the language selector in the header.

## Running with Servers

The admin panel can run standalone or alongside an MCP / OpenAPI server:

```bash
# Standalone
weilink admin -p 8080

# With MCP server
weilink mcp -t sse -p 8000 --admin-port 8080

# With OpenAPI server
weilink openapi -p 8000 --admin-port 8080
```

When using `--admin-port`, the admin panel shares the same process and session state with the server.

## Docker

The default Docker image runs MCP SSE + admin panel together. See [Docker Deployment](docker.md) for details.
