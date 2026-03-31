# Architecture

This page describes the internal architecture of WeiLink, including module structure, message routing, login flow, media handling, and the optional admin panel.

## Package Structure

The package is organized into three groups: the core SDK, the admin panel, and the server/MCP layer.

### Core SDK Modules

```mermaid
graph TB
    subgraph "weilink package"
        client["client.py<br/><i>WeiLink (public API)</i>"]
        models["models.py<br/><i>Message, BotInfo, MediaContent...</i>"]
        protocol["_protocol.py<br/><i>iLink HTTP API calls</i>"]
        cdn["_cdn.py<br/><i>CDN upload / download</i>"]
        crypto["_crypto.py<br/><i>AES encryption dispatch</i>"]
        aes_ssl["_aes_openssl.py<br/><i>ctypes + OpenSSL</i>"]
        aes_py["_aes.py<br/><i>Pure-Python AES fallback</i>"]
        qr["_qr.py<br/><i>QR code generation</i>"]
        store["_store.py<br/><i>SQLite message persistence</i>"]
        filelock["_filelock.py<br/><i>Cross-process file locks</i>"]
    end

    client --> protocol
    client --> cdn
    client --> models
    client --> store
    client --> filelock
    cdn --> crypto
    crypto --> aes_ssl
    crypto -.->|fallback| aes_py

    admin[/"weilink.admin"/]
    server[/"weilink.server"/]
    client --> admin
    admin -.-> client
    admin -.-> protocol
    admin -.-> qr
    server -.-> client

    classDef ext fill:#f5f5f5,stroke:#999,stroke-dasharray:5 5
    class admin,server ext
```

### Admin Panel Modules

```mermaid
graph TB
    subgraph "weilink.admin"
        admin_srv["server.py<br/><i>AdminServer (daemon thread)</i>"]
        admin_hdl["handlers.py<br/><i>REST API handlers</i>"]
        admin_stc["static.py<br/><i>HTML & locale loading</i>"]
    end

    admin_srv --> admin_hdl
    admin_hdl --> admin_stc

    client[/"client.py"/]
    protocol[/"_protocol.py"/]
    qr[/"_qr.py"/]

    client --> admin_srv
    admin_hdl --> client
    admin_hdl --> protocol
    admin_hdl --> qr

    classDef ext fill:#f5f5f5,stroke:#999,stroke-dasharray:5 5
    class client,protocol,qr ext
```

### Server & MCP Modules

```mermaid
graph TB
    subgraph "weilink.server"
        mcp_srv["app.py<br/><i>Tool definitions</i>"]
    end

    subgraph "toolregistry-server"
        tr["ToolRegistry<br/><i>Single tool registry</i>"]
        mcp_out["MCP transport<br/><i>stdio / sse / streamable-http</i>"]
        openapi_out["OpenAPI transport<br/><i>REST + Swagger UI</i>"]
    end

    mcp_srv --> tr
    tr --> mcp_out
    tr --> openapi_out

    client[/"client.py"/]
    mcp_srv --> client

    classDef ext fill:#f5f5f5,stroke:#999,stroke-dasharray:5 5
    class client ext
```

## Multi-Session Architecture

WeiLink supports multiple concurrent sessions. Each session represents a separate WeChat account registered with the bot.

```mermaid
graph LR
    subgraph "WeiLink Client"
        sessions["_sessions dict"]
        default["_default_session"]
    end

    subgraph "Session: default"
        s1_info["bot_info<br/>(bot_id, token, base_url)"]
        s1_ctx["context_tokens<br/>{user_id → token}"]
        s1_disk["token.json + contexts.json"]
    end

    subgraph "Session: work"
        s2_info["bot_info"]
        s2_ctx["context_tokens"]
        s2_disk["token.json + contexts.json"]
    end

    sessions --> s1_info
    sessions --> s2_info
    default --> s1_info
    s1_info --- s1_ctx
    s1_ctx --- s1_disk
    s2_info --- s2_ctx
    s2_ctx --- s2_disk
```

