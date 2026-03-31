# 多会话

WeiLink 支持将一个 bot 同时注册到多个微信账号。每次注册创建一个独立的**会话**，拥有各自的凭证和消息流。

## 使用场景

- 客服 bot 通过多个微信账号服务不同用户群
- 开发测试时使用不同微信账号
- 将用户分组到不同的微信运营账号

!!! note "平台限制"
    一个微信账号同一时间只能绑定**一个 bot**。扫描新 bot 的二维码会断开之前的 bot 连接。多会话需要**不同的微信账号**分别扫码，而不是同一个账号重复扫码。

## 基本用法

```python
from weilink import WeiLink

wl = WeiLink()

# 第一个微信账号扫码
wl.login(name="account_a")

# 第二个微信账号扫新的二维码
wl.login(name="account_b")

print(wl.sessions)   # ['default', 'account_a', 'account_b']
print(wl.bot_ids)     # {'account_a': '...@im.bot', 'account_b': '...@im.bot'}
```

## 接收消息

`recv()` 自动并发轮询所有活跃会话。每条消息包含 `bot_id`，可以知道是哪个会话收到的：

```python
messages = wl.recv()
for msg in messages:
    print(f"[{msg.bot_id}] {msg.from_user}: {msg.text}")
```

## 发送消息

`send()` 自动路由到拥有目标用户 `context_token` 的会话，无需手动指定：

```python
# 自动使用收到过该用户消息的会话
wl.send("user@im.wechat", "你好！")
```

如果多个会话都有同一个用户的 token，使用时间戳最新的那个。

## 会话管理

### 重命名会话

```python
# 重命名默认会话
wl.rename_session("default", "main_account")
```

### 登出

```python
# 移除会话及其持久化的凭证
wl.logout("account_b")
```

### 属性

| 属性 | 描述 |
|------|------|
| `sessions` | 所有会话名称列表 |
| `bot_ids` | `{名称: bot_id}` 字典，仅包含已连接的会话 |
| `bot_id` | 默认会话的 bot_id（向后兼容） |
| `is_connected` | 任一会话已连接时返回 `True` |

## 文件存储

会话存储在基础路径下（默认 `~/.weilink/`）：

```
~/.weilink/
├── default/
│   ├── token.json      # 默认会话
│   └── contexts.json
├── account_a/
│   ├── token.json
│   └── contexts.json
└── account_b/
    ├── token.json
    └── contexts.json
```

如需运行多个独立的 bot 应用，使用不同的基础路径：

```python
bot_a = WeiLink(base_path="~/.weilink-app-a")
bot_b = WeiLink(base_path="~/.weilink-app-b")
```

!!! info "跨进程安全"
    多个进程共享同一基础路径时（例如 SDK 脚本和 stdio MCP 服务器），通过文件锁协调访问。同一时刻只有一个进程可以轮询消息，另一个的 `recv()` 返回空列表。两者均可并发 `send()`。详见 [架构 > 跨进程文件锁](../architecture.md#跨进程文件锁)。

## 向后兼容

所有现有的单会话代码无需修改即可使用。`login()` 不传 `name` 时使用默认会话：

```python
wl = WeiLink()
wl.login()          # 和以前一样 — 使用默认会话
wl.recv()           # 轮询默认会话
wl.send(to, text)   # 通过默认会话发送
```

!!! note "从平铺布局自动迁移"
    v0.5.0 之前，默认会话的文件直接存放在 `base_path/` 下（如 `~/.weilink/token.json`）。从 v0.5.0 起，所有会话（包括默认会话）均使用子目录（`~/.weilink/default/`）。首次加载时，WeiLink 会自动将已有的平铺布局迁移到新结构，无需手动操作。
