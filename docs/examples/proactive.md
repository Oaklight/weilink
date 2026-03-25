# Proactive Messaging

These examples demonstrate sending messages proactively -- without waiting for a user to message first (once a `context_token` has been established).

## Proactive Text Sending

Waits for one incoming message to cache a `context_token`, then sends 3 consecutive text messages to that user.

See [`examples/test_proactive_send.py`](https://github.com/Oaklight/weilink/blob/master/examples/test_proactive_send.py) in the repository.

### Usage

```bash
python examples/test_proactive_send.py
```

### How It Works

1. Logs in and waits for one incoming message via `wl.recv()`.
2. The SDK automatically caches the `context_token` from that message.
3. Sends 3 text messages in a row to the same user using `wl.send()` -- no further `recv()` needed.

## Proactive Media Sending

Sends text, image, file (PDF), and video to a specific user using a persisted `context_token` -- no `recv()` call is needed at all.

See [`examples/test_proactive_media.py`](https://github.com/Oaklight/weilink/blob/master/examples/test_proactive_media.py) in the repository.

### Usage

```bash
python examples/test_proactive_media.py
```

!!! note
    This example hardcodes a target user ID and local file paths. Edit the `USER` variable and file paths in the script before running.

### How It Works

1. Logs in. Because the SDK persists `context_token` values across sessions, no `recv()` is needed if the user has previously messaged the bot.
2. Sends four media types in sequence: text, image, file, and video.
3. Each `wl.send()` call reads the local file into `bytes` and passes it via the appropriate keyword argument (`image=`, `file=`, `video=`).

## Key Features Demonstrated

- **context_token caching** -- the SDK automatically stores tokens so you can message users without waiting for them to message first.
- **context_token persistence** -- tokens survive across bot restarts, enabling fully proactive messaging.
- **Consecutive sends** -- multiple `wl.send()` calls work without interleaving `wl.recv()`.
- **Multimodal proactive sending** -- text, image, file, and video can all be sent proactively.
