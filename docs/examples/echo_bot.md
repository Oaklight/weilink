# Echo Bot Example

A simple bot that forwards messages to an OpenAI-compatible API and replies.

See [`examples/echo_bot.py`](https://github.com/Oaklight/weilink/blob/master/examples/echo_bot.py) in the repository.

## Usage

```bash
export OPENAI_API_KEY="your-key"
export OPENAI_BASE_URL="https://api.openai.com/v1"  # or any compatible endpoint
python examples/echo_bot.py
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | API key |
| `OPENAI_BASE_URL` | No | API endpoint (default: OpenAI) |
| `OPENAI_MODEL` | No | Model name (default: `gpt-4o-mini`) |
| `SYSTEM_PROMPT` | No | System prompt |
