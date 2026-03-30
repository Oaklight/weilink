# 架构

本页介绍 WeiLink 的内部架构，包括模块结构、消息路由、登录流程、媒体处理及可选的管理面板。

## 包结构

```mermaid
graph TB
    subgraph "weilink 包"
        client["client.py<br/><i>WeiLink（公开 API）</i>"]
        models["models.py<br/><i>Message, BotInfo, MediaContent...</i>"]
        protocol["_protocol.py<br/><i>iLink HTTP API 调用</i>"]
        cdn["_cdn.py<br/><i>CDN 上传 / 下载</i>"]
        crypto["_crypto.py<br/><i>AES 加密调度</i>"]
        aes_ssl["_aes_openssl.py<br/><i>ctypes + OpenSSL</i>"]
        aes_py["_aes.py<br/><i>纯 Python AES 后备</i>"]
        qr["_qr.py<br/><i>二维码生成</i>"]
        store["_store.py<br/><i>SQLite 消息持久化</i>"]
        filelock["_filelock.py<br/><i>跨进程文件锁</i>"]
    end

    subgraph "weilink.admin"
        admin_srv["server.py<br/><i>AdminServer（守护线程）</i>"]
        admin_hdl["handlers.py<br/><i>REST API 处理器</i>"]
        admin_stc["static.py<br/><i>HTML 与多语言加载</i>"]
    end

    subgraph "weilink.server"
        mcp_srv["app.py<br/><i>工具定义</i>"]
    end

    subgraph "toolregistry-server"
        tr["ToolRegistry<br/><i>统一工具注册表</i>"]
        mcp_out["MCP 传输<br/><i>stdio / sse / streamable-http</i>"]
        openapi_out["OpenAPI 传输<br/><i>REST + Swagger UI</i>"]
    end

    client --> protocol
    client --> cdn
    client --> models
    client --> admin_srv
    client --> store
    client --> filelock
    cdn --> crypto
    crypto --> aes_ssl
    crypto -.->|后备| aes_py
    admin_hdl --> protocol
    admin_hdl --> qr
    admin_hdl --> client
    mcp_srv --> tr
    tr --> mcp_out
    tr --> openapi_out
    mcp_srv --> client
```

## 多会话架构

WeiLink 支持多个并发会话。每个会话代表一个独立的微信账号注册到机器人。

```mermaid
graph LR
    subgraph "WeiLink 客户端"
        sessions["_sessions 字典"]
        default["_default_session"]
    end

    subgraph "会话: default"
        s1_info["bot_info<br/>(bot_id, token, base_url)"]
        s1_ctx["context_tokens<br/>{user_id → token}"]
        s1_disk["token.json + contexts.json"]
    end

    subgraph "会话: work"
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

### 接收流程

`recv()` 使用线程池**并行轮询所有活跃会话**，将结果合并为统一的消息列表。每条 `Message` 都携带 `bot_id` 字段，标识它来自哪个会话。

```mermaid
sequenceDiagram
    participant App as 应用程序
    participant WL as WeiLink.recv()
    participant TP as 线程池
    participant S1 as 会话 "default"
    participant S2 as 会话 "work"
    participant API as iLink API

    App->>WL: recv(timeout=35)
    WL->>TP: 提交 _recv_session(S1)
    WL->>TP: 提交 _recv_session(S2)
    par
        S1->>API: get_updates(cursor, timeout)
        API-->>S1: 消息 + 新游标
    and
        S2->>API: get_updates(cursor, timeout)
        API-->>S2: 消息 + 新游标
    end
    TP-->>WL: 合并后的消息
    WL-->>App: List[Message]
```

### 发送路由

`send()` 根据目标用户最近的 `context_token` 所在会话**自动路由**到正确的会话。无需手动指定会话。

```mermaid
flowchart TD
    A["send(to=user_id)"] --> B{"持有该用户<br/>context_token？"}
    B -->|找到| C["使用该会话"]
    B -->|未找到| D{"有已连接会话？"}
    D -->|有| C2["第一个已连接"]
    D -->|无| E["RuntimeError"]
    C & C2 --> F["上传媒体"]
    F --> G["send_message()"]
```

## 跨进程文件锁

当多个进程共享同一数据目录时（例如 SDK 脚本和 stdio MCP 服务器同时使用 `~/.weilink/`），WeiLink 通过两把基于 `fcntl.flock()` 的文件锁协调访问：

```mermaid
flowchart TD
    subgraph "进程 A（SDK 脚本）"
        A_recv["recv()"]
        A_send["send()"]
    end

    subgraph "进程 B（MCP stdio）"
        B_recv["recv()"]
        B_send["send()"]
    end

    subgraph "~/.weilink/"
        poll_lock[".poll.lock<br/><i>非阻塞排他锁</i>"]
        data_lock[".data.lock<br/><i>阻塞排他锁（短暂持有）</i>"]
        files["token.json<br/>contexts.json"]
        db["messages.db<br/><i>(SQLite WAL)</i>"]
    end

    A_recv -->|"try_lock"| poll_lock
    B_recv -->|"try_lock（失败 → SQLite 降级）"| poll_lock
    A_send -->|"lock"| data_lock
    B_send -->|"lock"| data_lock
    poll_lock -.-> files
    data_lock -.-> files
    A_recv -.->|"store()"| db
    B_recv -.->|"query_messages()"| db
