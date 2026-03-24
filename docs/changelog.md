# 更新日志

## 未发布

- 修复 CDN 上传失败：添加重试逻辑（5xx 错误最多重试 3 次）、修正响应头 (`x-encrypted-param`)、URL 编码对齐 JS `encodeURIComponent`
- 修复图片解密：优先使用 `image_item.aeskey`（原始 hex）而非 `media.aes_key`（base64）
- 重启后持久化 context_tokens 以支持主动发消息
- 添加主动发消息示例（`test_proactive_send.py`、`test_proactive_media.py`）
- `media_echo.py` 示例支持 `LOGLEVEL` 环境变量

## v0.1.0 (2026-03-23)

- 初始版本发布
- 二维码登录与凭证持久化
- 长轮询消息接收
- 文本消息发送与自动 context_token 管理
- 输入状态指示支持
