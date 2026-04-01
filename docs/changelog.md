# 更新日志

## v0.6.0 (2026-04-01)

### 新功能

- **AI 编程助手集成** — 新增 `weilink setup` 命令，一条命令即可为 Claude Code、Codex 和 OpenCode 安装 hooks、MCP 配置和斜杠命令；`weilink setup claude-code` 以符号链接方式安装完整插件（自动轮询 hook + MCP + `/weilink` 技能），`weilink setup codex` 安装 hooks 和命令，`weilink setup opencode` 将 MCP 配置合并到 `opencode.json`
- **Hook 轮询引擎** — 新增 `weilink hook-poll`，读取本地 SQLite 消息存储并以 JSON 格式输出新消息；Claude Code 和 Codex 的 `UserPromptSubmit` hook 通过此引擎自动将微信新消息注入对话上下文

## v0.5.1 (2026-04-01)

### 改进

- **跨平台文件锁** ([#8](https://github.com/Oaklight/weilink/pull/8)) — 将内部 `_filelock.py`（Windows 上为空操作）替换为 [zerodep](https://github.com/Oaklight/zerodep) `filelock` 模块；Windows 现在使用 `msvcrt.locking` 实现真正的跨进程文件锁，不再静默跳过

## v0.5.0 (2026-03-31)

### 破坏性变更

- **重命名服务器工具以匹配 SDK** ([#6](https://github.com/Oaklight/weilink/issues/6)) — `recv_messages` → `recv`、`send_message` → `send`、`download_media` → `download`、`get_message_history` → `history`、`list_sessions` → `sessions`；工具名称现在与 SDK 方法名保持一致，三层 API 统一命名
- **合并 `login` + `check_login` 为单个 `login` 工具** — `login` 工具现在是有状态的：首次调用发起二维码流程，后续调用以可配置超时（默认 30 秒）轮询直到状态变化；`check_login` 已移除
- **默认会话子目录布局** — 默认会话文件现存储在 `base_path/default/` 而非直接平铺在 `base_path/` 下；已有的旧布局在首次加载时自动迁移；所有会话目录结构统一

### 新功能

- **SQLite 消息持久化** — 新增 `MessageStore`（`_store.py`），基于 SQLite WAL 模式存储所有收发消息到 `messages.db`；支持历史消息查询、防止重启后消息丢失、`download` 重启后仍可恢复；通过 `WeiLink(message_store=True)` 启用，MCP/OpenAPI 服务模式下默认开启
- **`history` 服务器工具** — 按用户、bot、类型、方向、时间范围或文本内容查询历史消息；支持 `limit`/`offset` 分页
- **`logout` 服务器工具** — 登出会话并移除持久化凭据
- **`rename_session` 服务器工具** — 重命名会话
- **`set_default` 服务器工具** — 设置默认会话
- **协作式轮询降级** — 当 `message_store` 已启用且轮询锁被其他进程持有时，`recv()` 从 SQLite 读取最近消息而非返回空列表；无需中心服务器即可实现多客户端访问
- **CLI Bot 命令** — 新增 `login`、`logout`、`status`、`recv`、`send`、`download`、`history` 和 `sessions`（含 `rename`/`default` 子命令）子命令；所有命令支持 `--json` 输出机器可读格式，以及 `-d, --base-path` 自定义数据目录
- **原子文件写入** — `token.json`、`contexts.json` 和 `.default_session` 现在通过临时文件 + `os.replace()` 写入，防止崩溃时文件损坏
- **管理面板消息历史** — 滑出式消息抽屉，以微信风格气泡展示每个用户的对话记录；支持所有消息类型、分页、类型过滤和文本搜索
- **管理面板懒加载下载** — 媒体消息上的下载按钮通过 `GET /api/messages/<id>/download` 按需从 CDN 拉取文件
- **后台自动轮询** — 管理面板和 MCP/OpenAPI 服务器启动时自动调用 `run_background()`，用户和消息无需等待显式 `recv` 调用即可自动显示

### 改进

- **管理面板 i18n 改进** — 切换语言时动态内容重新渲染；新增本地化的下载按钮和发送者标签

### 问题修复

- **修复管理面板 API 消息 ID 精度** — 19 位 message_id 在 `/api/messages` 响应中序列化为字符串，防止 JavaScript 整数精度丢失

## v0.4.3 (2026-03-30)

### 问题修复

- **修复管理面板登录未保存 `user_id`** — `_handle_poll_login` 现在从 QR 确认响应中提取 `ilink_user_id` 并存入 `BotInfo`，与 SDK `login()` 行为一致
- **整合管理面板用户 ID 显示** — 用统一的「用户 ID」列替代冗余的「用户」列，显示 bot 拥有者的微信用户 ID 及活跃/过期徽章；`/api/sessions` 响应中增加 `user_id` 字段

### 改进

- **协议层增加调试日志** — `_protocol.py` 现在在 DEBUG/INFO 级别记录所有 HTTP 请求/响应、`get_updates` 消息数量、cursor 变化和错误详情，便于问题排查
- **MCP `recv` 增加调试日志** — `server/app.py` 记录轮询开始、消息数量和单条消息详情
- **Docker entrypoint 支持 PUID/PGID** — 新增 `entrypoint.sh`，运行时通过 `su-exec` 修正 `/data/weilink` 目录权限，支持 bind-mount 卷与宿主机用户权限匹配

## v0.4.2 (2026-03-28)

### 新功能

- **跨进程 profile 文件锁** ([#5](https://github.com/Oaklight/weilink/issues/5)) — 多个 WeiLink 实例共享同一数据目录（`~/.weilink/`）时，通过 `fcntl.flock()` 文件锁进行协调；非阻塞 **轮询锁**（`.poll.lock`）确保同一时刻只有一个进程轮询 iLink，短暂持有的 **数据锁**（`.data.lock`）序列化 `token.json` / `contexts.json` 的读-改-写操作；防止 cursor 分叉、send_count 覆盖和文件损坏

## v0.4.1 (2026-03-27)

### 问题修复

- **修复会话重命名后旧目录残留** — 为 `_Session` 添加 `_io_lock` 互斥锁，序列化文件 I/O 操作（rename、save、load、logout）；重命名现使用 `shutil.rmtree` 替代 `rmdir` 强制清理旧目录；防止后台线程在文件移动和路径更新之间重新创建旧目录的竞态条件

## v0.4.0 (2026-03-27)

### 破坏性变更

- **`weilink.mcp` 模块重命名为 `weilink.server`** — 内部服务器模块从 `weilink.mcp.server` 迁移至 `weilink.server.app`；请使用 `python -m weilink.server` 替代 `python -m weilink.mcp`；CLI 子命令（`weilink mcp`、`weilink openapi`、`weilink admin`）和安装 extras（`weilink[mcp]`、`weilink[server]`）保持不变

### 新功能

- **凭证迁移 CLI** *（实验性）* — `weilink migrate openclaw` 从 OpenClaw 微信插件（`@tencent-weixin/openclaw-weixin`）导入会话，无需重新扫码；支持 `--dry-run` 预览和 `--source` 自定义 OpenClaw 状态目录
- **发送配额跟踪** ([`58de18b`](https://github.com/Oaklight/weilink/commit/58de18b)) — SDK 自动跟踪每用户发送计数（10 条 context_token 配额）；配额耗尽时抛出 `QuotaExhaustedError`；`SendResult.remaining` 显示剩余可发送条数
- **`TextTooLongError`** ([`58de18b`](https://github.com/Oaklight/weilink/commit/58de18b)) — 文本超过 16 KiB UTF-8 限制时，`send()` 抛出 `TextTooLongError` 并报告实际字节数，而非静默拆分
- **`BotInfo.user_id`** ([`3772776`](https://github.com/Oaklight/weilink/commit/3772776)) — 登录时捕获授权 bot 的微信用户 ID；可通过 `Session.user_id` 访问
- **新增模型字段** ([`a2759bc`](https://github.com/Oaklight/weilink/commit/a2759bc)) — `ImageInfo.hd_size`、`VoiceInfo.encode_type` / `bits_per_sample` / `sample_rate`
- **会话过期自动恢复** ([`b44181b`](https://github.com/Oaklight/weilink/commit/b44181b)) — 收到 `errcode: -14` 时自动清除 cursor 和 context token，确保重新登录可从干净状态开始
- **消息接收增强** ([`c000f8a`](https://github.com/Oaklight/weilink/commit/c000f8a), [`ddcb0f0`](https://github.com/Oaklight/weilink/commit/ddcb0f0)) — 连续 `recv()` 失败时自动退避重试；支持服务端返回的 `longpolling_timeout_ms`

## v0.3.0 (2026-03-25)

### 新功能

- **多会话支持** ([`7dbb23d`](https://github.com/Oaklight/weilink/commit/7dbb23d)) — 通过 `login(name="...")` 将一个 bot 注册到多个微信账号；`recv()` 并发轮询所有会话，`send()` 自动路由到正确的会话
- **CDN 预上传** ([`20f660e`](https://github.com/Oaklight/weilink/commit/20f660e)) — `upload()` 预先上传媒体到 CDN，返回可复用的 `UploadedMedia` 引用；`send()` 接受它以避免重复上传
- **`send()` 的 `auto_recv` 参数** ([#4](https://github.com/Oaklight/weilink/issues/4), [`c72099a`](https://github.com/Oaklight/weilink/commit/c72099a)) — 发送前可选刷新 context token，返回 `SendResult`（兼容 bool）并携带刷新期间收到的消息
- **引用消息支持** ([#3](https://github.com/Oaklight/weilink/issues/3), [`c984f72`](https://github.com/Oaklight/weilink/commit/c984f72)) — 当用户回复（引用）一条消息时，`Message.ref_msg` 字段暴露被引用的原始消息内容
- **MCP 服务器** ([`837997f`](https://github.com/Oaklight/weilink/commit/837997f)) — 支持 `stdio`、`sse` 和 `streamable-http` 传输；`--admin-port` 可同进程启动管理面板
- **OpenAPI 服务器** ([`e40c126`](https://github.com/Oaklight/weilink/commit/e40c126)) — 通过 `weilink openapi` 子命令以 REST API 暴露 bot 工具
- **Web 管理面板** ([`c65a28a`](https://github.com/Oaklight/weilink/commit/c65a28a)) — 浏览器 UI，支持会话管理、扫码登录和状态监控
- **Docker 部署** ([`e1450dd`](https://github.com/Oaklight/weilink/commit/e1450dd)) — 容器镜像内置 MCP SSE + 管理面板，附带 `docker-compose.yaml`
- **统一 CLI** ([`9a48774`](https://github.com/Oaklight/weilink/commit/9a48774)) — 单一 `weilink` 命令，包含 `admin`、`mcp` 和 `openapi` 子命令

### 问题修复

- 修复 Python 3.10 多会话时 `recv()` 崩溃问题 ([`4625f34`](https://github.com/Oaklight/weilink/commit/4625f34))

## v0.2.0 (2026-03-24)

### 新功能

- **多模态消息** — 支持收发图片、语音、文件和视频
- **主动发消息** — context_tokens 重启后持久化

### 问题修复

- 修复 CDN 上传可靠性

## v0.1.0 (2026-03-23)

- 初始版本发布
- 二维码登录与凭证持久化
- 长轮询消息接收
- 文本消息发送与自动 context_token 管理
- 输入状态指示支持
