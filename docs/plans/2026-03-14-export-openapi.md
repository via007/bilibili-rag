# 导出 API OpenAPI 文档

> 日期: 2026-03-14

---

## 1. 视频导出

### POST /export/video

导出单个视频内容

**请求**:
```http
POST /export/video
Content-Type: application/json
```

```json
{
  "bvid": "BV1xxx",
  "format": "full"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| bvid | string | 是 | 视频 BV 号 |
| format | string | 否 | 格式: `full`(默认) / `simple` |

**响应** (200):
```json
{
  "success": true,
  "filename": "video_BV1xxx_20260314.md",
  "content": "# 视频标题\n\n> 来源: B站 | ...",
  "size": 12345
}
```

---

## 2. 收藏夹导出

### POST /export/folder

导出一个或多个收藏夹

**请求**:
```http
POST /export/folder
Content-Type: application/json
```

```json
{
  "folder_ids": [1, 2, 3],
  "format": "full"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| folder_ids | array[int] | 是 | 收藏夹 ID 列表 |
| format | string | 否 | 格式: `full`(默认) / `simple` |

**响应** (200):
```json
{
  "success": true,
  "filename": "folders_3个_20260314.md",
  "content": "## 收藏夹1\n\n内容...\n\n---\n\n## 收藏夹2\n\n内容...",
  "size": 56789
}
```

---

## 3. 会话导出

### POST /export/session

导出会话（问答格式）

**请求**:
```http
POST /export/session
Content-Type: application/json
```

```json
{
  "chat_session_id": "xxx"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| chat_session_id | string | 是 | 会话 ID |

**响应** (200):
```json
{
  "success": true,
  "filename": "session_xxx_20260314.md",
  "content": "# 会话标题\n\n## 对话记录\n\n### 用户\n问题...\n\n---\n\n### AI回答\n回答...",
  "size": 9999
}
```

---

## 4. 会话总结导出（缓存优先）

### GET /export/session-summary/{chat_session_id}

获取会话总结（优先返回缓存）

**路径参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| chat_session_id | string | 会话 ID |

**响应** (200):
```json
{
  "success": true,
  "has_cache": true,
  "data": {
    "content": "# 总结标题\n\n## 整体总结\n...",
    "version": 1,
    "source_video_count": 2,
    "message_count": 8,
    "created_at": "2026-03-14T10:00:00",
    "updated_at": "2026-03-14T10:00:00"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| has_cache | boolean | 是否有缓存 |
| data.content | string | Markdown 内容 |
| data.version | int | 缓存版本号 |
| data.source_video_count | int | 关联视频数 |
| data.message_count | int | 对话轮次 |
| data.created_at | string | 创建时间 |
| data.updated_at | string | 更新时间 |

**错误** (404):
```json
{
  "detail": "会话不存在: xxx"
}
```

---

### POST /export/session-summary/{chat_session_id}/refresh

重新生成会话总结

**路径参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| chat_session_id | string | 会话 ID |

**请求**:
```http
POST /export/session-summary/{chat_session_id}/refresh
Content-Type: application/json
```

```json
{
  "format": "full"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| format | string | 否 | 格式: `full`(默认) / `simple` |

**响应** (200):
```json
{
  "success": true,
  "regenerated": true,
  "data": {
    "content": "# 新总结\n\n...",
    "version": 2,
    "source_video_count": 2,
    "message_count": 10,
    "created_at": "2026-03-14T10:05:00",
    "updated_at": "2026-03-14T10:05:00"
  }
}
```

---

### DELETE /export/session-summary/{chat_session_id}

删除会话总结缓存

**路径参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| chat_session_id | string | 会话 ID |

**响应** (200):
```json
{
  "success": true,
  "message": "缓存已删除"
}
```

---

## 5. 通用响应格式

### 成功
```json
{
  "success": true,
  "filename": "xxx.md",
  "content": "...",
  "size": 12345
}
```

### 错误
```json
{
  "detail": "错误信息"
}
```

**状态码**:
| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |

---

## 6. 前端调用示例

```typescript
// 导出视频
const videoData = await exportVideo('BV1xxx', 'full');

// 导出收藏夹
const folderData = await exportFolder([1, 2], 'full');

// 导出会话
const sessionData = await exportSession('session-id');

// 获取会话总结（缓存优先）
const summary = await getSessionSummary('session-id');

// 重新生成总结
const newSummary = await refreshSessionSummary('session-id', 'full');

// 删除缓存
await deleteSessionSummary('session-id');
```
