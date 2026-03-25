# Multi-Session

WeiLink supports registering one bot with multiple WeChat accounts simultaneously. Each registration creates an independent **session** with its own credentials and message stream.

## Use Cases

- A customer service bot serving users from multiple WeChat accounts
- Testing with different WeChat accounts in development
- Separating user groups across different WeChat operators

!!! note "Platform Limitation"
    One WeChat account can only bind to **one bot** at a time. Scanning a new bot's QR code will disconnect the previous bot. Multi-session requires **different WeChat accounts**, not the same account scanning multiple times.

## Basic Usage

```python
from weilink import WeiLink

wl = WeiLink()

# First WeChat account scans the QR code
wl.login(name="account_a")

# Second WeChat account scans a new QR code
wl.login(name="account_b")

print(wl.sessions)   # ['default', 'account_a', 'account_b']
print(wl.bot_ids)     # {'account_a': '...@im.bot', 'account_b': '...@im.bot'}
```

## Receiving Messages

`recv()` automatically polls all active sessions concurrently. Each message includes `bot_id` so you know which session received it:

```python
messages = wl.recv()
for msg in messages:
    print(f"[{msg.bot_id}] {msg.from_user}: {msg.text}")
```

## Sending Messages

`send()` automatically routes to the session that has a `context_token` for the target user. No manual session selection is needed:

```python
# Automatically uses whichever session received a message from this user
wl.send("user@im.wechat", "Hello!")
```

If multiple sessions have a token for the same user, the one with the most recent timestamp is used.

## Session Management

### Renaming Sessions

```python
# Rename the default session
wl.rename_session("default", "main_account")
```

### Logging Out

```python
# Remove a session and its persisted credentials
wl.logout("account_b")
```

### Properties

| Property | Description |
|----------|-------------|
| `sessions` | List of all session names |
| `bot_ids` | Dict of `{name: bot_id}` for connected sessions |
| `bot_id` | Default session's bot_id (backward compat) |
| `is_connected` | `True` if any session is connected |

## File Storage

Sessions are stored under the base path (`~/.weilink/` by default):

```
~/.weilink/
├── token.json          # default session
├── contexts.json
├── account_a/
│   ├── token.json
│   └── contexts.json
└── account_b/
    ├── token.json
    └── contexts.json
```

To run multiple independent bot applications, use separate base paths:

```python
bot_a = WeiLink(base_path="~/.weilink-app-a")
bot_b = WeiLink(base_path="~/.weilink-app-b")
```

## Backward Compatibility

All existing single-session code works unchanged. When `name` is omitted from `login()`, the default session is used:

```python
wl = WeiLink()
wl.login()          # same as before — uses default session
wl.recv()           # polls the default session
wl.send(to, text)   # sends via default session
```
