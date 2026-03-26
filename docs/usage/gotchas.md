# Tips & Gotchas

Practical tips and tricky parts discovered during development of the WeChat iLink Bot SDK.

## Platform Limitations

- **No proactive conversations** — The user must message the bot first. The bot can only reply to users who have an active context_token.
- **24-hour window** — If a user hasn't messaged the bot in 24 hours, messages sent by the bot are silently discarded by the platform. No error is returned.
- **`ret: -14` = session expired** — The bot's login session has expired. Call `login(force=True)` to re-authenticate.
- **`ret: -2` = request rejected** — Can mean: the context_token is expired, the 10-reply limit was reached, or the text exceeds 16 KiB. Wait for the user to send a new message to get a fresh token.

## Media & CDN

- **One message = one media item** — The protocol does not support sending multiple media items (e.g. image + text) in a single message. When you pass both `text` and `image` to `send()`, they are sent as separate messages automatically.
- **CDN uploads are user-bound** — When uploading to CDN, the `to_user_id` must be a valid user. Dummy user IDs cause `ret: -1`.
- **CDN references can be reused** — After `upload()`, the returned `UploadedMedia` can be passed to `send()` multiple times for the same user. This avoids re-uploading the same file. However, CDN expiry is undocumented — don't cache references long-term.
- **Video preview errors** — Re-uploading a downloaded video to CDN may fail with "probe preview error". Direct uploads from local files work fine.
- **Image AES key quirk** — For received images, the correct decryption key is in `image_item.aeskey` (raw hex), NOT `media.aes_key` (base64). The SDK handles this automatically.

## Message Delivery

- **Text size limit: 16 KiB UTF-8** — The server rejects text items exceeding 16 384 UTF-8 bytes (`ret: -2`). Note: the limit is on **byte length**, not character count — a message with 16 000 ASCII characters fits, but 6 000 Chinese characters (~18 000 bytes) does not. The SDK automatically splits long texts into multiple messages.
- **10 replies per context_token** — Each context_token allows at most 10 outbound messages. After that, `send()` returns `ret: -2`. The counter resets when the user sends a new message (which issues a fresh token). See [epiral/weixin-bot#3](https://github.com/epiral/weixin-bot/issues/3).
- **Batch delayed delivery** — Occasionally, `send()` returns success but messages arrive at the user's WeChat several minutes later in a batch. This is a WeChat / iLink server-side behavior, not an SDK bug. Using `auto_recv=True` on `send()` may partially mitigate this by refreshing context tokens before sending. Under investigation ([#2](https://github.com/Oaklight/weilink/issues/2)).

## Context Tokens

- **Tokens are per-user, not per-session** — Each user has their own context_token. Old tokens remain valid within the 24h window even after newer tokens are issued.
- **Persisted to `contexts.json`** — Context tokens are saved to `~/.weilink/contexts.json` (separate from `token.json`) with timestamps. Entries older than 24h are discarded on load.
- **Proactive messaging** — You can send messages to a user without first calling `recv()`, as long as a valid context_token exists (either from a previous session or loaded from disk).