```

| 锁 | 作用范围 | 行为 |
|----|----------|------|
| `.poll.lock` | 整个 `recv()` 周期 | 非阻塞 try-lock。被其他进程持有时，`recv()` 降级从 SQLite 读取（如已启用），否则返回 `[]`。防止 cursor 分叉。 |
| `.data.lock` | 文件读-改-写 | 阻塞式，短暂持有（~毫秒级）。序列化 `token.json` / `contexts.json` 的访问，`recv()` 和 `send()` 均使用。 |

**核心原则：** 磁盘是唯一事实来源。每次 `recv()` 和 `send()` 在数据锁下重新从磁盘读取状态后再执行操作，确保其他进程的变更可见。

**原子文件写入：** 所有对 `token.json`、`contexts.json` 和 `.default_session` 的写入均使用"写临时文件 + `os.replace()`"模式，确保进程崩溃不会产生损坏的文件。

在 Windows 上，文件锁被跳过（无 `fcntl`），WeiLink 的行为与之前一致。

### Route C — 协作式轮询降级

当启用 `message_store` 且轮询锁被其他进程持有时，`recv()` 从 SQLite 存储中读取最近的消息（最近 60 秒），而不是返回空列表。这使得次级进程无需与主轮询者的 cursor 冲突即可获取消息。

```mermaid
flowchart TD
    A["recv()"] --> B{"try_lock<br/>poll_lock"}
    B -->|获取成功| C["轮询 iLink API"]
    C --> D["消息存入 SQLite"]
    D --> E["更新 cursor<br/>和 context_tokens"]
    E --> F["返回消息"]
    B -->|"获取失败"| G{"已启用<br/>message_store？"}
    G -->|是| H["查询 SQLite<br/>（最近 60 秒，仅接收方向）"]
    H --> I["返回消息<br/>（不更新状态）"]
    G -->|否| J["返回 []"]
```

降级读取期间不会更新 cursor 或 context_token — 这些消息在主轮询者存储时已完成处理。降级读取是纯只读操作，完全安全。

**激活条件：** 同时满足两个条件时自动启用：轮询锁被其他进程持有，且 `message_store` 已启用（`message_store=True`）。

## 消息持久化（SQLite 存储）

WeiLink 包含一个可选的 SQLite 消息存储后端，记录所有收发消息的完整序列化数据（保留 CDN 引用以便后续媒体下载）。

```mermaid
flowchart LR
    recv["recv()"] -->|"store()"| db["messages.db<br/>(SQLite WAL)"]
    send["send()"] -->|"store_sent()"| db
    fallback["Route C<br/>降级读取"] -->|"query_messages()"| db
    history["get_message_history"] -->|"query()"| db
    download["download_media"] -->|"get_by_id()"| db
```

| 特性 | 描述 |
|------|------|
| **WAL 模式** | 并发读者 + 单写者。读者不阻塞写者，写者不阻塞读者。 |
| **幂等写入** | 基于 `message_id` 的 `INSERT OR IGNORE`，防止重复写入。 |
| **自动清理** | 可配置按时间（默认 30 天）和条数（默认 10 万条）清理。 |
| **线程安全** | 内部写锁 + SQLite 自身锁机制。 |
| **跨进程安全** | SQLite WAL 模式处理多进程并发访问。 |

### 启用方式

- **Server 模式**：始终启用（server 中默认 `message_store=True`）。
- **SDK 模式**：通过 `WeiLink(message_store=True)` 或 `WeiLink(message_store="/path/to/messages.db")` 手动启用。
- **未启用**（SDK 默认）：单客户端模式，运行时无 SQLite 依赖。

### 多客户端协调总结

WeiLink 通过四种机制支持多个进程共享同一数据目录：

1. **轮询锁**（`.poll.lock`）：确保同一时间只有一个进程轮询 iLink，防止 cursor 分叉。
2. **数据锁**（`.data.lock`）：序列化对 `token.json` 和 `contexts.json` 的读写。
3. **Route C 降级读取**：当轮询锁不可用且 SQLite 持久化已启用时，次级进程从数据库读取最近的消息。
4. **原子写入**：所有文件写入使用临时文件 + 重命名模式，防止崩溃时文件损坏。

## 二维码登录流程

登录使用微信手机端扫描二维码完成。无论从终端还是管理面板发起，流程相同。

```mermaid
sequenceDiagram
    participant User as 用户 / 浏览器
    participant WL as WeiLink / 管理面板
    participant API as iLink API
    participant Phone as 微信 App

    User->>WL: login() / POST /api/sessions/login
    WL->>API: get_qr_code()
    API-->>WL: {qrcode, qrcode_img_content}
    WL-->>User: 显示二维码（终端 / SVG）

    loop 每 2-3 秒轮询
        WL->>API: poll_qr_status(qrcode)
        API-->>WL: {status: "waiting"}
    end

    Phone->>API: 扫描二维码
    WL->>API: poll_qr_status(qrcode)
    API-->>WL: {status: "scaned"}
    Phone->>API: 确认登录
    WL->>API: poll_qr_status(qrcode)
    API-->>WL: {status: "confirmed", bot_token, bot_id}
    WL->>WL: 存储 BotInfo，保存 token.json
    WL-->>User: 登录成功
