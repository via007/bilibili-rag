# 🎬 Bilibili RAG 知识库系统

将你的 B站收藏夹变成可对话的知识库！再也不让收藏夹里的视频吃灰了。

## ✨ 功能特性

- 🔐 **B站扫码登录** - 安全便捷，使用 B站 APP 扫码即可登录
- 📁 **收藏夹管理** - 查看所有收藏夹，选择要加入知识库的收藏夹
- 🤖 **智能内容提取** - 二级降级策略：
  - Level 1: 音频转文字（ASR，优先）
  - Level 2: 视频基本信息（兜底）
- 💬 **智能问答** - 基于 RAG 技术，对收藏内容进行问答
- 🔍 **语义搜索** - 快速找到相关视频
- ⚡ **向量存储** - 使用 ChromaDB 实现高效检索

## 🛠️ 技术栈

- **后端框架**: FastAPI
- **LLM 框架**: LangChain
- **向量数据库**: ChromaDB
- **Embedding**: text-embedding-v4（DashScope，可配置）
- **LLM**: Qwen 系列（DashScope 兼容模式，可配置）
- **ASR**: fun-asr（DashScope，音频转文字）
- **前端**: Next.js + Tailwind CSS
- **数据库**: SQLite

## 📦 安装

### 1. 进入项目

```bash
cd /Users/via/projects/bilibili-rag
```

### 2. 激活 Conda 环境

```bash
conda activate bilibili-rag
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置环境变量

```bash
# 复制示例配置
cp .env.example .env

# 编辑 .env 文件，填入你的 DashScope API Key
```

**.env 文件内容：**

```env
# OpenAI Compatible API (Alibaba Cloud DashScope)
DASHSCOPE_API_KEY=sk-your-dashscope-api-key
OPENAI_API_KEY=
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# Model Config
LLM_MODEL=qwen3-max
EMBEDDING_MODEL=text-embedding-v4

# DashScope ASR
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/api/v1
ASR_MODEL=fun-asr
ASR_TIMEOUT=600

# App Config
APP_HOST=0.0.0.0
APP_PORT=8000
DEBUG=true

# Database
DATABASE_URL=sqlite+aiosqlite:///./data/bilibili_rag.db

# ChromaDB
CHROMA_PERSIST_DIRECTORY=./data/chroma_db
```

## 🚀 启动

### 启动后端服务

```bash
# 方式 1: 使用脚本
chmod +x run_backend.sh
./run_backend.sh

# 方式 2: 直接运行
conda activate bilibili-rag
python -m uvicorn app.main:app --reload
```

后端 API 文档: http://localhost:8000/docs

### 启动前端界面

```bash
# 方式 1: 使用脚本
chmod +x run_frontend.sh
./run_frontend.sh

# 方式 2: 手动启动
cd frontend
npm install
npm run dev
```

前端界面: http://localhost:3000

## 📖 使用流程

### 1. 登录

1. 打开前端界面 http://localhost:3000
2. 点击「扫码登录」
3. 使用 B站 APP 扫码登录
4. 登录成功后进入工作台

### 2. 选择收藏夹

1. 勾选要加入知识库的收藏夹
2. 点击「构建知识库」
3. 等待构建完成

### 3. 开始对话

在「对话工作台」输入问题即可获取回答与来源视频。

## 📁 项目结构

```
bilibili-rag/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 主应用
│   ├── config.py            # 配置管理
│   ├── database.py          # 数据库连接
│   ├── models.py            # 数据模型
│   ├── routers/
│   │   ├── auth.py          # 登录认证
│   │   ├── favorites.py     # 收藏夹管理
│   │   ├── knowledge.py     # 知识库构建
│   │   └── chat.py          # AI 对话
│   └── services/
│       ├── bilibili.py      # B站 API 封装
│       ├── wbi.py           # Wbi 签名
│       ├── content_fetcher.py  # 内容获取
│       ├── asr.py           # 音频转写（ASR）
│       └── rag.py           # RAG 服务
├── frontend/                # Next.js 前端
│   ├── app/
│   ├── components/
│   └── lib/
├── requirements.txt         # Python 依赖
├── .env.example             # 环境变量示例
├── .gitignore
└── README.md
```

## 🔌 API 接口

### 认证

| 接口 | 方法 | 说明 |
|------|------|------|
| `/auth/qrcode` | GET | 获取登录二维码 |
| `/auth/qrcode/poll/{key}` | GET | 轮询登录状态 |
| `/auth/session/{id}` | GET | 获取会话信息 |
| `/auth/session/{id}` | DELETE | 退出登录 |

### 收藏夹

| 接口 | 方法 | 说明 |
|------|------|------|
| `/favorites/list` | GET | 获取收藏夹列表 |
| `/favorites/{id}/videos` | GET | 获取收藏夹视频 |
| `/favorites/{id}/all-videos` | GET | 获取全部视频 |

### 知识库

| 接口 | 方法 | 说明 |
|------|------|------|
| `/knowledge/stats` | GET | 获取统计信息 |
| `/knowledge/build` | POST | 构建知识库 |
| `/knowledge/build/status/{id}` | GET | 获取构建进度 |
| `/knowledge/clear` | DELETE | 清空知识库 |

### 对话

| 接口 | 方法 | 说明 |
|------|------|------|
| `/chat/ask` | POST | 提问 |
| `/chat/search` | POST | 搜索 |

## ⚠️ 注意事项

1. **API Key**: 需要配置 DashScope API Key
2. **B站 API**: 使用非官方 API，可能存在限制或变更
3. **Cookie 安全**: 登录信息存储在内存中，重启后需重新登录
4. **请求频率**: 请避免频繁请求，以免触发 B站限制

## 💰 费用与计费说明（DashScope）

以下能力均为 DashScope 计费项，价格以阿里云官方计费为准：

1. **LLM 对话**：按输入/输出 Token 计费（模型不同价格不同）。
2. **向量化 Embedding**：按输入 Token 计费。
3. **ASR 音频转文字**：按音频时长（秒）计费。

建议：  
- 构建前先选中少量收藏夹试跑，观察日志与费用。  
- 长视频优先使用“更新”而非频繁“重建”，避免重复转写。

## 📄 License

MIT
