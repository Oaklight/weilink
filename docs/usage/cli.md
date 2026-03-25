# CLI 参考

`weilink` 命令提供三个子命令，适用于不同的部署场景：

```bash
# 仅管理面板
weilink admin --host 0.0.0.0 -p 8080

# MCP 服务器（stdio，供 AI agent 使用）
weilink mcp

# MCP 服务器（SSE）+ 管理面板，同一进程
weilink mcp -t sse --host 0.0.0.0 -p 8000 --admin-port 8080

# OpenAPI 服务器（REST API）
weilink openapi --host 0.0.0.0 -p 8000

# OpenAPI 服务器 + 管理面板，同一进程
weilink openapi --host 0.0.0.0 -p 8000 --admin-port 8080
```

## 全局选项

| 选项 | 说明 |
|------|------|
| `-V, --version` | 显示版本并检查更新 |

## `weilink admin`

启动 Web 管理面板，用于会话管理和扫码登录。

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--host` | 绑定地址 | `127.0.0.1` |
| `-p, --port` | 端口号 | `8080` |
| `-d, --base-path` | 数据目录（Profile 路径） | `~/.weilink/` |
| `--log-level` | 日志级别（`DEBUG`、`INFO`、`WARNING`、`ERROR`） | `INFO` |
| `--no-banner` | 抑制启动时的 ASCII 横幅 | *（关闭）* |

## `weilink mcp`

启动 MCP 服务器，用于 AI agent 集成。传输方式和客户端配置详见 [MCP 服务器](mcp.md)。

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `-t, --transport` | MCP 传输方式（`stdio`、`sse`、`streamable-http`、`http`） | `stdio` |
| `--host` | SSE/streamable-http 绑定地址 | `127.0.0.1` |
| `-p, --port` | SSE/streamable-http 端口 | `8000` |
| `-d, --base-path` | 数据目录（Profile 路径） | `~/.weilink/` |
| `--admin-port` | 同时在此端口启动管理面板（共用 host） | *（不启用）* |
| `--log-level` | 日志级别（`DEBUG`、`INFO`、`WARNING`、`ERROR`） | `INFO` |
| `--no-banner` | 抑制启动时的 ASCII 横幅 | *（关闭）* |

!!! note
    `http` 是 `streamable-http` 的别名。

## `weilink openapi`

启动 OpenAPI（REST）服务器。端点详情参见 [OpenAPI 服务器](openapi.md)。

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--host` | 绑定地址 | `127.0.0.1` |
| `-p, --port` | 端口号 | `8000` |
| `-d, --base-path` | 数据目录（Profile 路径） | `~/.weilink/` |
| `--admin-port` | 同时在此端口启动管理面板（共用 host） | *（不启用）* |
| `--log-level` | 日志级别（`DEBUG`、`INFO`、`WARNING`、`ERROR`） | `INFO` |
| `--no-banner` | 抑制启动时的 ASCII 横幅 | *（关闭）* |

## 多 Profile

运行多个实例，使用不同的 profile 管理不同的 bot 账号：

```bash
weilink admin -d ~/.weilink/personal -p 8080 &
weilink admin -d ~/.weilink/work     -p 8081 &
```

每个 profile 独立维护自己的 `token.json` 和会话数据。
