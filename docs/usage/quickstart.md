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

## Callback Mode

Instead of a manual `recv()` loop, you can register handlers and let the SDK poll for you:

```python
@wl.on_message
def handle(msg):
    print(f"{msg.from_user}: {msg.text}")
    wl.send(msg.from_user, "Got it!")

wl.run_forever()  # blocks until Ctrl+C
```

Use `run_background()` if you need the main thread for other work:

```python
wl.run_background()
# ... do other things ...
wl.stop()
```

## Send Messages

```python
ok = wl.send(msg.from_user, "Got it!")
if not ok:
    print("No active session with this user")
```

`send()` returns `False` if no `context_token` is available for the user.

## Send Media

The unified `send()` method supports text, images, voice, files, and video:

```python
# Image
wl.send(user, image=img_data)

# Voice
wl.send(user, voice=audio_data)

# File (with filename)
wl.send(user, file=pdf_data, file_name="report.pdf")

# Video
wl.send(user, video=vid_data)

# Text + multiple images
wl.send(user, "Check these photos", image=[img1, img2])
```

## Quoted Messages

When a user replies to a previous message, `msg.ref_msg` contains the quoted content:

```python
for msg in wl.recv():
    if msg.ref_msg:
        print(f"Replying to: {msg.ref_msg.text}")
    print(f"Message: {msg.text}")
```

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
