# 配置说明

> 环境变量和系统配置

---

## 必需配置

| 变量名 | 说明 | 示例 |
|--------|------|------|
| DASHSCOPE_API_KEY | 阿里云 DashScope API Key | sk-xxxx |
| LLM_MODEL | LLM 模型名称 | qwen3-max |
| EMBEDDING_MODEL | Embedding 模型 | text-embedding-v4 |

---

## 可选配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| OPENAI_API_KEY | - | OpenAI API Key |
| OPENAI_BASE_URL | dashscope端点 | API 地址 |
| ASR_MODEL | paraformer-v2 | ASR 模型 |
| APP_HOST | 0.0.0.0 | 监听地址 |
| APP_PORT | 8000 | 监听端口 |
| DEBUG | true | 调试模式 |
| DATABASE_URL | sqlite路径 | 数据库连接 |
| CHROMA_PERSIST_DIRECTORY | ./data/chroma_db | 向量库路径 |

---

## 获取 API Key

### DashScope

1. 访问 https://dashscope.console.aliyun.com/
2. 注册/登录
3. 创建 API Key
4. 充值（有免费额度）
