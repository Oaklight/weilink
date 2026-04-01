# CLI 参考

`weilink` 命令提供 Bot 交互、服务器管理和凭证迁移等子命令：

```bash
# Bot 命令
weilink login                                    # 扫码登录
weilink status                                   # 查看会话状态
weilink recv --timeout 5                         # 接收消息
weilink send USER_ID --text "hello"              # 发送消息
weilink download 42 -o ./media                   # 下载媒体
weilink history --user USER_ID --limit 20        # 查询历史消息
weilink sessions                                 # 列出会话
weilink sessions rename old_name new_name        # 重命名会话
weilink sessions default work                    # 设置默认会话

# 服务器命令
weilink admin --host 0.0.0.0 -p 8080
weilink mcp -t sse --host 0.0.0.0 -p 8000 --admin-port 8080
weilink openapi --host 0.0.0.0 -p 8000

# 集成命令
weilink setup claude-code                       # 安装 Claude Code 插件
weilink setup codex                             # 安装 Codex 集成
weilink setup opencode                          # 安装 OpenCode 集成

# 其他命令
weilink migrate openclaw
```

所有 Bot 命令支持 `--json` 输出机器可读格式，以及 `-d, --base-path` 自定义数据目录。

## 全局选项

| 选项 | 说明 |
|------|------|
| `-V, --version` | 显示版本并检查更新 |

## Bot 命令

### `weilink login`

通过扫描二维码登录。在终端显示二维码供微信扫描。

```bash
weilink login                    # 登录默认会话
weilink login work               # 登录命名会话
weilink login --force            # 强制重新登录（忽略已有凭证）
weilink login --json             # 输出 JSON 结果
```

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `session_name` | 会话名称（位置参数，可选） | 默认会话 |
| `-f, --force` | 强制重新登录 | *（关闭）* |
| `-d, --base-path` | 数据目录 | `~/.weilink/` |
| `--json` | 输出机器可读 JSON | *（关闭）* |
| `--log-level` | 日志级别 | `INFO` |

### `weilink logout`

登出会话并移除持久化凭证。

```bash
weilink logout                   # 登出默认会话
weilink logout work              # 登出命名会话
```

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `session_name` | 会话名称（位置参数，可选） | 默认会话 |
| `-d, --base-path` | 数据目录 | `~/.weilink/` |
| `--json` | 输出机器可读 JSON | *（关闭）* |
| `--log-level` | 日志级别 | `INFO` |

### `weilink status`

显示会话连接状态。

```bash
weilink status                   # 人类可读格式
weilink status --json            # JSON 输出
```

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `-d, --base-path` | 数据目录 | `~/.weilink/` |
| `--json` | 输出机器可读 JSON | *（关闭）* |
| `--log-level` | 日志级别 | `INFO` |

### `weilink recv`

从所有已连接会话接收消息。

```bash
weilink recv                     # 默认 5 秒超时
weilink recv --timeout 30        # 等待最多 30 秒
weilink recv --json              # JSON 输出（用于脚本）
```

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `-t, --timeout` | 最大等待时间（秒） | `5` |
| `-d, --base-path` | 数据目录 | `~/.weilink/` |
| `--json` | 输出机器可读 JSON | *（关闭）* |
| `--log-level` | 日志级别 | `INFO` |

### `weilink send`

向用户发送消息。至少需要一个内容选项。

```bash
weilink send USER_ID --text "你好！"
weilink send USER_ID --image ./photo.jpg
weilink send USER_ID --file ./doc.pdf --file-name "报告.pdf"
weilink send USER_ID --text "见附件" --image ./photo.jpg  # 多模态
```

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `to` | 目标用户 ID（位置参数，必需） | — |
| `--text` | 文本内容 | — |
| `--image` | 图片文件路径 | — |
| `--file` | 文件附件路径 | — |
| `--file-name` | 文件显示名称 | 文件原始名 |
| `--video` | 视频文件路径 | — |
| `--voice` | 语音文件路径 | — |
| `-d, --base-path` | 数据目录 | `~/.weilink/` |
| `--json` | 输出机器可读 JSON | *（关闭）* |
| `--log-level` | 日志级别 | `INFO` |

### `weilink download`

根据消息 ID 下载媒体文件。需要消息存储（默认已启用）。

```bash
weilink download 42                       # 保存到 ~/.weilink/downloads/
weilink download 42 -o ./media            # 保存到自定义目录
weilink download 42 --json                # 以 JSON 输出路径和大小
```

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `message_id` | 消息 ID（位置参数，必需） | — |
| `-o, --output` | 输出目录 | `~/.weilink/downloads/` |
| `-d, --base-path` | 数据目录 | `~/.weilink/` |
| `--json` | 输出机器可读 JSON | *（关闭）* |
| `--log-level` | 日志级别 | `INFO` |

### `weilink history`

从 SQLite 存储查询历史消息。需要消息存储（默认已启用）。

