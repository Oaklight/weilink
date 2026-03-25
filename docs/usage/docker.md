# Docker 部署

WeiLink 提供独立的管理面板服务器（`weilink-admin`），可作为长驻进程运行，非常适合 Docker 部署。

## 独立 CLI

`weilink-admin` 命令启动一个 HTTP 管理面板，通过浏览器管理 bot 会话。

```bash
# 默认配置（~/.weilink/）
weilink-admin --host 0.0.0.0 --port 8080

# 自定义配置目录
weilink-admin -d /path/to/profile -p 9090
```

### CLI 选项

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--host` | 绑定地址 | `127.0.0.1` |
| `-p, --port` | 端口号 | `8080` |
| `-d, --base-path` | 数据目录（Profile 路径） | `~/.weilink/` |
| `--log-level` | 日志级别（`DEBUG`、`INFO`、`WARNING`、`ERROR`） | `INFO` |

### 多 Profile

运行多个实例，使用不同的 profile 管理不同的 bot 账号：

```bash
weilink-admin -d ~/.weilink/personal -p 8080 &
weilink-admin -d ~/.weilink/work     -p 8081 &
```

每个 profile 独立维护自己的 `token.json` 和会话数据。

## Docker

### 快速开始

```bash
docker run -p 8080:8080 -v weilink-data:/data/weilink oaklight/weilink-admin
```

在浏览器中打开 `http://localhost:8080` 访问管理面板。

### Docker 多 Profile

使用不同的 Docker volume 隔离 profile：

```bash
# 个人 bot
docker run -d --name weilink-personal \
    -p 8080:8080 \
    -v weilink-personal:/data/weilink \
    oaklight/weilink-admin

# 工作 bot
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

多 profile 配置：

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

### 构建镜像

```bash
cd docker/
make build

# 使用 PyPI 镜像
make build PYPI_MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple

# 使用 Docker 镜像加速
make build REGISTRY_MIRROR=docker.1ms.run
```

### 数据持久化

会话 token 和上下文数据存储在容器内的 `/data/weilink`。**请务必挂载 volume** 到此路径以持久化数据——否则每次容器重启后都需要重新扫码登录。
