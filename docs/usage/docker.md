# Docker 部署

WeiLink Docker 镜像将 **MCP 服务器**（AI agent 集成）和**管理面板**（Web UI 会话管理）打包在同一个容器中。Docker 外的 CLI 用法参见 [CLI 参考](cli.md)。

## 快速开始

```bash
docker run -p 8000:8000 -p 8080:8080 -v weilink-data:/data/weilink oaklight/weilink
```

这将同时启动 MCP SSE 服务器（端口 8000）和管理面板（端口 8080）。在浏览器中打开 `http://localhost:8080` 管理会话。

## 默认入口

容器默认运行以下命令：

```bash
weilink mcp -t sse --host 0.0.0.0 -p 8000 --admin-port 8080 -d /data/weilink
```

你可以追加自定义命令来覆盖默认行为：

```bash
# 仅管理面板
docker run -p 8080:8080 -v weilink-data:/data/weilink oaklight/weilink \
    weilink admin --host 0.0.0.0 -p 8080 -d /data/weilink

# OpenAPI 服务器 + 管理面板
docker run -p 8000:8000 -p 8080:8080 -v weilink-data:/data/weilink oaklight/weilink \
    weilink openapi --host 0.0.0.0 -p 8000 --admin-port 8080 -d /data/weilink
```

## 端口

| 端口 | 服务 |
|------|------|
| `8000` | MCP SSE / OpenAPI 服务器 |
| `8080` | 管理面板 |

## 数据持久化

会话 token 和上下文数据存储在容器内的 `/data/weilink`。**请务必挂载 volume** 到此路径以持久化数据——否则每次容器重启后都需要重新扫码登录。

## 多 Profile

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

## Docker Compose

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

## 构建镜像

```bash
make build-docker

# 使用 PyPI 镜像
make build-docker PYPI_MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple

# 使用 Docker 镜像加速
make build-docker REGISTRY_MIRROR=docker.1ms.run

# 指定版本
make build-docker V=0.3.0
```
