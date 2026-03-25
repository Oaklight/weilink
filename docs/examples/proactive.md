# 主动发消息

这些示例演示主动发送消息——在建立 `context_token` 后，无需等待用户先发消息。

## 主动发送文本

等待一条传入消息以缓存 `context_token`，然后向该用户连续发送 3 条文本消息。

参见仓库中的 [`examples/test_proactive_send.py`](https://github.com/Oaklight/weilink/blob/master/examples/test_proactive_send.py)。

### 使用方法

```bash
python examples/test_proactive_send.py
```

### 工作原理

1. 登录后通过 `wl.recv()` 等待一条传入消息。
2. SDK 自动缓存该消息的 `context_token`。
3. 连续调用 `wl.send()` 向同一用户发送 3 条文本消息——无需再次调用 `recv()`。

## 主动发送多媒体

使用持久化的 `context_token` 向指定用户发送文本、图片、文件（PDF）和视频——完全不需要调用 `recv()`。

参见仓库中的 [`examples/test_proactive_media.py`](https://github.com/Oaklight/weilink/blob/master/examples/test_proactive_media.py)。

### 使用方法

```bash
python examples/test_proactive_media.py
```

!!! note
    此示例硬编码了目标用户 ID 和本地文件路径。运行前请修改脚本中的 `USER` 变量和文件路径。

### 工作原理

1. 登录后，由于 SDK 会跨会话持久化 `context_token`，如果用户之前给机器人发过消息，则无需调用 `recv()`。
2. 依次发送四种媒体类型：文本、图片、文件、视频。
3. 每次 `wl.send()` 调用都将本地文件读取为 `bytes`，通过相应的关键字参数传入（`image=`、`file=`、`video=`）。

## 展示的核心功能

- **context_token 缓存** -- SDK 自动存储令牌，无需等待用户先发消息即可向其发送。
- **context_token 持久化** -- 令牌在机器人重启后仍然有效，支持完全主动的消息发送。
- **连续发送** -- 多次 `wl.send()` 调用无需穿插 `wl.recv()`。
- **多模态主动发送** -- 文本、图片、文件、视频均可主动发送。
