# 聚类 API

> 视频智能分类

---

## 获取聚类结果

### GET /clustering/{folder_id}

获取收藏夹视频聚类结果

**响应**
```json
{
  "clusters": [
    {
      "name": "Python 入门",
      "bvids": ["BV1xxx", "BV1yyy"],
      "description": "Python 基础教程"
    }
  ]
}
```

---

## 生成聚类

### POST /clustering/generate

手动触发聚类生成

**请求**
```json
{
  "folder_id": 1,
  "force": false
}
```
