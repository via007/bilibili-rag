# Bilibili RAG API 文档

本目录包含 Bilibili RAG 知识库系统的完整 API 文档。

## 文件结构

```
api/
├── README.md           # 本文档
├── openapi.yaml        # OpenAPI 3.0 规范文档
└── swagger-ui.html     # Swagger UI 本地查看器
```

## 快速开始

### 方式一：使用本地 Swagger UI

直接用浏览器打开 `swagger-ui.html` 文件即可查看 API 文档。

> 注意：由于浏览器安全策略，建议通过 HTTP 服务器访问

```bash
# 使用 Python 启动简单服务器
cd api
python -m http.server 8080

# 或使用 Node.js
npx serve .
```

然后访问 http://localhost:8080/swagger-ui.html

### 方式二：使用在线编辑器

1. 访问 https://editor.swagger.io
2. 点击 "File" -> "Import URL"
3. 输入 `http://localhost:8000/openapi.yaml` 或直接粘贴 `openapi.yaml` 内容

### 方式三：集成到 FastAPI

如果你的 FastAPI 应用已启用 OpenAPI 文档，可以直接访问：

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## API 概览

### 认证 (`/auth`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/auth/qrcode` | 生成登录二维码 |
| GET | `/auth/qrcode/poll/{qrcode_key}` | 轮询登录状态 |
| GET | `/auth/session/{session_id}` | 获取会话信息 |
| DELETE | `/auth/session/{session_id}` | 退出登录 |

### 对话 (`/chat`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chat/ask` | 智能问答（非流式） |
| POST | `/chat/ask/stream` | 流式智能问答（SSE） |
| POST | `/chat/search` | 搜索相关视频片段 |

### 收藏夹 (`/favorites`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/favorites/list` | 获取收藏夹列表 |
| GET | `/favorites/{media_id}/videos` | 获取收藏夹视频（分页） |
| GET | `/favorites/{media_id}/all-videos` | 获取所有视频 |
| POST | `/favorites/organize/preview` | 预览收藏夹整理 |
| POST | `/favorites/organize/execute` | 执行收藏夹整理 |
| POST | `/favorites/organize/clean-invalid` | 清理失效内容 |

### 知识库 (`/knowledge`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/knowledge/stats` | 获取知识库统计 |
| GET | `/knowledge/folders/status` | 获取收藏夹入库状态 |
| POST | `/knowledge/folders/sync` | 同步收藏夹到向量库 |
| POST | `/knowledge/build` | 构建知识库（后台任务） |
| GET | `/knowledge/build/status/{task_id}` | 获取构建任务状态 |
| DELETE | `/knowledge/clear` | 清空知识库 |
| DELETE | `/knowledge/video/{bvid}` | 删除单个视频 |

### ASR 分P转写 (`/asr`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/asr` | 创建 ASR 任务（转写分P音频） |
| GET | `/asr/{task_id}` | 查询 ASR 任务状态 |
| GET | `/asr/content/{bvid}/{page}` | 获取某 P 的转写内容 |
| PUT | `/asr/content/{bvid}/{page}` | 更新某 P 的转写内容 |
| POST | `/asr/retry` | 重新执行 ASR 任务 |

### 分P向量化 (`/vec/page`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/vec/page` | 创建分P向量化任务 |
| GET | `/vec/page/{task_id}` | 查询向量化任务状态 |
| POST | `/vec/page/re-vector` | 重新向量化（覆盖已有） |
| GET | `/vec/page/status/{bvid}/{page}` | 查询某 P 的向量状态 |

---

## 认证流程

### 1. 扫码登录

```
1. 调用 GET /auth/qrcode 获取二维码
2. 展示二维码给用户扫码
3. 调用 GET /auth/qrcode/poll/{qrcode_key} 轮询状态
4. 状态变为 "confirmed" 时，保存返回的 session_id
```

### 2. 使用 session

在后续请求中，通过 **query 参数**携带 `session_id`：

```
GET /favorites/list?session_id=abc123-def456
```

---

## SSE 流式响应

`/chat/ask/stream` 接口使用 Server-Sent Events，返回格式如下：

```
data: 你好
data: ，
data: 欢迎
data: 使用
...
data: [[SOURCES_JSON]][{"bvid":"BV1xx411c7mD","title":"机器学习教程","url":"..."}]
```

最后一条消息以 `[[SOURCES_JSON]]` 开头，包含来源信息。

### 前端 SSE 消费规范