```

## CDN 媒体管道

媒体文件（图片、语音、文件、视频）在上传前使用 AES-128-ECB 加密，下载后解密。加密密钥由 iLink API 提供。

```mermaid
flowchart TB
    subgraph 上传
        direction LR
        A1[原始字节] --> A2["AES-128-ECB<br/>加密"]
        A2 --> A3["HTTP PUT<br/>CDN URL"]
        A3 --> A4["UploadedMedia"]
    end

    subgraph 下载
        direction LR
        B1["MediaInfo"] --> B2["HTTP GET<br/>CDN URL"]
        B2 --> B3["AES-128-ECB<br/>解密"]
        B3 --> B4[原始字节]
    end
```

### AES 加密策略

```mermaid
flowchart TD
    C1["_crypto.py"] --> C2{"通过 ctypes<br/>可用 OpenSSL？"}
    C2 -->|是| C3["_aes_openssl.py<br/>（原生性能）"]
    C2 -->|否| C4["_aes.py<br/>（纯 Python 后备）"]
```

本库**零运行时依赖**。AES 加密首先尝试通过 `ctypes` 加载 OpenSSL 以获得原生性能。如果不可用（例如某些精简容器），则回退到内置的纯 Python AES 实现。

## 管理面板架构

管理面板是一个可选的 Web UI，用于在无需终端的情况下管理会话。它作为守护线程运行在 WeiLink 进程内部。

```mermaid
graph TB
    subgraph "WeiLink 进程"
        client["WeiLink 客户端"]
        subgraph "Admin 线程（守护）"
            server["AdminServer<br/>(HTTPServer)"]
            handler["AdminRequestHandler"]
        end
    end

    browser["浏览器"] -->|"HTTP"| server
    server --> handler
    handler -->|"读取会话、<br/>状态"| client
    handler -->|"登录、登出、<br/>重命名（加锁）"| client
    handler -->|"二维码"| protocol["_protocol.py"]
    handler -->|"SVG 生成"| qr["_qr.py"]
    handler -->|"HTML / 多语言"| static["static.py"]
```

### 管理面板 API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/` | 提供单页管理 UI |
| GET | `/api/status` | 版本、连接状态、会话数 |
| GET | `/api/sessions` | 所有会话及用户详情 |
| POST | `/api/sessions/login` | 启动二维码登录流程 |
| GET | `/api/sessions/login/status` | 轮询扫码状态 |
| POST | `/api/sessions/{name}/logout` | 登出会话 |
| POST | `/api/sessions/{name}/rename` | 重命名会话 |
| GET | `/locales/{lang}.json` | 提供国际化语言文件 |

### 线程安全

```mermaid
flowchart TD
    subgraph "无需加锁"
        R1["GET /api/status"]
        R2["GET /api/sessions"]
    end

    subgraph "由 threading.Lock 保护"
        W1["登录确认"]
        W2["POST .../logout"]
        W3["POST .../rename"]
    end

    R1 & R2 -.->|"只读"| sessions["_sessions 字典"]
    W1 & W2 & W3 -->|"获取锁"| lock["threading.Lock"]
    lock --> sessions
```

只读端点（状态、会话列表）无需加锁即可访问会话数据。写操作（登录确认、登出、重命名）通过 `threading.Lock` 串行化，防止竞态条件。

## 双模式服务器架构

WeiLink 使用 [toolregistry-server](https://github.com/Oaklight/toolregistry) 将 bot 工具通过 **MCP** 和 **OpenAPI** 两种协议暴露，基于同一套工具定义。

```mermaid
flowchart LR
    subgraph "weilink.server.app"
        tools["工具函数<br/>(recv, send, download, ...)"]
        registry["ToolRegistry"]
    end

    subgraph "toolregistry-server"
        rt["RouteTable"]
        mcp["MCP 服务器<br/>(stdio / sse / streamable-http)"]
        openapi["OpenAPI 应用<br/>(FastAPI + Swagger UI)"]
    end

    tools --> registry
    registry --> rt
    rt --> mcp
    rt --> openapi

    mcp -->|"MCP 协议"| agent["AI Agent"]
    openapi -->|"REST API"| client["HTTP 客户端"]
```

工具以异步 Python 函数形式定义在 `weilink.server.app` 中，注册到 `ToolRegistry`，然后通过任一传输方式提供服务：

- **`weilink mcp`** — 使用 `toolregistry_server.mcp` 创建 MCP 服务器
- **`weilink openapi`** — 使用 `toolregistry_server.openapi` 创建 FastAPI 应用

两种模式共享同一个全局 `WeiLink` 客户端实例和消息缓存。
