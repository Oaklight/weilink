# CLI 参考

`weilink` 命令提供部署、服务器管理和凭证迁移等子命令：

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

# 从 OpenClaw 迁移凭证
weilink migrate openclaw
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

## `weilink migrate`

!!! warning "实验性功能"
    此子命令为实验性功能，接口可能在未来版本中发生变化。

从其他 iLink Bot 工具导入凭证，切换到 WeiLink 时无需重新扫码。

### `weilink migrate openclaw`

从 OpenClaw 微信插件（`@tencent-weixin/openclaw-weixin`）迁移会话。

```bash
# 预览将会迁移的内容
weilink migrate openclaw --dry-run

# 执行迁移（读取 ~/.openclaw，写入 ~/.weilink/）
weilink migrate openclaw

# 自定义路径
weilink migrate openclaw --source /path/to/openclaw --base-path /path/to/weilink
```

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--source` | OpenClaw 状态目录 | `~/.openclaw` |
| `-d, --base-path` | WeiLink 数据目录 | `~/.weilink/` |
| `--dry-run` | 仅展示将要迁移的内容，不写入文件 | *（关闭）* |

迁移会将每个 OpenClaw 账户转换为一个命名的 WeiLink 会话。已存在的会话不会被覆盖 — 如果同名会话已经存在，则跳过。

!!! tip
    迁移完成后，可通过 `weilink admin` 查看会话是否正确加载并已连接。

## 多 Profile

运行多个实例，使用不同的 profile 管理不同的 bot 账号：

```bash
weilink admin -d ~/.weilink/personal -p 8080 &
weilink admin -d ~/.weilink/work     -p 8081 &
```

每个 profile 独立维护自己的 `token.json` 和会话数据。
