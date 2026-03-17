# Bilibili RAG 文档中心

> 基于 AI 的 B 站知识库系统

---

## 在线文档

| 资源 | 地址 |
|------|------|
| API 在线文档 | http://localhost:8000/docs |
| OpenAPI JSON | http://localhost:8000/openapi.json |

---

## 快速导航

### 👤 我是用户

- [快速开始](./user/01-quickstart.md) - 5 分钟上手
- [使用指南](./user/02-guide.md) - 完整功能说明
- [FAQ](./user/03-faq.md) - 常见问题

### 🛠️ 我是开发者

- [系统架构](./dev/01-architecture.md) - 技术架构
- [快速开始](./dev/02-setup.md) - 开发环境
- [API 参考](./api/00-index.md) - API 端点

### 📖 API 文档

| 模块 | 说明 | 端点数 |
|------|------|--------|
| [认证](./api/01-auth.md) | 登录、登出 | 4 |
| [收藏夹](./api/02-favorites.md) | 收藏夹操作 | 6 |
| [知识库](./api/03-knowledge.md) | 视频处理、ASR | 10 |
| [对话](./api/04-chat.md) | 问答、检索 | 3 |
| [会话](./api/05-conversation.md) | 会话管理 | 7 |
| [导出](./api/06-export.md) | 导出功能 | 6 |
| [摘要](./api/07-summary.md) | 视频摘要 | 2 |
| [纠错](./api/08-correction.md) | ASR 纠错 | 4 |
| [配置](./api/09-config.md) | LLM 配置 | 2 |
| [聚类](./api/10-clustering.md) | 视频聚类 | 2 |
| [学习路径](./api/11-learning-path.md) | 学习路径 | 2 |

---

## 目录结构

```
docs/
├── README.md
├── user/                    # 用户文档
│   ├── 01-quickstart.md
│   ├── 02-guide.md
│   └── 03-faq.md
├── api/                     # API 文档
│   ├── 00-index.md         # API 索引
│   ├── 01-auth.md
│   ├── 02-favorites.md
│   ├── 03-knowledge.md
│   ├── 04-chat.md
│   ├── 05-conversation.md
│   ├── 06-export.md
│   ├── 07-summary.md
│   ├── 08-correction.md
│   ├── 09-config.md
│   ├── 10-clustering.md
│   └── 11-learning-path.md
├── dev/                     # 开发者文档
│   ├── 01-architecture.md
│   └── 02-setup.md
├── reference/               # 参考文档
│   ├── 01-models.md
│   ├── 02-config.md
│   └── 03-openapi.yaml    # Swagger 规范
└── changelog/              # 更新日志
```
