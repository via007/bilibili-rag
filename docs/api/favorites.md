# 收藏夹 API

> 收藏夹列表、视频获取、整理功能

---

## 目录

- [获取收藏夹列表](#获取收藏夹列表)
- [获取收藏夹视频](#获取收藏夹视频)
- [获取所有视频](#获取所有视频)
- [整理预览](#整理预览)
- [执行整理](#执行整理)
- [清理无效视频](#清理无效视频)

---

## 获取收藏夹列表

### GET /favorites/list

获取当前用户的收藏夹列表

**响应**
```json
[
  {
    "media_id": 1,
    "title": "学习资料",
    "count": 100,
    "is_default": false
  }
]
```

---

## 获取收藏夹视频

### GET /favorites/{media_id}/videos

获取收藏夹视频（分页）

**路径参数**
| 参数 | 类型 | 说明 |
|------|------|------|
| media_id | int | 收藏夹 ID |

**查询参数**
| 参数 | 类型 | 说明 |
|------|------|------|
| page | int | 页码，默认 1 |
| page_size | int | 每页数量，默认 20 |

**响应**
```json
{
  "videos": [...],
  "total": 100,
  "page": 1,
  "page_size": 20
}
```

---

## 获取所有视频

### GET /favorites/{media_id}/all-videos

获取收藏夹所有视频（不分页）

**响应**
```json
{
  "videos": [...],
  "total": 100
}
```

---

## 整理预览

### POST /favorites/organize/preview

预览收藏夹整理结果（AI 自动分类）

**请求**
```json
{
  "media_id": 1
}
```

**响应**
```json
{
  "clusters": [
    {
      "name": "Python 入门",
      "bvids": ["BV1xxx", "BV1yyy"]
    }
  ]
}
```

---

## 执行整理

### POST /favorites/organize/execute

执行整理，将视频移动到分类收藏夹

**请求**
```json
{
  "media_id": 1,
  "clusters": [
    {"name": "Python 入门", "bvids": ["BV1xxx"]}
  ]
}
```

---

## 清理无效视频

### POST /favorites/organize/clean-invalid

清理收藏夹中已失效的视频

**请求**
```json
{
  "media_id": 1
}
```
