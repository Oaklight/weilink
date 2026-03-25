# Simple Echo Bot

A minimal echo bot with zero external dependencies. It receives text messages and echoes them back.

See [`examples/simple_echo.py`](https://github.com/Oaklight/weilink/blob/master/examples/simple_echo.py) in the repository.

## Usage

```bash
python examples/simple_echo.py
```

## How It Works

1. Creates a `WeiLink` instance and logs in via QR code.
2. Enters a polling loop with `wl.recv(timeout=35.0)`.
3. For each incoming text message, replies with `"Echo: <text>"` using `wl.send()`.

## Key Features Demonstrated

- **Login flow** -- `WeiLink()` + `wl.login()` to authenticate.
- **Long-polling** -- `wl.recv(timeout=...)` blocks until messages arrive or the timeout elapses.
- **Sending text** -- `wl.send(user, text)` sends a plain text reply.
- **Graceful shutdown** -- catches `KeyboardInterrupt` and calls `wl.close()`.