### Receive Flow

`recv()` polls **all active sessions in parallel** using a thread pool, merging results into a single message list. Each `Message` carries a `bot_id` field identifying which session it came from.

```mermaid
sequenceDiagram
    participant App as Application
    participant WL as WeiLink.recv()
    participant TP as ThreadPool
    participant S1 as Session "default"
    participant S2 as Session "work"
    participant API as iLink API

    App->>WL: recv(timeout=35)
    WL->>TP: submit _recv_session(S1)
    WL->>TP: submit _recv_session(S2)
    par
        S1->>API: get_updates(cursor, timeout)
        API-->>S1: messages + new cursor
    and
        S2->>API: get_updates(cursor, timeout)
        API-->>S2: messages + new cursor
    end
    TP-->>WL: merged messages
    WL-->>App: List[Message]
```

### Send Routing

`send()` **auto-routes** to the correct session based on which session most recently held a `context_token` for the target user. No manual session selection needed.

```mermaid
flowchart TD
    A["send(to=user_id)"] --> B{"Session with<br/>context_token?"}
    B -->|Found| C["Use that session"]
    B -->|Not found| D{"Any connected?"}
    D -->|Yes| C2["First connected"]
    D -->|No| E["RuntimeError"]
    C & C2 --> F["Upload media"]
    F --> G["send_message()"]
```

## Cross-Process File Locking

When multiple processes share the same data directory (e.g., an SDK script and a stdio MCP server both using `~/.weilink/`), WeiLink coordinates access using two `fcntl.flock()`-based file locks:

```mermaid
flowchart TD
    subgraph "Process A (SDK script)"
        A_recv["recv()"]
        A_send["send()"]
    end

    subgraph "Process B (MCP stdio)"
        B_recv["recv()"]
        B_send["send()"]
    end

    subgraph "~/.weilink/"
        poll_lock[".poll.lock<br/><i>non-blocking exclusive</i>"]
        data_lock[".data.lock<br/><i>blocking exclusive (brief)</i>"]
        files["token.json<br/>contexts.json"]
        db["messages.db<br/><i>(SQLite WAL)</i>"]
    end

    A_recv -->|"try_lock"| poll_lock
    B_recv -->|"try_lock (fails → SQLite fallback)"| poll_lock
    A_send -->|"lock"| data_lock
    B_send -->|"lock"| data_lock
    poll_lock -.-> files
    data_lock -.-> files
    A_recv -.->|"store()"| db
    B_recv -.->|"query_messages()"| db
```

| Lock | Scope | Behavior |
|------|-------|----------|
| `.poll.lock` | Entire `recv()` cycle | Non-blocking try-lock. If held by another process, `recv()` falls back to SQLite (when enabled) or returns `[]`. Prevents cursor divergence. |
| `.data.lock` | File read-modify-write | Blocking, held briefly (~ms). Serializes `token.json` / `contexts.json` access for both `recv()` and `send()`. |

**Key principle:** disk is the source of truth. Every `recv()` and `send()` re-reads state from disk under the data lock before acting, ensuring changes from other processes are visible.

**Atomic file writes:** All writes to `token.json`, `contexts.json`, and `.default_session` use a write-to-temp-then-`os.replace()` pattern, ensuring that a process crash mid-write never produces a corrupted file.

On Windows, file locking is skipped (no `fcntl`) and WeiLink operates as before.

### Cooperative Polling Fallback

When `message_store` is enabled and the poll lock is held by another process, `recv()` reads recent messages (last 60 seconds) from the SQLite store instead of returning an empty list. This allows secondary processes to observe messages without conflicting with the primary poller's cursor.

