# 更新日志

## v0.2.0 (2026-03-24)

- 新增多模态消息支持 — `send()` 现接受 `image`、`voice`、`file`、`video` 参数（单条或列表批量发送）
- 新增媒体下载 — `download()` 获取收到的图片/语音/文件/视频内容
- `pycryptodome` 升级为核心依赖，用于 AES-128-ECB 媒体加密
- 重启后持久化 context_tokens 以支持主动发消息
- 修复 CDN 上传：5xx 重试、修正响应头、URL 编码对齐 JS `encodeURIComponent`
- 修复图片解密密钥选择
- 新增示例：`media_echo.py`、`test_proactive_send.py`、`test_proactive_media.py`

## v0.1.0 (2026-03-23)

- 初始版本发布
- 二维码登录与凭证持久化
- 长轮询消息接收
- 文本消息发送与自动 context_token 管理
- 输入状态指示支持
