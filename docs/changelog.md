# 更新日志

## v0.3.0 (2026-03-25)

### 新功能

- **多会话支持** — 通过 `login(name="...")` 将一个 bot 注册到多个微信账号；`recv()` 并发轮询所有会话，`send()` 自动路由到正确的会话
- **CDN 预上传 API** — `upload()` 预先上传媒体到 CDN，返回可复用的 `UploadedMedia` 引用
- **`send()` 接受 `UploadedMedia`**，发送预上传的媒体无需重复上传
- **`send()` 的 `auto_recv` 参数** — 发送前自动刷新 context token，返回 `SendResult`（兼容 bool）并携带 auto-recv 期间收到的消息；MCP 服务器默认启用
- **引用消息支持** — 当用户回复（引用）一条消息时，`Message.ref_msg` 字段暴露被引用的原始消息内容
- **OpenAPI 服务器** — 通过 `weilink openapi` 子命令以 REST API 暴露 bot 工具
- **Web 管理面板** — 浏览器 UI，支持会话管理、扫码登录和状态监控
- **MCP 多传输模式** — 支持 `stdio`、`sse` 和 `streamable-http` 传输
- **Docker 部署** — 容器镜像内置 MCP SSE + 管理面板，附带 `docker-compose.yaml`
- **统一 CLI** — 单一 `weilink` 命令，包含 `admin`、`mcp` 和 `openapi` 子命令
- `weilink mcp` 的 `--admin-port` 参数，可在同一进程中运行管理面板和 MCP 服务器
- 启动横幅与 PyPI 版本检查（`--no-banner` 可抑制）
- `get_updates()` 新增 `timeout` 参数
- 新增 `MediaContent` 类型别名，简化媒体参数的类型注解

### 问题修复

- 修复 Python 3.10 多会话时 `recv()` 崩溃问题（`concurrent.futures.TimeoutError` 未被捕获）

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
