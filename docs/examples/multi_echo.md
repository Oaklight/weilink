# 多会话回声机器人

演示多会话支持：在同一个机器人上登录两个微信账号，并回声所有会话的消息。

参见仓库中的 [`examples/multi_echo.py`](https://github.com/Oaklight/weilink/blob/master/examples/multi_echo.py)。

## 使用方法

```bash
python examples/multi_echo.py
```

每个会话都需要扫描各自的二维码。

## 工作原理

1. 创建一个 `WeiLink` 实例。
2. 使用不同的会话名称调用两次 `wl.login(name="...")`——每次调用会触发一个独立的二维码登录，对应不同的微信账号。
3. `wl.recv()` 在一次调用中返回**所有**活跃会话的消息。
4. 每条消息携带 `msg.bot_id` 字段，标识它来自哪个会话。

## 展示的核心功能

- **多会话登录** -- 多次调用 `wl.login(name=...)` 注册不同的微信账号。
- **统一接收** -- 单次 `wl.recv()` 调用聚合所有会话的消息。
- **会话标识** -- 通过 `msg.bot_id` 区分消息来源。
- **会话查询** -- `wl.sessions` 和 `wl.bot_ids` 列出所有活跃会话及其 bot ID。
