# WeiLink

轻量级 Python SDK，用于微信 iLink Bot 协议。

[English](README_en.md)

## 特性

- **零依赖** — 纯 Python 标准库，无第三方依赖
- **消息队列语义** — `login()` / `send()` / `recv()` 三个核心接口
- **状态自动管理** — `context_token`、sync cursor 内部缓存，调用方无需关心
- **凭证持久化** — 扫码登录后 token 自动保存，重启免登录
- **输入状态** — 支持"对方正在输入中"指示器

## 安装

```bash
pip install weilink
```

## 快速开始

```python
from weilink import WeiLink

wl = WeiLink()
wl.login()

# 接收消息
messages = wl.recv()
for msg in messages:
    print(f"{msg.from_user}: {msg.text}")

# 回复
wl.send(msg.from_user, "收到！")

wl.close()
```

## 工作原理

WeiLink 封装了微信 iLink Bot 协议（ClawBot 插件的底层协议），提供消息队列式的收发接口：

```
login()  →  扫码获取凭证（持久化）
recv()   →  长轮询收消息（35 秒超时）
send()   →  回复消息（自动关联 context_token）
```

### 重要限制

- **不能主动发起对话** — 用户必须先给 ClawBot 发消息，bot 才能回复
- **24 小时窗口** — 用户超过 24 小时未发消息，bot 的消息会被丢弃
- **仅文本消息** — 当前版本不支持图片/文件/语音/视频
- **腾讯可随时终止服务** — 不建议将核心业务完全依赖此协议

## API

| 方法 | 说明 |
|------|------|
| `login(force=False)` | 扫码登录，已有凭证则自动复用 |
| `recv(timeout=35.0)` | 长轮询接收消息 |
| `send(to, text)` | 发送文本消息，返回 `bool` |
| `send_typing(to)` | 显示"正在输入" |
| `stop_typing(to)` | 取消"正在输入" |
| `close()` | 保存状态并清理 |
| `is_connected` | 是否已登录（属性） |
| `bot_id` | 当前 bot ID（属性） |

## 协议参考

- [iLink Bot API 技术解析](https://github.com/hao-ji-xing/openclaw-weixin/blob/main/weixin-bot-api.md)
- [官方 npm 包](https://www.npmjs.com/package/@tencent-weixin/openclaw-weixin)
- [微信 ClawBot 功能使用条款](https://github.com/hao-ji-xing/openclaw-weixin/blob/main/protocol.md)

## 致谢

- QR 码终端渲染基于 [nayuki/QR-Code-generator](https://github.com/nayuki/QR-Code-generator)（MIT 许可）

## License

[MIT](LICENSE)
