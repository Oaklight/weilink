# 更新日志

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
