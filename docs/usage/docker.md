# Docker Deployment

The WeiLink Docker image bundles the **MCP / OpenAPI servers** (for AI agents and other LLM tools to integrate with) and the **admin panel** (web UI for session management) in a single container. For CLI usage outside Docker, see [CLI Reference](cli.md).

## Quick Start

```bash
docker run -p 8000:8000 -p 8080:8080 -v weilink-data:/data/weilink oaklight/weilink
```

This starts both the MCP SSE server on port 8000 and the admin panel on port 8080. Open `http://localhost:8080` in your browser to manage sessions.

## Default Entrypoint

The container runs the following command by default:

```bash
weilink mcp -t sse --host 0.0.0.0 -p 8000 --admin-port 8080 -d /data/weilink
```

You can override this by appending your own command:

```bash
# Admin panel only
docker run -p 8080:8080 -v weilink-data:/data/weilink oaklight/weilink \
    weilink admin --host 0.0.0.0 -p 8080 -d /data/weilink

# OpenAPI server + admin panel
docker run -p 8000:8000 -p 8080:8080 -v weilink-data:/data/weilink oaklight/weilink \
    weilink openapi --host 0.0.0.0 -p 8000 --admin-port 8080 -d /data/weilink
```

## Ports

| Port | Service |
|------|---------|
| `8000` | MCP SSE / OpenAPI server |
| `8080` | Admin panel |

## Data Persistence

Session tokens and context data are stored in `/data/weilink` inside the container. **Always mount a volume** to this path to persist data across container restarts — otherwise you'll need to re-scan the QR code each time.

## Multiple Profiles

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

## Docker Compose

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

## Building the Image

```bash
make build-docker

# With PyPI mirror
make build-docker PYPI_MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple

# With registry mirror
make build-docker REGISTRY_MIRROR=docker.1ms.run

# Specific version
make build-docker V=0.3.0
```
