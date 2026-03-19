# 会话管理 API

> 会话 CRUD、消息列表

---

## 目录

- [获取会话列表](#获取会话列表)
- [创建会话](#创建会话)
- [获取会话详情](#获取会话详情)
- [更新会话](#更新会话)
- [删除会话](#删除会话)
- [获取消息列表](#获取消息列表)
- [搜索会话](#搜索会话)

---

## 获取会话列表

### GET /conversation/list

获取当前用户的所有会话

**查询参数**
| 参数 | 类型 | 说明 |
|------|------|------|
| page | int | 页码 |
| page_size | int | 每页数量 |

**响应**
```json
{
  "sessions": [
    {
      "chat_session_id": "xxx",
      "title": "会话标题",
      "message_count": 10,
      "last_message_at": "2026-03-15T10:00:00"
    }
  ],
  "total": 100
}
```

---

## 创建会话

### POST /conversation/create

创建新会话

**请求**
```json
{
  "title": "新会话",
  "folder_ids": [1, 2]
}
```

**响应**
```json
{
  "chat_session_id": "xxx",
  "title": "新会话"
}
```

---

## 获取会话详情

### GET /conversation/{chat_session_id}

获取单个会话信息

**响应**
```json
{
  "chat_session_id": "xxx",
  "title": "会话标题",
  "folder_ids": [1, 2],
  "message_count": 10,
  "created_at": "2026-03-15T10:00:00"
}
```

---

## 更新会话

### PUT /conversation/{chat_session_id}

更新会话信息

**请求**
```json
{
  "title": "新标题"
}
```

---

## 删除会话

### DELETE /conversation/{chat_session_id}

删除会话（软删除）

---

## 获取消息列表

### GET /conversation/{chat_session_id}/messages

获取会话的所有消息

**响应**
```json
{
  "messages": [
    {
      "id": 1,
      "role": "user",
      "content": "问题内容",
      "created_at": "2026-03-15T10:00:00"
    },
    {
      "id": 2,
      "role": "assistant",
      "content": "回答内容",
      "sources": [...],
      "created_at": "2026-03-15T10:00:01"
    }
  ]
}
```

---

## 搜索会话

### GET /conversation/search

搜索会话标题

**查询参数**
| 参数 | 类型 | 说明 |
|------|------|------|
| q | string | 搜索关键词 |

**响应**
```json
{
  "sessions": [...]
}
```
