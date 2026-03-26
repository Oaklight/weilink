# 回调回声机器人

一个基于回调 API 的事件驱动回声机器人。功能与[简单回声机器人](simple_echo.md)相同，但用 `on_message` 和 `run_forever` 替代了手动轮询循环。

参见仓库中的 [`examples/callback_echo.py`](https://github.com/Oaklight/weilink/blob/master/examples/callback_echo.py)。

## 使用方法

```bash
python examples/callback_echo.py
```

## 工作原理

1. 创建 `WeiLink` 实例并通过扫码登录。
2. 使用 `@wl.on_message` 注册消息处理器 -- 每条消息到达时自动调用。
3. 调用 `wl.run_forever()`，启动后台轮询线程并阻塞主线程。
4. 收到 `Ctrl+C` 或 `SIGTERM` 信号时，`run_forever()` 自动停止调度器并调用 `wl.close()`。

## 展示的核心功能

- **装饰器注册** -- `@wl.on_message` 注册回调函数，无需手动编写 `recv()` 循环。
- **阻塞式调度** -- `run_forever()` 负责轮询、信号捕获和资源清理。
- **自动关停** -- `Ctrl+C` 触发优雅退出，无需 `try/finally` 样板代码。

## 轮询 vs 回调

| 方面 | 轮询（`recv()` 循环） | 回调（`on_message`） |
|------|----------------------|---------------------|
| 控制流 | 由你掌控循环 | 由框架掌控循环 |
| 样板代码 | `while True` + `try/finally` | 装饰器 + `run_forever()` |
| 适用场景 | 自定义调度、批处理 | 简单的请求/响应机器人 |
