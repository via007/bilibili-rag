# 系统架构

---

## 架构图

```
┌──────────┐     ┌──────────┐
│ Frontend │────▶│ Backend  │
│ Next.js   │◀────│ FastAPI │
└──────────┘     └────┬─────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
    ┌─────────┐  ┌─────────┐  ┌─────────┐
    │ SQLite  │  │ ChromaDB│  │External │
    └─────────┘  └─────────┘  │  APIs   │
                               └─────────┘
```

---

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | Next.js, Tailwind, Mantine |
| 后端 | FastAPI, LangChain |
| 数据库 | SQLite |
| 向量库 | ChromaDB |
| LLM | DashScope |
