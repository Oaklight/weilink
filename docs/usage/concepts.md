# 核心概念

本页解释 WeiLink 的关键概念和设计决策，帮助你理解各组件之间的关系。

## iLink 协议

iLink 是腾讯为微信推出的官方 bot 协议。它提供一组 REST API 端点，允许开发者注册 bot 并与微信用户进行程序化交互。

WeiLink 是一个轻量级 Python SDK，封装了 iLink 协议，提供简洁的登录、消息收发和媒体处理接口——零运行时依赖。

## Bot

**Bot** 是在 iLink 平台注册的应用。每个 bot 有唯一的 `bot_id`（如 `abc123@im.bot`）。

!!! warning "一个账号，一个 bot"
    一个微信号同一时间只能绑定 **一个 bot**。登录新 bot 会自动解绑该账号与之前 bot 的关系。

## Session（会话）

**Session** 代表一个微信号与 bot 之间的绑定关系。

```python
wl = WeiLink()

# 默认会话
wl.login()

# 命名会话 — 同一个 bot 绑定另一个微信号
wl.login(name="work")
```

- **默认会话** 在实例化 `WeiLink` 时自动创建。
- **命名会话** 允许一个 bot 同时服务多个微信账号。
- 每个会话有独立的登录凭证，存储在 `~/.weilink/<session_name>/` 目录下。

### 默认会话

当存在多个会话时，其中一个被指定为 **默认会话**。默认会话用于 `wl.bot_id`、`wl.is_connected` 等操作。

```python
wl.set_default("work")  # 切换默认会话为 "work"
```

默认会话的选择通过 `~/.weilink/.default_session` 持久化，重启后自动恢复。

详见 [多会话](multi_session.md) 了解完整用法。

## User（用户）

**用户** 是向 bot 发过消息的微信账号。用户通过 `user_id`（如 `wxid_xxx@im.wechat`）标识。

Bot **无法主动发起对话** — 只能回复曾经发过消息的用户。

## Context Token

**context_token** 是 iLink 服务器在用户发送消息时签发的短时效凭证。Bot 需要有效的 context_token 才能向该用户发送消息。

关键特性：

- **按用户独立管理** — 每个用户有自己的 context_token。
- **24 小时窗口** — token 在用户最后一条消息后约 24 小时过期。过期后 bot 发送的消息会被平台 **静默丢弃**（不返回错误）。
- **自动管理** — SDK 自动从收到的消息中提取和更新 context_token。
- **持久化** — token 保存在 `~/.weilink/<session>/contexts.json`，带有时间戳，重启后自动恢复。

```
用户发消息 → iLink 签发 context_token → SDK 存储
Bot 调用 send() → SDK 使用已存储的 context_token → iLink 投递消息
```

!!! tip "主动发消息"
    只要存在有效的 context_token（来自之前的会话或从磁盘加载），无需先调用 `recv()` 即可直接调用 `send()`。

!!! tip "自动刷新"
    向 `send()` 传入 `auto_recv=True` 可在发送前自动调用 `recv()` 刷新 context token。MCP 服务器默认启用此功能。

## 引用消息（ref_msg）

当用户 **引用回复** 一条消息时，iLink 协议会在载荷中包含被引用消息的内容。SDK 将其解析为 `RefMessage` 对象，通过 `Message.ref_msg` 访问。

```python
for msg in wl.recv():
    if msg.ref_msg is not None:
        print(f"引用: {msg.ref_msg.text}")
    print(f"新消息: {msg.text}")
```

`RefMessage` 携带与 `Message` 相同的媒体字段（`text`、`image`、`voice`、`file`、`video`），但 **不含元数据**（无 `from_user`、`message_id`、`timestamp`）——协议不为被引用消息提供这些信息。

!!! note
    当被引用的消息是图片或其他纯媒体消息时，部分微信客户端不会在协议载荷中包含 `ref_msg`。此时 `msg.ref_msg` 为 `None`。

## 消息流

### 接收

```
微信用户 → 微信 → iLink 服务器 → WeiLink SDK (recv) → 你的代码
```

`recv()` 使用长轮询：阻塞等待新消息到达或超时。当存在多个会话时，所有会话并发轮询。

### 发送

```
你的代码 → WeiLink SDK (send) → iLink 服务器 → 微信 → 微信用户
```

`send()` 根据目标 `user_id` 自动路由到正确的会话。如果该用户存在于多个会话中，使用最近活跃的会话。

### 媒体

iLink 协议要求 **每条消息只能包含一个媒体项**。当你同时传入 `text` 和 `image` 给 `send()` 时，SDK 会自动拆分为多条消息发送。

媒体文件（图片、语音、视频、文件）在投递前会加密上传到腾讯 CDN。SDK 自动处理加密、上传和解密过程。
