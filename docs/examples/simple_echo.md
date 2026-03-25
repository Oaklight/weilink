# 简单回声机器人

一个无外部依赖的最小回声机器人。接收文字消息并原样回复。

参见仓库中的 [`examples/simple_echo.py`](https://github.com/Oaklight/weilink/blob/master/examples/simple_echo.py)。

## 使用方法

```bash
python examples/simple_echo.py
```

## 工作原理

1. 创建 `WeiLink` 实例并通过扫码登录。
2. 进入轮询循环，调用 `wl.recv(timeout=35.0)` 等待消息。
3. 对每条文字消息，使用 `wl.send()` 回复 `"Echo: <文本>"`。

## 展示的核心功能

- **登录流程** -- `WeiLink()` + `wl.login()` 进行身份验证。
- **长轮询** -- `wl.recv(timeout=...)` 阻塞等待消息到达或超时。
- **发送文本** -- `wl.send(user, text)` 发送纯文本回复。
- **优雅退出** -- 捕获 `KeyboardInterrupt` 并调用 `wl.close()`。
