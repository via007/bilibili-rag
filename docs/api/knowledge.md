# 知识库 API

> 视频处理、ASR 状态、入库管理

---

## 目录

- [知识库统计](#知识库统计)
- [收藏夹状态](#收藏夹状态)
- [同步收藏夹](#同步收藏夹)
- [构建知识库](#构建知识库)
- [构建状态](#构建状态)
- [删除视频](#删除视频)
- [ASR 状态](#asr-状态)
- [ASR 质量](#asr-质量)
- [ASR 纠错](#asr-纠错)

---

## 知识库统计

### GET /knowledge/stats

获取知识库统计信息

**响应**
```json
{
  "total_videos": 100,
  "total_videos_processed": 80,
  "total_videos_asr": 75,
  "total_size_mb": 500
}
```

---

## 收藏夹状态

### GET /knowledge/folders/status

获取收藏夹入库状态

**响应**
```json
[
  {
    "media_id": 1,
    "media_count": 100,
    "indexed_count": 80,
    "last_sync_at": "2026-03-15T10:00:00"
  }
]
```

---

## 同步收藏夹

### POST /knowledge/folders/sync

同步收藏夹到本地数据库

**请求**
```json
{
  "folder_ids": [1, 2, 3]
}
```

**响应**
```json
[
  {"media_id": 1, "synced": true, "video_count": 100},
  {"media_id": 2, "synced": true, "video_count": 50}
]
```

---

## 构建知识库

### POST /knowledge/build

构建知识库（ASR + 向量化）

**请求**
```json
{
  "folder_ids": [1, 2, 3]
}
```

**响应**
```json
{
  "task_id": "task-xxx",
  "status": "pending"
}
```

---

## 构建状态

### GET /knowledge/build/status/{task_id}

获取构建任务状态

**响应**
```json
{
  "task_id": "task-xxx",
  "status": "running",
  "progress": 50,
  "current_step": "正在转写视频 3/10"
}
```

---

## 删除视频

### DELETE /knowledge/video/{bvid}

删除指定视频的所有数据

---

## ASR 状态

### GET /knowledge/video/{bvid}/asr-status

获取视频 ASR 处理状态

**响应**
```json
{
  "bvid": "BV1xxx",
  "asr_status": "completed",
  "asr_text": "视频字幕内容...",
  "duration": 600
}
```

---

## ASR 质量

### GET /knowledge/video/{bvid}/asr-quality

获取 ASR 质量评分

**响应**
```json
{
  "bvid": "BV1xxx",
  "asr_quality_score": 0.85,
  "asr_quality_flags": ["short_duration"]
}
```

---

## ASR 纠错

### POST /knowledge/video/{bvid}/asr-correct

提交 ASR 纠错

**请求**
```json
{
  "corrected_text": "正确的字幕内容"
}
```
