# Callback Echo Bot

An event-driven echo bot using the callback API. Functionally identical to the [Simple Echo Bot](simple_echo.md) but replaces the manual polling loop with `on_message` and `run_forever`.

See [`examples/callback_echo.py`](https://github.com/Oaklight/weilink/blob/master/examples/callback_echo.py) in the repository.

## Usage

```bash
python examples/callback_echo.py
```

## How It Works

1. Creates a `WeiLink` instance and logs in via QR code.
2. Registers a handler with `@wl.on_message` -- the handler is called for every incoming message.
3. Calls `wl.run_forever()`, which starts a background polling thread and blocks the main thread.
4. On `Ctrl+C` or `SIGTERM`, `run_forever()` stops the dispatcher and calls `wl.close()` automatically.

## Key Features Demonstrated

- **Decorator-based handlers** -- `@wl.on_message` registers a callback, no manual `recv()` loop needed.
- **Blocking dispatcher** -- `run_forever()` handles polling, signal trapping, and cleanup.
- **Automatic shutdown** -- `Ctrl+C` triggers a graceful stop; no `try/finally` boilerplate required.

## Polling vs Callback

| Aspect | Polling (`recv()` loop) | Callback (`on_message`) |
|--------|------------------------|------------------------|
| Control flow | You own the loop | Framework owns the loop |
| Boilerplate | `while True` + `try/finally` | Decorator + `run_forever()` |
| Best for | Custom scheduling, batching | Simple request/response bots |