```typescript
// 必须处理四种事件
eventSource.onmessage = (event) => {
    const data = event.data;
    if (data.startsWith("[[SOURCES_JSON]]")) {
        // 解析来源信息
        const sources = JSON.parse(data.replace("[[SOURCES_JSON]]", ""));
    } else {
        // 追加到消息气泡
        appendText(data);
    }
};
```

---

## 路由策略说明

对话接口采用智能路由策略：

| 路由 | 说明 | 使用场景 |
|------|------|----------|
| `direct` | 直接回答 | 寒暄、闲聊、通用问题 |
| `db_list` | 列表回答 | "有哪些"、"清单"、"目录"类问题 |
| `db_content` | 内容总结 | "总结"、"概述"、"分析"类问题 |
| `vector` | 向量检索+RAG | 具体主题问题，需要检索相关内容 |

路由决策流程：
1. 优先尝试 LLM 路由判断
2. LLM 失败时使用规则路由兜底
3. 无数据时返回引导性兜底回答
4. 向量检索无结果时返回 fallback 回答

---

## ASR 任务说明

### 创建 ASR 任务

```bash
POST /asr
Content-Type: application/json

{
    "bvid": "BV1xx411c7mD",
    "page": 1,
    "cid": 12345678
}
```

### 任务状态流转

```
pending → processing → completed
                 ↘ failed（可重试）
```

### 获取转写结果

```bash
GET /asr/content/{bvid}/{page}
```

返回已转写的文本内容，支持 Markdown 格式。

---

## 分P向量化说明

### 创建向量化任务

```bash
POST /vec/page
Content-Type: application/json

{
    "bvid": "BV1xx411c7mD",
    "page": 1,
    "title": "P1: 课程介绍"
}
```

### 状态查询

```bash
GET /vec/page/status/{bvid}/{page}
```

返回该 P 的向量化状态：`pending` / `processing` / `done` / `failed`

---

## 错误处理

所有接口在出错时返回统一的错误格式：

```json
{
    "detail": "错误描述信息"
}
```

### HTTP 状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 401 | 未登录或会话过期 |
| 404 | 资源不存在 |
| 409 | 资源冲突（如重复创建） |
| 422 | 请求体格式错误 |
| 500 | 服务器内部错误 |

### 常见错误场景

| 错误信息 | 原因 | 解决方案 |
|----------|------|----------|
| `未配置 LLM API Key` | 环境变量未设置 | 检查 `.env` 中的 `DASHSCOPE_API_KEY` |
| `会话已过期` | `session_id` 无效或过期 | 重新扫码登录 |
| `未检索到相关内容` | 知识库为空或范围不对 | 先同步收藏夹，或扩大搜索范围 |
| `ASR 失败` | 音频不可达或识别失败 | 检查 ffmpeg 安装，或重试 |

---

## 数据一致性原则

### 单一数据源

| 数据 | 唯一来源 |
|------|---------|
| 收藏夹列表 | B站 API |
| 视频内容 | `video_cache` 表 |
| 向量数据 | ChromaDB |
| 用户 session | SQLite + 内存缓存 |

### 删除规则

```
一个 bvid 不再属于任何收藏夹 → 才可删除其向量数据
```

### 防误删机制

```
B站返回空列表 ≠ 本地清空
```

原因：可能是网络问题 / API 限流，不能信任空返回。

---

## 日志与排查

### 日志位置

```
logs/app.log          # 应用日志（10MB 轮转，保留 7 天）
```

### 排查链路

```
1. logs/app.log                          → 查看错误堆栈
2. SQLite: video_cache / favorite_videos → 确认数据是否写入
3. ChromaDB: collection 是否存在 & vector count > 0
4. API 参数: session_id / folder_ids 是否正确传递
```

---

## 更新日志

| 日期 | 版本 | 变更内容 |
|------|------|----------|
| 2026-04 | v1.2.0 | 新增分P视频 ASR 和向量化接口 (`/asr/*`, `/vec/page/*`) |
| 2026-04 | v1.2.0 | 新增 Agentic RAG 查询重写能力 |
| 2026-04 | v1.2.0 | 集成 LangSmith 自动追踪 |
| 2026-03 | v1.1.0 | 新增收藏夹整理功能（预览/执行/清理） |
| 2026-03 | v1.1.0 | 新增后台知识库构建任务 (`/knowledge/build`) |
| 2026-03 | v1.0.0 | 初始版本，支持完整 API 文档 |

---

## 相关文档

- [项目 README](../README.md)
- [架构文档](../architecture/app/00-overview.md)
- [OpenAPI 规范](./openapi.yaml)
