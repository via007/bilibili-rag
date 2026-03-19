# 数据模型

> 数据库表结构说明

---

## 核心表

### UserSession

用户会话

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| session_id | string | 会话ID |
| cookie | string | B站Cookie |
| created_at | datetime | 创建时间 |

### FavoriteFolder

收藏夹

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| media_id | int | B站收藏夹ID |
| title | string | 标题 |
| user_session_id | string | 关联用户 |

### FavoriteVideo

收藏视频

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| bvid | string | 视频BV号 |
| folder_id | int | 收藏夹ID |

### VideoCache

视频缓存

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| bvid | string | 视频BV号 |
| title | string | 标题 |
| content | text | 转写内容 |
| summary | text | AI摘要 |
| is_processed | bool | 是否已处理 |

### ChatSession

对话会话

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| session_id | string | 会话ID |
| title | string | 标题 |
| user_session_id | string | 关联用户 |
| message_count | int | 消息数 |

### ChatMessage

对话消息

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| chat_session_id | string | 会话ID |
| role | string | user/assistant |
| content | text | 内容 |
| sources | JSON | 来源列表 |

### SessionSummary

会话总结缓存

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| chat_session_id | string | 会话ID |
| content | text | Markdown内容 |
| version | int | 版本号 |
| created_at | datetime | 创建时间 |
