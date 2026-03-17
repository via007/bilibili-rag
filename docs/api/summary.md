# 摘要 API

> 视频 AI 摘要

---

## 获取摘要

### GET /summary/{bvid}

获取视频 AI 摘要

**响应**
```json
{
  "bvid": "BV1xxx",
  "summary": "本视频介绍了 Python 的基础语法...",
  "outline": [
    {"title": "Python 简介", "points": ["诞生历史", "应用场景"]},
    {"title": "环境配置", "points": ["安装 Python", "运行方式"]}
  ]
}
```

---

## 生成摘要

### POST /summary/generate

手动触发摘要生成

**请求**
```json
{
  "bvid": "BV1xxx"
}
```
