# Docker 部署

WeiLink Docker 镜像将 **MCP 服务器**（AI agent 集成）和**管理面板**（Web UI 会话管理）打包在同一个容器中。

## 统一 CLI

`weilink` 命令提供三个子命令：

```bash
# 仅管理面板
weilink admin --host 0.0.0.0 -p 8080

# MCP 服务器（stdio，供 AI agent 使用）
weilink mcp

# MCP 服务器（SSE）+ 管理面板，同一进程
weilink mcp -t sse --host 0.0.0.0 -p 8000 --admin-port 8080 -d /data/weilink

# OpenAPI 服务器（REST API）
weilink openapi --host 0.0.0.0 -p 8000

# OpenAPI 服务器 + 管理面板，同一进程
weilink openapi --host 0.0.0.0 -p 8000 --admin-port 8080 -d /data/weilink
```

### `weilink admin` 选项

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--host` | 绑定地址 | `127.0.0.1` |
| `-p, --port` | 端口号 | `8080` |
| `-d, --base-path` | 数据目录（Profile 路径） | `~/.weilink/` |
| `--log-level` | 日志级别（`DEBUG`、`INFO`、`WARNING`、`ERROR`） | `INFO` |

### `weilink mcp` 选项

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `-t, --transport` | MCP 传输方式（`stdio`、`sse`、`streamable-http`） | `stdio` |
| `--host` | SSE/streamable-http 绑定地址 | `127.0.0.1` |
| `-p, --port` | SSE/streamable-http 端口 | `8000` |
| `-d, --base-path` | 数据目录（Profile 路径） | `~/.weilink/` |
| `--admin-port` | 同时在此端口启动管理面板（共用 host） | *（不启用）* |
| `--log-level` | 日志级别（`DEBUG`、`INFO`、`WARNING`、`ERROR`） | `INFO` |

### `weilink openapi` 选项

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--host` | 绑定地址 | `127.0.0.1` |
| `-p, --port` | 端口号 | `8000` |
| `-d, --base-path` | 数据目录（Profile 路径） | `~/.weilink/` |
| `--admin-port` | 同时在此端口启动管理面板（共用 host） | *（不启用）* |
| `--log-level` | 日志级别（`DEBUG`、`INFO`、`WARNING`、`ERROR`） | `INFO` |
| `--no-banner` | 抑制启动时的 ASCII 横幅 | *（关闭）* |

### 多 Profile

运行多个实例，使用不同的 profile 管理不同的 bot 账号：

```bash
weilink admin -d ~/.weilink/personal -p 8080 &
weilink admin -d ~/.weilink/work     -p 8081 &
```

每个 profile 独立维护自己的 `token.json` 和会话数据。

## Docker

### 快速开始

```bash
docker run -p 8000:8000 -p 8080:8080 -v weilink-data:/data/weilink oaklight/weilink
```

这将同时启动 MCP SSE 服务器（端口 8000）和管理面板（端口 8080）。在浏览器中打开 `http://localhost:8080` 管理会话。

### 仅管理面板

如果只需要管理面板而不需要 MCP 服务器：

```bash
docker run -p 8080:8080 -v weilink-data:/data/weilink oaklight/weilink \
    weilink admin --host 0.0.0.0 -p 8080 -d /data/weilink
```

### Docker 多 Profile

使用不同的 Docker volume 隔离 profile：

```bash
# 个人 bot
docker run -d --name weilink-personal \
    -p 8000:8000 -p 8080:8080 \
    -v weilink-personal:/data/weilink \
    oaklight/weilink

# 工作 bot
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
      - "8080:8080"  # 管理面板
    volumes:
      - weilink-data:/data/weilink
    restart: unless-stopped

volumes:
  weilink-data:
```

多 profile 配置：

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

### 构建镜像

```bash
make build-docker

# 使用 PyPI 镜像
make build-docker PYPI_MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple

# 使用 Docker 镜像加速
make build-docker REGISTRY_MIRROR=docker.1ms.run
```

### 数据持久化

会话 token 和上下文数据存储在容器内的 `/data/weilink`。**请务必挂载 volume** 到此路径以持久化数据——否则每次容器重启后都需要重新扫码登录。
