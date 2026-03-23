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

## 发送消息

```python
ok = wl.send(msg.from_user, "收到！")
if not ok:
    print("与该用户没有活跃会话")
```

如果该用户没有可用的 `context_token`，`send()` 返回 `False`。

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
