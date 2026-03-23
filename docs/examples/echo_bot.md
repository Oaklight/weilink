# 回声机器人示例

一个简单的机器人，将收到的消息转发到 OpenAI 兼容 API 并回复。

参见仓库中的 [`examples/echo_bot.py`](https://github.com/Oaklight/weilink/blob/master/examples/echo_bot.py)。

## 使用方法

```bash
export OPENAI_API_KEY="your-key"
export OPENAI_BASE_URL="https://api.openai.com/v1"  # 或任何兼容的 API 端点
python examples/echo_bot.py
```

## 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `OPENAI_API_KEY` | 是 | API 密钥 |
| `OPENAI_BASE_URL` | 否 | API 端点（默认：OpenAI） |
| `OPENAI_MODEL` | 否 | 模型名称（默认：`gpt-4o-mini`） |
| `SYSTEM_PROMPT` | 否 | 系统提示词 |
