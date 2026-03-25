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
    end

    subgraph "weilink.admin"
        admin_srv["server.py<br/><i>AdminServer（守护线程）</i>"]
        admin_hdl["handlers.py<br/><i>REST API 处理器</i>"]
        admin_stc["static.py<br/><i>HTML 与多语言加载</i>"]
    end

    subgraph "weilink.mcp"
        mcp_srv["server.py<br/><i>工具定义</i>"]
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
    subgraph "weilink.mcp.server"
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

工具以异步 Python 函数形式定义在 `weilink.mcp.server` 中，注册到 `ToolRegistry`，然后通过任一传输方式提供服务：

- **`weilink mcp`** — 使用 `toolregistry_server.mcp` 创建 MCP 服务器
- **`weilink openapi`** — 使用 `toolregistry_server.openapi` 创建 FastAPI 应用

两种模式共享同一个全局 `WeiLink` 客户端实例和消息缓存。
