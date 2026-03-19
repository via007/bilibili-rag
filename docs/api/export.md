# 导出 API

> 导出知识点为 Markdown 格式文件

## 目录

- [概述](#概述)
- [视频导出](#视频导出)
- [收藏夹导出](#收藏夹导出)
- [会话导出](#会话导出)
- [会话总结导出](#会话总结导出)
- [前端集成](#前端集成)

---

## 概述

| 分类 | 说明 |
|------|------|
| 视频导出 | 导出单个视频的内容 |
| 收藏夹导出 | 导出一个或多个收藏夹 |
| 会话导出 | 导出会话问答记录 |
| 会话总结导出 | AI 知识点提取，支持缓存 |

---

## 视频导出

### POST /export/video

导出单个视频的内容

**请求**
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

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| bvid | string | ✅ | 视频 BV 号 |
| format | string | - | `full`(完整) / `simple`(精简)，默认 full |

**响应**
```json
{
  "success": true,
  "filename": "video_BV1xxx_20260315.md",
  "content": "# 视频标题\n\n> 来源: B站 | ...",
  "size": 12345
}
```

---

## 收藏夹导出

### POST /export/folder

导出一个或多个收藏夹

**请求**
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

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| folder_ids | array[int] | ✅ | 收藏夹 ID 列表 |
| format | string | - | `full` / `simple`，默认 full |

**响应**
```json
{
  "success": true,
  "filename": "folders_3个_20260315.md",
  "content": "## 收藏夹1\n\n内容...\n\n---\n\n## 收藏夹2\n\n内容...",
  "size": 56789
}
```

---

## 会话导出

### POST /export/session

导出会话（问答格式）

**请求**
```http
POST /export/session
Content-Type: application/json
```

```json
{
  "chat_session_id": "session-xxx"
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| chat_session_id | string | ✅ | 会话 ID |

**响应**
```json
{
  "success": true,
  "filename": "session_xxx_20260315.md",
  "content": "# 会话标题\n\n## 对话记录\n\n### 用户\n问题...\n\n---\n\n### AI回答\n回答...",
  "size": 9999
}
```

---

## 会话总结导出

### GET /export/session-summary/{chat_session_id}

获取会话总结（优先返回缓存）

**路径参数**
| 参数 | 类型 | 说明 |
|------|------|------|
| chat_session_id | string | 会话 ID |

**响应**
```json
{
  "success": true,
  "has_cache": true,
  "data": {
    "content": "# 总结标题\n\n## 整体总结\n...",
    "version": 1,
    "source_video_count": 2,
    "message_count": 8,
    "created_at": "2026-03-15T10:00:00",
    "updated_at": "2026-03-15T10:00:00"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| has_cache | boolean | 是否有缓存 |
| data.version | int | 缓存版本号 |
| data.source_video_count | int | 关联视频数 |
| data.message_count | int | 对话轮次 |

---

### POST /export/session-summary/{chat_session_id}/refresh

重新生成会话总结

**路径参数**
| 参数 | 类型 | 说明 |
|------|------|------|
| chat_session_id | string | 会话 ID |

**请求**
```json
{
  "format": "full"
}
```

**响应**
```json
{
  "success": true,
  "regenerated": true,
  "data": {
    "content": "# 新总结\n\n...",
    "version": 2,
    "source_video_count": 2,
    "message_count": 10,
    "created_at": "2026-03-15T10:05:00",
    "updated_at": "2026-03-15T10:05:00"
  }
}
```

---

### DELETE /export/session-summary/{chat_session_id}

删除会话总结缓存

**响应**
```json
{
  "success": true,
  "message": "缓存已删除"
}
```

---

## 缓存机制

### 流程

```
用户点击导出
    ↓
检查缓存是否存在？
    ↓ 是 → 直接返回缓存
    ↓ 否 → 调用 LLM 生成 → 存入缓存 → 返回
```

### 刷新逻辑

- 用户点击"重新生成" → 删除旧缓存 → LLM 生成 → 新缓存
- 版本号自动 +1

### SessionSummary 表结构

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| chat_session_id | string | 会话 ID |
| content | text | Markdown 内容 |
| version | int | 版本号 |
| source_video_count | int | 关联视频数 |
| message_count | int | 对话轮次 |
| token_used | int | 消耗的 token |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |

---

## 前端集成

### API 调用示例

```typescript
import {
  exportVideo,
  exportFolder,
  exportSession,
  getSessionSummary,
  refreshSessionSummary,
  deleteSessionSummary
} from '@/lib/export';

// 导出视频
const video = await exportVideo('BV1xxx', 'full');

// 导出收藏夹
const folder = await exportFolder([1, 2], 'full');

// 导出会话
const session = await exportSession('session-id');

// 获取会话总结（缓存优先）
const summary = await getSessionSummary('session-id');

// 重新生成
const newSummary = await refreshSessionSummary('session-id', 'full');

// 删除缓存
await deleteSessionSummary('session-id');
```

### UI 组件

- `ExportModal` - 导出预览弹窗
- 支持缓存状态显示
- 支持"重新生成"按钮

---

## 错误处理

| 错误 | 说明 |
|------|------|
| `会话不存在` | chat_session_id 无效 |
| `会话中没有 AI 回答` | 无法生成总结 |
| `导出失败` | 服务器内部错误 |
