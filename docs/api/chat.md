# 对话 API

> 问答、语义检索

---

## 目录

- [问答](#问答)
- [流式问答](#流式问答)
- [语义检索](#语义检索)

---

## 问答

### POST /chat/ask

普通问答（非流式）

**请求**
```json
{
  "question": "什么是 Python？",
  "session_id": "user-session-id",
  "folder_ids": [1, 2],
  "chat_session_id": "chat-session-id"
}
```

**响应**
```json
{
  "answer": "Python 是一种...",
  "sources": [
    {"bvid": "BV1xxx", "title": "Python 入门", "url": "https://..."}
  ],
  "tokens_used": 1000
}
```

---

## 流式问答

### POST /chat/ask/stream

流式问答（Server-Sent Events）

**请求**
```json
{
  "question": "什么是 Python？",
  "session_id": "user-session-id",
  "folder_ids": [1, 2],
  "chat_session_id": "chat-session-id"
}
```

**响应**
```
data: {"content": "Python 是..."}
data: {"content": " 一种..."}
data: {"sources_json": "[...]"}
```

---

## 语义检索

### POST /chat/search

纯语义检索（不生成回答）

**请求**
```json
{
  "query": "Python 入门",
  "folder_ids": [1, 2],
  "top_k": 5
}
```

**响应**
```json
{
  "results": [
    {
      "bvid": "BV1xxx",
      "title": "Python 基础教程",
      "content": "...",
      "score": 0.95
    }
  ]
}
```
