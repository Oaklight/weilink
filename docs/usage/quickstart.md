# Quick Start

## Login

```python
from weilink import WeiLink

wl = WeiLink()
wl.login()
```

A QR code URL will be printed. Scan it with WeChat to authorize.

Credentials are saved to `~/.weilink/token.json` and reused on next run.

## Receive Messages

```python
messages = wl.recv(timeout=35.0)
for msg in messages:
    print(f"{msg.from_user}: {msg.text}")
```

`recv()` blocks for up to 35 seconds (long-polling).

## Send Messages

```python
ok = wl.send(msg.from_user, "Got it!")
if not ok:
    print("No active session with this user")
```

`send()` returns `False` if no `context_token` is available for the user.

## Typing Indicator

```python
wl.send_typing(user_id)
# ... do work ...
wl.stop_typing(user_id)
```

## Context Manager

```python
with WeiLink() as wl:
    wl.login()
    messages = wl.recv()
```
