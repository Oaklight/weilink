# Docker Deployment

The WeiLink Docker image bundles both the **MCP server** (for AI agent integration) and the **admin panel** (web UI for session management) in a single container.

## Unified CLI

The `weilink` command provides two subcommands:

```bash
# Admin panel only
weilink admin --host 0.0.0.0 -p 8080

# MCP server (stdio, for AI agents)
weilink mcp

# MCP server (SSE) + admin panel in one process
weilink mcp -t sse --host 0.0.0.0 -p 8000 --admin-port 8080 -d /data/weilink
```

### `weilink admin` Options

| Option | Description | Default |
|--------|-------------|---------|
| `--host` | Host address to bind to | `127.0.0.1` |
| `-p, --port` | Port number | `8080` |
| `-d, --base-path` | Data directory (profile path) | `~/.weilink/` |
| `--log-level` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |

### `weilink mcp` Options

| Option | Description | Default |
|--------|-------------|---------|
| `-t, --transport` | MCP transport (`stdio`, `sse`, `streamable-http`) | `stdio` |
| `--host` | Host address for SSE/streamable-http | `127.0.0.1` |
| `-p, --port` | Port for SSE/streamable-http | `8000` |
| `-d, --base-path` | Data directory (profile path) | `~/.weilink/` |
| `--admin-port` | Also start admin panel on this port (same host) | *(disabled)* |
| `--log-level` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |

### Multiple Profiles

Run multiple instances with different profiles to manage separate bot accounts:

```bash
weilink admin -d ~/.weilink/personal -p 8080 &
weilink admin -d ~/.weilink/work     -p 8081 &
```

Each profile maintains its own `token.json` and session data independently.

## Docker

### Quick Start

```bash
docker run -p 8000:8000 -p 8080:8080 -v weilink-data:/data/weilink oaklight/weilink
```

This starts both the MCP SSE server on port 8000 and the admin panel on port 8080. Open `http://localhost:8080` in your browser to manage sessions.

### Admin Panel Only

To run only the admin panel without the MCP server:

```bash
docker run -p 8080:8080 -v weilink-data:/data/weilink oaklight/weilink \
    weilink admin --host 0.0.0.0 -p 8080 -d /data/weilink
```

### Multiple Profiles with Docker

Use different Docker volumes to isolate profiles:

```bash
# Personal bot
docker run -d --name weilink-personal \
    -p 8000:8000 -p 8080:8080 \
    -v weilink-personal:/data/weilink \
    oaklight/weilink

# Work bot
docker run -d --name weilink-work \
    -p 8001:8000 -p 8081:8080 \
    -v weilink-work:/data/weilink \
    oaklight/weilink
```

### Docker Compose

```yaml
services:
  weilink:
    image: oaklight/weilink
    ports:
      - "8000:8000"  # MCP SSE
      - "8080:8080"  # Admin panel
    volumes:
      - weilink-data:/data/weilink
    restart: unless-stopped

volumes:
  weilink-data:
```

For multiple profiles:

```yaml
services:
  bot-personal:
    image: oaklight/weilink
    ports:
      - "8000:8000"
      - "8080:8080"
    volumes:
      - personal-data:/data/weilink
    restart: unless-stopped

  bot-work:
    image: oaklight/weilink
    ports:
      - "8001:8000"
      - "8081:8080"
    volumes:
      - work-data:/data/weilink
    restart: unless-stopped

volumes:
  personal-data:
  work-data:
```

### Building the Image

```bash
make build-docker

# With PyPI mirror
make build-docker PYPI_MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple

# With registry mirror
make build-docker REGISTRY_MIRROR=docker.1ms.run
```

### Data Persistence

Session tokens and context data are stored in `/data/weilink` inside the container. **Always mount a volume** to this path to persist data across container restarts — otherwise you'll need to re-scan the QR code each time.
