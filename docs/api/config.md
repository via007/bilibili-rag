# 配置 API

> LLM 配置管理

---

## 获取配置

### GET /config

获取当前 LLM 配置

**响应**
```json
{
  "llm_provider": "dashscope",
  "llm_model": "qwen3-max",
  "embedding_model": "text-embedding-v4",
  "temperature": 0.5
}
```

---

## 更新配置

### PUT /config

更新 LLM 配置

**请求**
```json
{
  "llm_provider": "dashscope",
  "llm_model": "qwen3-max",
  "temperature": 0.7
}
```