```mermaid
flowchart TD
    A["recv()"] --> B{"try_lock<br/>poll_lock"}
    B -->|acquired| C["Poll iLink API"]
    C --> D["Store messages<br/>to SQLite"]
    D --> E["Update cursor<br/>& context_tokens"]
    E --> F["Return messages"]
    B -->|"failed"| G{"message_store<br/>enabled?"}
    G -->|yes| H["Query SQLite<br/>(last 60s, direction=received)"]
    H --> I["Return messages<br/>(no state updates)"]
    G -->|no| J["Return []"]
```

No cursor or context-token updates occur during a fallback read — the messages were already fully processed when the primary poller stored them. This makes the fallback purely read-only and safe.

**Activation:** automatic when both conditions are true: the poll lock is held by another process, and `message_store` is enabled (`message_store=True`).

## Message Persistence (SQLite Store)

WeiLink includes an optional SQLite-backed message store that records all received and sent messages with full serialization (preserving CDN references for later media download).

```mermaid
flowchart LR
    recv["recv()"] -->|"store()"| db["messages.db<br/>(SQLite WAL)"]
    send["send()"] -->|"store_sent()"| db
    fallback["SQLite<br/>fallback"] -->|"query_messages()"| db
    history["history"] -->|"query()"| db
    download["download"] -->|"get_by_id()"| db
```

| Feature | Description |
|---------|-------------|
| **WAL mode** | Concurrent readers + single writer. Readers never block writers, and vice versa. |
| **Idempotent writes** | `INSERT OR IGNORE` on `message_id` prevents duplicates. |
| **Auto-pruning** | Configurable by age (default 30 days) and count (default 100,000). |
| **Thread-safe** | Internal write lock + SQLite's own locking. |
| **Cross-process safe** | SQLite WAL handles concurrent access from multiple processes. |

### Enabling

- **Server mode**: always enabled (`message_store=True` by default in server).
- **SDK mode**: opt-in via `WeiLink(message_store=True)` or `WeiLink(message_store="/path/to/messages.db")`.
- **Disabled** (default for SDK): single-client mode, no SQLite dependency at runtime.

### Multi-Client Coordination Summary

WeiLink supports multiple processes sharing the same data directory through four mechanisms:

1. **Poll lock** (`.poll.lock`): ensures only one process polls iLink at a time, preventing cursor divergence.
2. **Data lock** (`.data.lock`): serializes reads and writes to `token.json` and `contexts.json`.
3. **SQLite fallback**: when the poll lock is unavailable and SQLite persistence is enabled, secondary processes read recent messages from the database.
4. **Atomic writes**: all file writes use temp-file-then-rename to prevent corruption on crash.

## QR Code Login Flow

Login uses a QR code scanned by the WeChat mobile app. The flow works the same whether initiated from the terminal or the admin panel.

```mermaid
sequenceDiagram
    participant User as User / Browser
    participant WL as WeiLink / Admin
    participant API as iLink API
    participant Phone as WeChat App

    User->>WL: login() / POST /api/sessions/login
    WL->>API: get_qr_code()
    API-->>WL: {qrcode, qrcode_img_content}
    WL-->>User: Display QR code (terminal / SVG)

    loop Poll every 2-3s
        WL->>API: poll_qr_status(qrcode)
        API-->>WL: {status: "waiting"}
    end

    Phone->>API: Scan QR code
    WL->>API: poll_qr_status(qrcode)
    API-->>WL: {status: "scaned"}
    Phone->>API: Confirm login
    WL->>API: poll_qr_status(qrcode)
    API-->>WL: {status: "confirmed", bot_token, bot_id}
    WL->>WL: Store BotInfo, save token.json
    WL-->>User: Login success
```

## CDN Media Pipeline

Media (images, voice, files, video) is encrypted with AES-128-ECB before upload and decrypted after download. The encryption key is provided by the iLink API.

```mermaid
flowchart TB
    subgraph Upload
        direction LR
        A1[Raw bytes] --> A2["AES-128-ECB<br/>encrypt"]
        A2 --> A3["HTTP PUT<br/>CDN URL"]
        A3 --> A4["UploadedMedia"]
    end

    subgraph Download
        direction LR
        B1["MediaInfo"] --> B2["HTTP GET<br/>CDN URL"]
        B2 --> B3["AES-128-ECB<br/>decrypt"]
        B3 --> B4[Raw bytes]
    end
```

