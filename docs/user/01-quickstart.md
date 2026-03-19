# 快速开始

> 5 分钟快速上手 Bilibili RAG

---

## 环境要求

| 组件 | 要求 |
|------|------|
| Python | 3.10+ |
| Node.js | 18+ |
| ffmpeg | 已安装并在 PATH |

---

## 步骤 1：克隆项目

```bash
git clone https://github.com/your-repo/bilibili-rag
cd bilibili-rag
```

---

## 步骤 2：安装依赖

```bash
# 后端
pip install -r requirements.txt

# 前端
cd frontend && npm install
```

---

## 步骤 3：配置环境变量

```bash
# 复制配置
cp .env.example .env

# 编辑 .env，填写必要配置
DASHSCOPE_API_KEY=your-key
LLM_MODEL=qwen3-max
EMBEDDING_MODEL=text-embedding-v4
```

---

## 步骤 4：启动服务

```bash
# 终端 1：后端
python -m uvicorn app.main:app --reload --port 8000

# 终端 2：前端
cd frontend && npm run dev
```

---

## 步骤 5：使用

1. 打开 http://localhost:3000
2. 扫码登录 B 站账号
3. 刷新收藏夹
4. 勾选收藏夹，点击入库
5. 开始问答

---

## 下一步

- [完整使用指南](./02-guide.md)
- [FAQ](./03-faq.md)
