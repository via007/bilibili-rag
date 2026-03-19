# API 参考

> 所有 API 端点索引

---

## 基础信息

| 项目 | 值 |
|------|-----|
| Base URL | `http://localhost:8000` |
| API 文档 | `/docs` |
| OpenAPI JSON | `/openapi.json` |
| OpenAPI YAML | `/reference/03-openapi.yaml` |

---

## 端点总览

### Auth (认证)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/auth/qrcode` | 获取登录二维码 |
| GET | `/auth/qrcode/poll/{qrcode_key}` | 轮询登录状态 |
| GET | `/auth/session/{session_id}` | 获取用户会话 |
| DELETE | `/auth/session/{session_id}` | 删除用户会话 |

### Favorites (收藏夹)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/favorites/list` | 获取收藏夹列表 |
| GET | `/favorites/{media_id}/videos` | 获取视频（分页） |
| GET | `/favorites/{media_id}/all-videos` | 获取所有视频 |
| POST | `/favorites/organize/preview` | 整理预览 |
| POST | `/favorites/organize/execute` | 执行整理 |

### Knowledge (知识库)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/knowledge/stats` | 获取统计 |
| GET | `/knowledge/folders/status` | 收藏夹状态 |
| POST | `/knowledge/folders/sync` | 同步收藏夹 |
| POST | `/knowledge/build` | 构建知识库 |
| GET | `/knowledge/build/status/{task_id}` | 构建状态 |
| GET | `/knowledge/video/{bvid}/asr-status` | ASR 状态 |

### Chat (对话)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chat/ask` | 问答 |
| POST | `/chat/ask/stream` | 流式问答 |
| POST | `/chat/search` | 语义检索 |

### Conversation (会话管理)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/conversation/list` | 会话列表 |
| POST | `/conversation/create` | 创建会话 |
| GET | `/conversation/{chat_session_id}` | 会话详情 |
| PUT | `/conversation/{chat_session_id}` | 更新会话 |
| DELETE | `/conversation/{chat_session_id}` | 删除会话 |
| GET | `/conversation/{chat_session_id}/messages` | 消息列表 |

### Export (导出)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/export/video` | 导出视频 |
| POST | `/export/folder` | 导出收藏夹 |
| POST | `/export/session` | 导出会话 |
| GET | `/export/session-summary/{id}` | 获取总结 |
| POST | `/export/session-summary/{id}/refresh` | 刷新总结 |
| DELETE | `/export/session-summary/{id}` | 删除缓存 |

### Summary (摘要)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/summary/{bvid}` | 获取摘要 |
| POST | `/summary/generate` | 生成摘要 |

### Correction (纠错)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/correction/list` | 纠错列表 |
| GET | `/correction/{bvid}` | 纠错详情 |
| POST | `/correction/{bvid}` | 提交纠错 |

### Config (配置)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/config` | 获取配置 |
| PUT | `/config` | 更新配置 |

### Clustering (聚类)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/clustering/{folder_id}` | 获取聚类 |
| POST | `/clustering/generate` | 生成聚类 |

### Learning Path (学习路径)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/learning-path/{folder_id}` | 获取路径 |
| POST | `/learning-path/generate` | 生成路径 |

---

## 通用格式

### 请求头

```
Content-Type: application/json
X-Session-Id: {session_id}
```

### 响应格式

**成功**
```json
{
  "success": true,
  "data": {}
}
```

**错误**
```json
{
  "detail": "错误信息"
}
```

---

## 状态码

| 码 | 说明 |
|----|------|
| 200 | 成功 |
| 400 | 参数错误 |
| 401 | 未认证 |
| 404 | 不存在 |
| 500 | 服务器错误 |
