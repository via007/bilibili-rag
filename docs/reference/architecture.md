# 技术架构

> Bilibili RAG 系统架构设计

---

## 系统架构

```
┌─────────────┐     ┌─────────────┐
│   Frontend  │────▶│   Backend   │
│  (Next.js)  │◀────│  (FastAPI)  │
└─────────────┘     └──────┬──────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
         ▼                 ▼                 ▼
┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│  Database   │   │  Vector DB  │   │  External   │
│   (SQLite)  │   │  (ChromaDB)  │   │    APIs     │
└─────────────┘   └─────────────┘   │  - Bilibili  │
                                     │  - DashScope │
                                     └─────────────┘
```

---

## 模块说明

### 前端 (Frontend)

- **框架**: Next.js + TypeScript
- **UI**: Tailwind CSS + Mantine UI
- **状态管理**: React Hooks

### 后端 (Backend)

- **框架**: FastAPI
- **ORM**: SQLAlchemy (Async)
- **LLM**: LangChain

### 数据存储

| 存储 | 用途 |
|------|------|
| SQLite | 结构化数据（用户、会话、视频元信息） |
| ChromaDB | 向量数据（视频内容 embedding） |
| 本地文件 | 音频文件、临时文件 |

### 外部服务

| 服务 | 用途 |
|------|------|
| B站 API | 登录、获取收藏夹、视频 |
| DashScope | LLM、Embedding、ASR |

---

## 数据流

### 1. 登录流程

```
用户扫码 → B站验证 → 获取Cookie → 存入数据库
```

### 2. 同步流程

```
获取收藏夹列表 → 遍历视频 → 存入SQLite
```

### 3. 入库流程

```
选择收藏夹 → 下载音频 → ASR转写 → 生成摘要 → 向量化 → 存入ChromaDB
```

### 4. 问答流程

```
用户提问 → 检索向量库 → 构建Prompt → 调用LLM → 返回回答 → 存入消息
```

---

## 目录结构

```
bilibili-rag/
├── app/                    # 后端代码
│   ├── routers/           # API 路由
│   ├── services/          # 业务逻辑
│   ├── models.py          # 数据模型
│   ├── database.py        # 数据库
│   └── config.py          # 配置
├── frontend/              # 前端代码
│   ├── app/              # 页面
│   ├── components/       # 组件
│   └── lib/              # 工具函数
├── data/                  # 数据存储
├── docs/                  # 文档
└── test/                  # 测试
```
