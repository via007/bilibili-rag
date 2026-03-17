# 纠错 API

> ASR 字幕纠错

---

## 获取纠错列表

### GET /correction/list

获取可纠错的视频列表

**响应**
```json
{
  "videos": [
    {"bvid": "BV1xxx", "title": "视频标题", "has_correction": true}
  ]
}
```

---

## 获取纠错详情

### GET /correction/{bvid}

获取视频纠错详情

**响应**
```json
{
  "bvid": "BV1xxx",
  "original_text": "原始字幕",
  "corrected_text": "纠正后字幕",
  "status": "pending"
}
```

---

## 提交纠错

### POST /correction/{bvid}

提交纠错

**请求**
```json
{
  "corrected_text": "正确的字幕内容"
}
```

---

## 纠错历史

### GET /correction/{bvid}/history

获取纠错历史记录
