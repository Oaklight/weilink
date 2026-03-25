# MCP 服务器

WeiLink 提供可选的 [MCP](https://modelcontextprotocol.io/)（Model Context Protocol）服务器，将 bot 能力暴露为 AI agent 可调用的工具。

## 安装

```bash
pip install weilink[mcp]
```

这会在核心包之外安装 [toolregistry-server](https://github.com/Oaklight/toolregistry) 的 MCP 支持。

!!! tip "MCP + OpenAPI"
    一次性安装 MCP 和 OpenAPI 服务器支持：

    ```bash
    pip install weilink[server]
    ```

    详见 [OpenAPI 服务器](openapi.md) 了解 REST API 模式。

## 运行

WeiLink MCP 服务器支持三种传输模式：**stdio**（默认）、**SSE** 和 **streamable-http**。

### stdio（默认）

```bash
# 通过统一 CLI
weilink mcp

# 或通过 Python 模块
python -m weilink.mcp
```

stdio 传输由 MCP 客户端（Claude Desktop、Cursor 等）启动，而非独立运行。

### SSE / HTTP

```bash
# SSE 传输
weilink mcp -t sse -p 8000

# Streamable HTTP 传输（推荐用于网络访问）
weilink mcp -t http -p 8000

# 同时运行管理面板
weilink mcp -t http -p 8000 --admin-port 8080

# 绑定到所有网卡
weilink mcp -t http --host 0.0.0.0 -p 8000
```

### CLI 选项

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `-t, --transport` | 传输模式：`stdio`、`sse`、`streamable-http`（或 `http`） | `stdio` |
| `--host` | SSE / HTTP 绑定地址 | `127.0.0.1` |
| `-p, --port` | SSE / HTTP 端口 | `8000` |
| `-d, --base-path` | 数据目录（配置路径） | `~/.weilink/` |
| `--admin-port` | 同时在此端口启动管理面板（同一地址） | *（禁用）* |
| `--log-level` | 日志级别（`DEBUG`、`INFO`、`WARNING`、`ERROR`） | `INFO` |
| `--no-banner` | 禁止启动时显示 ASCII 横幅 | *（关闭）* |

## 客户端配置

### Claude Desktop

添加到 `claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "weilink": {
      "command": "weilink",
      "args": ["mcp"]
    }
  }
}
```

### Claude Code（stdio）

```bash
claude mcp add weilink -- weilink mcp
```

### Claude Code（HTTP）

先启动 MCP 服务器：

```bash
weilink mcp -t http -p 8000
```

然后在 Claude Code 设置（`~/.claude/settings.json`）中添加：

```json
{
  "mcpServers": {
    "weilink": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

!!! tip "为什么用 HTTP？"
    HTTP 传输让 MCP 服务器在 Claude Code 会话之间持久运行。只需启动一次，所有 Claude Code 会话都可以连接同一个服务器实例——无需在开始新对话时重启服务器。

### Cursor / VS Code

在 MCP 设置中添加：

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

## 可用工具

### `recv_messages`

轮询接收微信用户的新消息。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `timeout` | float | 5.0 | 最大等待时间（秒） |

返回 JSON 消息数组。每条消息包含 `message_id`、`from_user`、`msg_type`、`text`、`timestamp`、`bot_id`，以及媒体元数据（如有）。

### `send_message`

向微信用户发送文本和/或媒体。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `to` | str | *（必填）* | 目标用户 ID |
| `text` | str | `""` | 文本内容 |
| `image_path` | str | `""` | 本地图片路径 |
| `file_path` | str | `""` | 本地文件路径 |
| `file_name` | str | `""` | 文件显示名称 |
| `video_path` | str | `""` | 本地视频路径 |
| `voice_path` | str | `""` | 本地语音路径 |

!!! note "自动刷新 context"
    MCP 服务器在每次发送前会自动调用 `recv()` 刷新 context token。即使最近未调用 `recv_messages`，也能确保 bot 持有有效的 token。

### `download_media`

下载已接收消息中的媒体文件。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `message_id` | str | *（必填）* | 来自 `recv_messages` 的消息 ID |
| `save_dir` | str | `~/.weilink/downloads/` | 文件保存目录 |

返回保存路径和文件大小。

### `list_sessions`

列出所有会话及其连接状态。无参数。

### `login` / `check_login`

两步式 QR 码登录流程：

1. 调用 `login(session_name="")` — 返回 QR 码 URL 供用户扫码。
2. 反复调用 `check_login()` — 返回扫码状态（`pending`、`scanned`、`confirmed` 或 `expired`）。

!!! note "推荐预先登录"
    服务器启动时会自动发现 `~/.weilink/` 下的已有会话。如果你已经通过 SDK 登录过，MCP 服务器会自动加载你的会话 — 无需调用登录工具。

## 架构

```mermaid
graph LR
    A[AI Agent] -->|MCP 协议| B[WeiLink MCP]
    B -->|WeiLink SDK| C[iLink API]
    C --> D[微信]
```

MCP 服务器内部封装了一个 `WeiLink` 实例。通过 `recv_messages` 接收的消息会被缓存（最多 1000 条），以便后续通过 `download_media` 下载媒体。

## Skills 元数据

WeiLink 附带两个元数据文件用于注册表发现：

- **`server.json`** — [MCP 官方标准](https://modelcontextprotocol.io/)，供 MCP 注册表和包管理器使用。
- **`smithery.yaml`** — [Smithery](https://smithery.ai/) 注册表格式，用于自动配置。