### AES Encryption Strategy

```mermaid
flowchart TD
    C1["_crypto.py"] --> C2{"OpenSSL available<br/>via ctypes?"}
    C2 -->|Yes| C3["_aes_openssl.py<br/>(native performance)"]
    C2 -->|No| C4["_aes.py<br/>(pure-Python fallback)"]
```

The library ships with **zero runtime dependencies**. AES encryption first tries to load OpenSSL via `ctypes` for native performance. If unavailable (e.g., on some minimal containers), it falls back to a vendored pure-Python AES implementation.

## Admin Panel Architecture

The admin panel is an optional web UI for managing sessions without terminal access. It runs as a daemon thread inside the WeiLink process.

```mermaid
graph TB
    subgraph "WeiLink Process"
        client["WeiLink Client"]
        subgraph "Admin Thread (daemon)"
            server["AdminServer<br/>(HTTPServer)"]
            handler["AdminRequestHandler"]
        end
    end

    browser["Browser"] -->|"HTTP"| server
    server --> handler
    handler -->|"Read sessions,<br/>status"| client
    handler -->|"Login, logout,<br/>rename (with lock)"| client
    handler -->|"QR code"| protocol["_protocol.py"]
    handler -->|"SVG generation"| qr["_qr.py"]
    handler -->|"HTML / locales"| static["static.py"]
```

### Admin API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Serve single-page admin UI |
| GET | `/api/status` | Version, connection status, session count |
| GET | `/api/sessions` | All sessions with user details |
| POST | `/api/sessions/login` | Start QR login flow |
| GET | `/api/sessions/login/status` | Poll QR scan status |
| POST | `/api/sessions/{name}/logout` | Log out a session |
| POST | `/api/sessions/{name}/rename` | Rename a session |
| GET | `/locales/{lang}.json` | Serve i18n locale file |

### Thread Safety

```mermaid
flowchart TD
    subgraph "No lock needed"
        R1["GET /api/status"]
        R2["GET /api/sessions"]
    end

    subgraph "Protected by threading.Lock"
        W1["Login confirmed"]
        W2["POST .../logout"]
        W3["POST .../rename"]
    end

    R1 & R2 -.->|"read-only"| sessions["_sessions dict"]
    W1 & W2 & W3 -->|"acquire lock"| lock["threading.Lock"]
    lock --> sessions
```

Read-only endpoints (status, sessions) access session data without locking. Write operations (login confirmation, logout, rename) are serialized through a `threading.Lock` to prevent race conditions.

## Dual-Mode Server Architecture

WeiLink uses [toolregistry-server](https://github.com/Oaklight/toolregistry) to expose bot tools via both **MCP** and **OpenAPI** protocols from a single set of tool definitions.

```mermaid
flowchart LR
    subgraph "weilink.server.app"
        tools["Tool functions<br/>(recv, send, download, ...)"]
        registry["ToolRegistry"]
    end

    subgraph "toolregistry-server"
        rt["RouteTable"]
        mcp["MCP Server<br/>(stdio / sse / streamable-http)"]
        openapi["OpenAPI App<br/>(FastAPI + Swagger UI)"]
    end

    tools --> registry
    registry --> rt
    rt --> mcp
    rt --> openapi

    mcp -->|"MCP protocol"| agent["AI Agent"]
    openapi -->|"REST API"| client["HTTP Client"]
```

Tools are defined once as async Python functions in `weilink.server.app`, registered into a `ToolRegistry`, and then served via either transport:

- **`weilink mcp`** — creates an MCP server using `toolregistry_server.mcp`
- **`weilink openapi`** — creates a FastAPI app using `toolregistry_server.openapi`

Both modes share the same global `WeiLink` client instance and message cache.
