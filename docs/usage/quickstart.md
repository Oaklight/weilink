# 快速开始

## 登录

```python
from weilink import WeiLink

wl = WeiLink()
wl.login()
```

终端将打印二维码链接，使用微信扫码授权。

凭证会保存到 `~/.weilink/token.json`，下次运行时自动复用。

## 接收消息

```python
messages = wl.recv(timeout=35.0)
for msg in messages:
    print(f"{msg.from_user}: {msg.text}")
```

`recv()` 使用长轮询，最长阻塞 35 秒。

## 回调模式

除了手动 `recv()` 循环，你可以注册处理器，让 SDK 自动轮询：

```python
@wl.on_message
def handle(msg):
    print(f"{msg.from_user}: {msg.text}")
    wl.send(msg.from_user, "收到！")

wl.run_forever()  # 阻塞直到 Ctrl+C
```

如果主线程需要做其他事情，可以使用 `run_background()`：

```python
wl.run_background()
# ... 执行其他操作 ...
wl.stop()
```

## 发送消息

```python
ok = wl.send(msg.from_user, "收到！")
if not ok:
    print("与该用户没有活跃会话")
```

如果该用户没有可用的 `context_token`，`send()` 返回 `False`。

## 发送媒体

统一的 `send()` 方法支持文本、图片、语音、文件和视频：

```python
# 图片
wl.send(user, image=img_data)

# 语音
wl.send(user, voice=audio_data)

# 文件（指定文件名）
wl.send(user, file=pdf_data, file_name="report.pdf")

# 视频
wl.send(user, video=vid_data)

# 文本 + 多张图片
wl.send(user, "看看这些照片", image=[img1, img2])
```

## 引用消息

当用户回复（引用）一条消息时，`msg.ref_msg` 包含被引用的内容：

```python
for msg in wl.recv():
    if msg.ref_msg:
        print(f"引用: {msg.ref_msg.text}")
    print(f"消息: {msg.text}")
```

## 输入状态指示

```python
wl.send_typing(user_id)
# ... 处理中 ...
wl.stop_typing(user_id)
```

## 上下文管理器

```python
with WeiLink() as wl:
    wl.login()
    messages = wl.recv()
```
