# 注意事项

本页整理了开发和调试过程中容易踩坑的地方，帮助你少走弯路。

## 平台限制

- **不能主动发起对话** — 用户必须先给 bot 发消息，bot 才能回复。bot 只能回复拥有有效 context_token 的用户。
- **24 小时窗口** — 用户超过 24 小时未发消息，bot 发送的消息会被平台静默丢弃，不会返回错误。
- **`ret: -14` = 登录过期** — bot 的登录凭证已过期，需要调用 `login(force=True)` 重新认证。
- **`ret: -2` = 请求被拒绝** — 可能原因：context_token 已过期、达到 10 条回复上限、或文本超过 16 KiB。需等待用户发送新消息以获取新 token。

## 媒体与 CDN

- **一条消息 = 一个媒体项** — 协议不支持在单条消息中发送多个媒体项（如图片+文字）。当同时传入 `text` 和 `image` 给 `send()` 时，SDK 会自动拆分为多条消息发送。
- **CDN 上传绑定用户** — 上传到 CDN 时，`to_user_id` 必须是有效用户，虚假用户 ID 会导致 `ret: -1`。
- **CDN 引用可复用** — `upload()` 返回的 `UploadedMedia` 可以多次传给 `send()`，避免重复上传同一文件。但 CDN 过期策略未公开，不建议长期缓存引用。
- **视频预览错误** — 将下载的视频重新上传到 CDN 可能会出现 "probe preview error"。直接上传本地文件则正常。
- **图片 AES 密钥差异** — 接收的图片消息中，正确的解密密钥在 `image_item.aeskey`（原始 hex），而非 `media.aes_key`（base64）。SDK 已自动处理此差异。

## 消息投递

- **文本大小限制：16 KiB UTF-8** — 服务端拒绝超过 16 384 字节 UTF-8 编码的文本（`ret: -2`）。注意：限制是**字节长度**而非字符数 — 16 000 个 ASCII 字符可以发送，但 6 000 个中文字符（约 18 000 字节）则超限。SDK 会自动将超长文本拆分为多条消息。
- **每个 context_token 最多回复 10 条** — 每个 context_token 允许最多发送 10 条出站消息，超出后 `send()` 返回 `ret: -2`。用户发送新消息后计数器重置（会签发新 token）。参见 [epiral/weixin-bot#3](https://github.com/epiral/weixin-bot/issues/3)。
- **批量延迟到达** — 已观察到偶发情况：`send()` 返回成功，但消息在用户端延迟数分钟后批量送达。这是微信 / iLink 服务端的行为，不是 SDK 的 bug。使用 `auto_recv=True` 在发送前刷新 context token 可能在一定程度上缓解此问题。正在持续跟踪中（[#2](https://github.com/Oaklight/weilink/issues/2)）。

## Context Token

- **Token 按用户独立管理** — 每个用户有独立的 context_token。旧 token 在 24 小时窗口内仍然有效，即使已签发更新的 token。
- **持久化到 `contexts.json`** — Context token 保存在 `~/.weilink/contexts.json`（与 `token.json` 分离），带有时间戳。加载时自动丢弃超过 24 小时的条目。
- **主动发消息** — 只要存在有效的 context_token（来自之前的会话或从磁盘加载），无需先调用 `recv()` 即可主动发送消息。