```bash
weilink history                                  # 最近 50 条消息
weilink history --user USER_ID --limit 20        # 按用户筛选
weilink history --type IMAGE --direction received # 按类型/方向筛选
weilink history --since 2026-03-30 --text "hello" --json
```

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--user` | 按用户 ID 筛选 | — |
| `--bot` | 按 Bot ID 筛选 | — |
| `--type` | 按类型筛选：`TEXT`、`IMAGE`、`VOICE`、`FILE`、`VIDEO` | — |
| `--direction` | 按方向筛选：`received` 或 `sent` | — |
| `--since` | 起始时间（ISO 8601 或 unix 毫秒） | — |
| `--until` | 结束时间（ISO 8601 或 unix 毫秒） | — |
| `--text` | 文本子串搜索 | — |
| `--limit` | 最大结果数 | `50` |
| `--offset` | 分页偏移 | `0` |
| `-d, --base-path` | 数据目录 | `~/.weilink/` |
| `--json` | 输出机器可读 JSON | *（关闭）* |
| `--log-level` | 日志级别 | `INFO` |

### `weilink sessions`

会话管理：列出、重命名和设置默认会话。

```bash
weilink sessions                             # 列出所有会话
weilink sessions rename old_name new_name    # 重命名会话
weilink sessions default work                # 设置默认会话
```

#### `weilink sessions`（无子命令）

列出所有会话及连接状态，等同于 `weilink status`。

#### `weilink sessions rename`

| 选项 | 说明 |
|------|------|
| `old_name` | 当前会话名称（位置参数） |
| `new_name` | 新会话名称（位置参数） |
| `--json` | 输出机器可读 JSON |

#### `weilink sessions default`

| 选项 | 说明 |
|------|------|
| `session_name` | 要设为默认的会话名称（位置参数） |
| `--json` | 输出机器可读 JSON |

## 服务器命令

### `weilink admin`

启动 Web 管理面板，用于会话管理和扫码登录。

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--host` | 绑定地址 | `127.0.0.1` |
| `-p, --port` | 端口号 | `8080` |
| `-d, --base-path` | 数据目录（Profile 路径） | `~/.weilink/` |
| `--log-level` | 日志级别（`DEBUG`、`INFO`、`WARNING`、`ERROR`） | `INFO` |
| `--no-banner` | 抑制启动时的 ASCII 横幅 | *（关闭）* |

### `weilink mcp`

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

### `weilink openapi`

启动 OpenAPI（REST）服务器。端点详情参见 [OpenAPI 服务器](openapi.md)。

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--host` | 绑定地址 | `127.0.0.1` |
| `-p, --port` | 端口号 | `8000` |
| `-d, --base-path` | 数据目录（Profile 路径） | `~/.weilink/` |
| `--admin-port` | 同时在此端口启动管理面板（共用 host） | *（不启用）* |
| `--log-level` | 日志级别（`DEBUG`、`INFO`、`WARNING`、`ERROR`） | `INFO` |
| `--no-banner` | 抑制启动时的 ASCII 横幅 | *（关闭）* |

## 集成命令

### `weilink setup`

设置 AI 编程助手集成。详细说明请参阅 [IDE 集成](setup.md)。

```bash
weilink setup claude-code              # 安装 Claude Code 插件（软链接）
weilink setup claude-code --copy       # 复制文件（用于 Windows）
weilink setup claude-code --uninstall  # 移除插件
weilink setup codex                    # 安装 Codex 集成
weilink setup codex --uninstall        # 移除集成
weilink setup opencode                 # 安装 OpenCode 集成
weilink setup opencode --uninstall     # 移除集成
```

### `weilink hook-poll`

从消息存储中轮询新消息。由 hook 脚本内部使用。详见 [IDE 集成](setup.md#weilink-hook-poll)。

```bash
weilink hook-poll                      # 轮询新消息
weilink hook-poll --limit 50           # 最多返回 50 条消息
weilink hook-poll --reset              # 清除轮询状态
```

## 其他命令

### `weilink migrate`

!!! warning "实验性功能"
    此子命令为实验性功能，接口可能在未来版本中发生变化。

从其他 iLink Bot 工具导入凭证，切换到 WeiLink 时无需重新扫码。

#### `weilink migrate openclaw`

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
    迁移完成后，可通过 `weilink status` 或 `weilink admin` 查看会话是否正确加载并已连接。

## `--json` 输出

所有 Bot 命令支持 `--json` 输出机器可读格式。适用于脚本和工具集成：

```bash
# 以 JSON 获取会话状态
weilink status --json

# 以 JSON 接收消息
weilink recv --json | jq '.[] | .text'

# 发送并检查结果
weilink send USER_ID --text "hello" --json | jq '.success'
```

错误时，JSON 输出包含 `error` 字段：

```json
{"error": "Not connected"}
```

## 多 Profile

运行多个实例，使用不同的 profile 管理不同的 bot 账号：

```bash
weilink admin -d ~/.weilink/personal -p 8080 &
weilink admin -d ~/.weilink/work     -p 8081 &
```

每个 profile 独立维护自己的 `token.json` 和会话数据。
