# 多媒体回声机器人

接收所有类型的消息（文本、图片、语音、文件、视频）并原样回复。多媒体消息会先下载再重新发送。

参见仓库中的 [`examples/media_echo.py`](https://github.com/Oaklight/weilink/blob/master/examples/media_echo.py)。

## 使用方法

```bash
pip install weilink[media]
python examples/media_echo.py
```

通过 `LOGLEVEL` 环境变量设置日志级别（默认：`INFO`）：

```bash
LOGLEVEL=DEBUG python examples/media_echo.py
```

## 工作原理

1. 登录并进入接收循环。
2. 根据 `msg_type` 分派每条消息：

    - **TEXT** -- 回复 `"Echo: <文本>"`。
    - **IMAGE** -- 通过 `wl.download(msg)` 下载图片，然后用 `wl.send(user, image=data)` 重新发送。
    - **VOICE** -- 下载语音。如果有转写文本（`msg.voice.text`），则回复转写内容；否则重新发送音频。
    - **FILE** -- 下载文件并重新发送，保留原始文件名。
    - **VIDEO** -- 下载视频并重新发送。

3. 所有多媒体处理错误会被捕获并以文本形式反馈给用户。

## 展示的核心功能

- **MessageType 枚举** -- 按 `MessageType.TEXT`、`IMAGE`、`VOICE`、`FILE`、`VIDEO` 分支处理。
- **多媒体下载** -- `wl.download(msg)` 返回原始 `bytes`。
- **发送多媒体** -- `wl.send()` 接受 `image`、`voice`、`file`、`video` 关键字参数。
- **文件元数据** -- 访问 `msg.file.file_name`、`msg.image.thumb_width`、`msg.voice.playtime` 等属性。
