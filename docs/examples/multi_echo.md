# Multi-Session Echo Bot

Demonstrates multi-session support: logs into two WeChat accounts on the same bot and echoes messages from all sessions.

See [`examples/multi_echo.py`](https://github.com/Oaklight/weilink/blob/master/examples/multi_echo.py) in the repository.

## Usage

```bash
python examples/multi_echo.py
```

You will be prompted to scan a QR code for each session.

## How It Works

1. Creates a single `WeiLink` instance.
2. Calls `wl.login(name="...")` twice with different session names -- each call triggers a separate QR code login for a different WeChat account.
3. `wl.recv()` returns messages from **all** active sessions in one call.
4. Each message carries a `msg.bot_id` field identifying which session it belongs to.

## Key Features Demonstrated

- **Multi-session login** -- calling `wl.login(name=...)` multiple times to register different WeChat accounts.
- **Unified receive** -- a single `wl.recv()` call aggregates messages across all sessions.
- **Session identification** -- using `msg.bot_id` to distinguish which session a message came from.
- **Session introspection** -- `wl.sessions` and `wl.bot_ids` list all active sessions and their bot IDs.
