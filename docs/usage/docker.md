# Docker Deployment

WeiLink provides a standalone admin panel server (`weilink-admin`) that can run as a long-lived process, making it ideal for Docker deployment.

## Standalone CLI

The `weilink-admin` command starts an HTTP admin panel for managing bot sessions via a web browser.

```bash
# Default profile (~/.weilink/)
weilink-admin --host 0.0.0.0 --port 8080

# Custom profile
weilink-admin -d /path/to/profile -p 9090
```

### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--host` | Host address to bind to | `127.0.0.1` |
| `-p, --port` | Port number | `8080` |
| `-d, --base-path` | Data directory (profile path) | `~/.weilink/` |
| `--log-level` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |

### Multiple Profiles

Run multiple instances with different profiles to manage separate bot accounts:

```bash
weilink-admin -d ~/.weilink/personal -p 8080 &
weilink-admin -d ~/.weilink/work     -p 8081 &
```

Each profile maintains its own `token.json` and session data independently.

## Docker

### Quick Start

```bash
docker run -p 8080:8080 -v weilink-data:/data/weilink oaklight/weilink-admin
```

Open `http://localhost:8080` in your browser to access the admin panel.

### Multiple Profiles with Docker

Use different Docker volumes to isolate profiles:

```bash
# Personal bot
docker run -d --name weilink-personal \
    -p 8080:8080 \
    -v weilink-personal:/data/weilink \
    oaklight/weilink-admin

# Work bot
docker run -d --name weilink-work \
    -p 8081:8080 \
    -v weilink-work:/data/weilink \
    oaklight/weilink-admin
```

### Docker Compose

```yaml
services:
  weilink-admin:
    image: oaklight/weilink-admin
    ports:
      - "8080:8080"
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
    image: oaklight/weilink-admin
    ports:
      - "8080:8080"
    volumes:
      - personal-data:/data/weilink
    restart: unless-stopped

  bot-work:
    image: oaklight/weilink-admin
    ports:
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
cd docker/
make build

# With PyPI mirror
make build PYPI_MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple

# With registry mirror
make build REGISTRY_MIRROR=docker.1ms.run
```

### Data Persistence

Session tokens and context data are stored in `/data/weilink` inside the container. **Always mount a volume** to this path to persist data across container restarts — otherwise you'll need to re-scan the QR code each time.
