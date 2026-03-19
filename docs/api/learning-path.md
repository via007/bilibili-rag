# 学习路径 API

> AI 生成学习路线

---

## 获取学习路径

### GET /learning-path/{folder_id}

获取收藏夹的学习路径

**响应**
```json
{
  "folder_id": 1,
  "title": "Python 学习路径",
  "levels": [
    {
      "name": "入门",
      "description": "Python 基础语法",
      "bvids": ["BV1xxx"]
    },
    {
      "name": "进阶",
      "description": "面向对象编程",
      "bvids": ["BV1yyy"]
    }
  ]
}
```

---

## 生成学习路径

### POST /learning-path/generate

手动生成学习路径

**请求**
```json
{
  "folder_id": 1
}
```
