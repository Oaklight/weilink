# MCP 服务器

WeiLink 提供可选的 [MCP](https://modelcontextprotocol.io/)（Model Context Protocol）服务器，将 bot 能力暴露为 AI agent 可调用的工具。

## 安装

```bash
pip install weilink[mcp]
```

这会在核心包之外安装官方 MCP SDK（`mcp>=1.8.0`）。

## 运行

```bash
# CLI 入口
weilink-mcp

# 或通过 Python 模块
python -m weilink.mcp
```

服务器使用 **stdio** 传输 — 由 MCP 客户端（Claude Desktop、Cursor 等）启动，而非独立运行。

## 客户端配置

### Claude Desktop

添加到 `claude_desktop_config.json`：

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
    A[AI Agent] -->|MCP 协议| B[weilink-mcp]
    B -->|WeiLink SDK| C[iLink API]
    C --> D[微信]
```

MCP 服务器内部封装了一个 `WeiLink` 实例。通过 `recv_messages` 接收的消息会被缓存（最多 1000 条），以便后续通过 `download_media` 下载媒体。

## Skills 元数据

WeiLink 附带两个元数据文件用于注册表发现：

- **`server.json`** — [MCP 官方标准](https://modelcontextprotocol.io/)，供 MCP 注册表和包管理器使用。
- **`smithery.yaml`** — [Smithery](https://smithery.ai/) 注册表格式，用于自动配置。
