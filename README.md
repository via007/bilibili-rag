# Bilibili RAG：把收藏夹变成可对话的知识库

[![GitHub Stars](https://img.shields.io/github/stars/via007/bilibili-rag)](https://github.com/via007/bilibili-rag)
[![License](https://img.shields.io/github/license/via007/bilibili-rag)](https://github.com/via007/bilibili-rag)
[![Python](https://img.shields.io/badge/Python-3.10+-blue)](https://www.python.org/)
[![Next.js](https://img.shields.io/badge/Next.js-14+-black)](https://nextjs.org/)

把你在 B 站收藏的访谈/演讲/课程，变成可检索、可追溯来源的**个人知识库**。
适合：访谈/演讲/课程、技术视频与学习视频整理、公开课复盘、知识总结、会议/分享回顾、播客内容归档等。

> 亮点：自动拉取内容 → 语音转写 → 向量检索 → 对话问答 → 智能总结 → 主题聚类 → 学习路径

---

## ✨ 功能一览

### 核心功能（基础版）
- ✅ B 站扫码登录，读取收藏夹
- ✅ 音频转文字（ASR），自动兜底处理
- ✅ 语义检索（向量检索）
- ✅ 基于 RAG 的对话问答
- ✅ 本地 SQLite + ChromaDB 存储

### 进阶功能（v2.0 新增）

#### 📚 知识管理
| 功能 | 说明 |
|------|------|
| **视频总结** | LLM 自动生成结构化摘要（要点、难度、适合人群） |
| **内容修正** | 手动修正 ASR 识别错误，记录修正历史 |
| **主题聚类** | 按主题自动聚合视频，发现知识结构 |
| **学习路径** | 智能推荐学习顺序，按难度分阶段 |

#### 💬 对话增强
| 功能 | 说明 |
|------|------|
| **多轮对话** | 会话管理，支持上下文连续对话 |
| **引用来源** | 答案附带参考来源，可追溯原文 |
| **会话导出** | 导出对话记录为 Markdown |

#### 🔧 RAG 增强
| 功能 | 说明 |
|------|------|
| **多路召回** | 语义检索 + 关键词召回融合 |
| **重排序** | Cross-Encoder 优化排序结果 |
| **流式输出** | 实时显示回答生成过程 |

#### 🤖 模型支持
| 提供商 | 模型 | 状态 |
|--------|------|------|
| 阿里云 DashScope | Qwen 系列 | ✅ 支持 |
| 百度文心 | ERNIE 系列 | ✅ 支持 |
| 腾讯混元 | Hunyuan 系列 | ✅ 支持 |
| 火山引擎 | Doubao 系列 | ✅ 支持 |
| 智谱 GLM | GLM 系列 | ✅ 支持 |

#### 🎧 ASR 方案
| 方案 | 说明 |
|------|------|
| 云端 ASR | 阿里 DashScope Paraformer（默认） |
| 本地 Whisper | OpenAI Whisper 模型 |
| 本地 FunASR | 阿里 FunASR 模型 |

---

## 🖼️ 演示

### 截图
![首页](assets/screenshots/home.png)
![对话](assets/screenshots/chat.png)

### 视频演示
[B 站演示视频](https://b23.tv/bGXyhjU)

### Star History
[![Star History](https://api.star-history.com/svg?repos=via007/bilibili-rag&type=Date)](https://star-history.com/#via007/bilibili-rag&Date)

---

## 🚀 快速开始

### 前置条件

1. **Python 3.10+**
2. **Node.js 18+**
3. **ffmpeg**（音频处理需要）
   - macOS: `brew install ffmpeg`
   - Windows: 下载安装包后将 `bin` 目录加入 PATH
   - Linux: `apt/yum/pacman` 安装 `ffmpeg`

### 步骤 1: 克隆项目

```bash
git clone https://github.com/via007/bilibili-rag.git
cd bilibili-rag
```

### 步骤 2: 创建虚拟环境

```bash
# 使用 conda（推荐）
conda create -n bilibili-rag python=3.11
conda activate bilibili-rag

# 或使用 venv
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows
```

### 步骤 3: 安装依赖

```bash
# 后端依赖
pip install -r requirements.txt

# 前端依赖
cd frontend
npm install
cd ..
```

### 步骤 4: 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填写必要配置
```

**必需配置**:
```env
# 阿里云 DashScope（必需）
DASHSCOPE_API_KEY=your-api-key

# LLM 模型（可选，默认 qwen3-max）
LLM_MODEL=qwen3-max

# Embedding 模型（可选）
EMBEDDING_MODEL=text-embedding-v4
```

**可选配置**:
```env
# 其他 LLM 提供商（如需使用）
# 百度
BAIDU_API_KEY=your-key
BAIDU_SECRET_KEY=your-secret

# 腾讯
TENCENT_SECRET_ID=your-id
TENCENT_SECRET_KEY=your-key

# 火山引擎
VOLCENGINE_API_KEY=your-key

# 智谱
ZHIPU_API_KEY=your-key

# 本地 ASR（如需使用）
ASR_BACKEND=whisper  # 或 funasr
WHISPER_MODEL=base
```

### 步骤 5: 启动服务

**后端**:
```bash
python -m uvicorn app.main:app --reload --port 8000
```
- API 文档: http://localhost:8000/docs
- 健康检查: http://localhost:8000/health

**前端**:
```bash
cd frontend
npm run dev
```
- 访问地址: http://localhost:3000

---

## 📡 API 端点完整列表

### 认证 `/auth`
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/auth/qrcode` | 生成登录二维码 |
| GET | `/auth/qrcode/poll/{qrcode_key}` | 轮询扫码状态 |
| GET | `/auth/session/{session_id}` | 获取登录状态 |
| POST | `/auth/logout` | 登出 |

### 收藏夹 `/favorites`
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/favorites/list` | 获取收藏夹列表 |
| GET | `/favorites/{media_id}/videos` | 获取收藏夹内视频 |
| GET | `/favorites/{media_id}/all-videos` | 获取全部视频 |
| POST | `/favorites/organize/preview` | 预览整理方案 |
| POST | `/favorites/organize/execute` | 执行整理 |
| POST | `/favorites/organize/clean-invalid` | 清理失效视频 |

### 知识库 `/knowledge`
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/knowledge/stats` | 获取知识库统计 |
| POST | `/knowledge/build` | 构建知识库 |
| GET | `/knowledge/build/status/{task_id}` | 获取构建状态 |
| GET | `/knowledge/folders/status` | 获取入库状态 |
| POST | `/knowledge/folders/sync` | 同步收藏夹 |
| DELETE | `/knowledge/clear` | 清理知识库 |
| DELETE | `/knowledge/video/{bvid}` | 删除视频 |
| GET | `/knowledge/video/{bvid}/asr-status` | ASR 状态 |
| GET | `/knowledge/video/{bvid}/asr-quality` | ASR 质量 |
| POST | `/knowledge/video/{bvid}/asr-correct` | ASR 修正 |

### 视频摘要 `/knowledge/summary`
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/knowledge/summary/{bvid}` | 获取视频摘要 |
| POST | `/knowledge/summary/generate` | 生成视频摘要 |

### 主题聚类 `/knowledge/clusters`
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/knowledge/clusters/{folder_id}` | 获取聚类结果 |
| POST | `/knowledge/clusters/generate` | 生成聚类 |

### 学习路径 `/knowledge/path`
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/knowledge/path/{folder_id}` | 获取学习路径 |
| POST | `/knowledge/path/generate` | 生成学习路径 |

### 对话 `/chat`
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chat/ask` | 问答 |
| POST | `/chat/ask/stream` | 流式问答 |
| POST | `/chat/search` | 语义检索 |

### 会话管理 `/conversation`
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/conversation/list` | 会话列表 |
| POST | `/conversation/create` | 创建会话 |
| GET | `/conversation/{id}` | 获取会话 |
| PUT | `/conversation/{id}` | 更新会话 |
| DELETE | `/conversation/{id}` | 删除会话 |
| GET | `/conversation/{id}/messages` | 消息历史 |
| GET | `/conversation/search` | 搜索会话 |

### 内容修正 `/correction`
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/correction/list` | 修正列表 |
| GET | `/correction/{bvid}` | 修正详情 |
| POST | `/correction/{bvid}` | 提交修正 |
| GET | `/correction/{bvid}/history` | 修正历史 |

### 导出 `/export`
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/export/video` | 导出视频 |
| POST | `/export/folder` | 导出收藏夹 |
| POST | `/export/session` | 导出会话 |
| GET | `/export/session-summary/{id}` | 获取会话总结 |
| POST | `/export/session-summary/{id}/refresh` | 刷新总结 |
| DELETE | `/export/session-summary/{id}` | 删除总结 |

### 配置 `/config`
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/config/llm` | 获取 LLM 配置 |
| PUT | `/config/llm` | 更新 LLM 配置 |

---

## 📂 项目结构

```
bilibili-rag/
├── app/                         # 后端代码
│   ├── main.py                  # FastAPI 应用入口
│   ├── config.py                # 配置管理
│   ├── models.py                # 数据模型
│   ├── database.py              # 数据库连接
│   ├── routers/                 # API 路由
│   │   ├── auth.py             # 认证
│   │   ├── chat.py             # 对话
│   │   ├── conversation.py     # 会话管理
│   │   ├── knowledge.py        # 知识库
│   │   ├── favorites.py        # 收藏夹
│   │   ├── summary.py          # 视频摘要
│   │   ├── correction.py       # 内容修正
│   │   ├── clustering.py       # 主题聚类
│   │   ├── learning_path.py    # 学习路径
│   │   ├── export.py           # 导出
│   │   └── config.py           # 配置管理
│   └── services/                # 业务逻辑
│       ├── bilibili.py         # B站 API
│       ├── asr.py              # 音频转写
│       ├── rag.py               # RAG 核心
│       ├── conversation.py      # 会话服务
│       ├── summary.py           # 摘要服务
│       ├── clustering.py        # 聚类服务
│       ├── learning_path.py     # 学习路径服务
│       ├── export.py           # 导出服务
│       ├── providers.py        # LLM 提供商
│       ├── llm_factory.py       # LLM 工厂
│       ├── citation.py         # 引用来源
│       ├── fusion.py           # 融合检索
│       ├── multi_recall.py     # 多路召回
│       ├── reranker.py         # 重排序
│       ├── asr_quality.py      # ASR 质量
│       ├── asr_local.py        # 本地 ASR
│       └── ...
├── frontend/                    # 前端界面
│   ├── app/                    # Next.js 页面
│   │   ├── layout.tsx         # 根布局
│   │   ├── page.tsx           # 首页
│   │   └── globals.css        # 全局样式
│   ├── components/             # React 组件
│   │   ├── ChatPanel.tsx     # 聊天面板
│   │   ├── SessionList.tsx   # 会话列表
│   │   ├── SessionManager.tsx # 会话管理
│   │   ├── SourcesPanel.tsx  # 来源面板
│   │   ├── LoginModal.tsx    # 登录弹窗
│   │   ├── VideoSummaryModal.tsx # 摘要弹窗
│   │   ├── CorrectionModal.tsx # 修正弹窗
│   │   ├── ClusteringModal.tsx # 聚类弹窗
│   │   ├── LearningPathModal.tsx # 学习路径弹窗
│   │   ├── ExportModal.tsx   # 导出弹窗
│   │   ├── ModelSelector.tsx # 模型选择
│   │   ├── Providers.tsx     # 提供商配置
│   │   └── Toast.tsx         # 提示组件
│   └── lib/                   # 工具函数
│       ├── api.ts            # API 调用
│       ├── export.ts         # 导出功能
│       └── conversation.ts   # 会话类型
├── data/                      # 数据存储
├── skills/                    # OpenClaw Skills
├── docs/                      # 项目文档
├── scripts/                   # 工具脚本
├── test/                      # 测试脚本
├── requirements.txt           # 后端依赖
├── .env.example              # 环境变量示例
└── README.md                 # 项目说明
```

---

## 🧠 工作流程

```
1. B 站扫码登录
      ↓
2. 选择收藏夹，同步视频
      ↓
3. 自动处理：音频转写 → 向量嵌入
      ↓
4. 对话问答 / 语义检索
      ↓
5. [可选] 生成视频摘要
      ↓
6. [可选] 主题聚类，发现知识结构
      ↓
7. [可选] 学习路径，推荐学习顺序
      ↓
8. [可选] 导出分享
```

---

## 🤖 OpenClaw 集成

本项目提供 OpenClaw Skill，可接入 OpenClaw 实现自动化。

### 接入方式

1. 将 `skills/bilibili-rag-local` 复制到 OpenClaw Skills 目录
2. 重启 OpenClaw
3. 使用 Skill 调用本地 API

### 可用接口

```python
# 问答
POST /chat/ask

# 检索
POST /chat/search

# 入库状态
GET /knowledge/folders/status
```

---

## 🧪 测试

### 运行测试

```bash
# 后端测试
pytest test/ -v

# E2E 测试
python test/full_e2e_test.py
```

### 诊断脚本

```bash
# 测试 ASR
python test/debug_asr_single.py

# 测试 RAG
python test/diagnose_rag.py
```

---

## 💰 费用说明

### DashScope 费用

| 服务 | 计费方式 |
|------|----------|
| LLM 对话 | 按 Token 计费 |
| Embedding | 按 Token 计费 |
| ASR | 按音频时长计费 |

### 建议

- 测试阶段：用**短视频（约 10 分钟）**验证
- 正式使用：按需启用，大部分模型有免费额度
- 本地 ASR：可减少云端 ASR 费用

---

## 🧩 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | FastAPI, LangChain, SQLAlchemy |
| LLM | DashScope, 文心一言, 混元, GLM |
| 向量库 | ChromaDB |
| 数据库 | SQLite |
| 前端 | Next.js 14, React, Tailwind CSS, TypeScript |
| UI | shadcn/ui 组件库 |

---

## ✅ 常见问题

### Q: 音频 URL 返回 403？
A: B 站直链存在鉴权/过期限制，系统会自动兜底（本地下载+转码+DashScope 识别）

### Q: 如何切换 LLM 提供商？
A: 使用 `/config/llm` API 或前端模型选择器

### Q: 支持本地部署 ASR 吗？
A: 支持 Whisper 和 FunASR，配置 `ASR_BACKEND` 即可

### Q: 会话可以保存多久？
A: SQLite 本地存储，理论上永久保存

### Q: 支持批量导出吗？
A: 支持，可导出整个收藏夹或指定会话

---

## 📜 更新日志

### v2.0 (当前版本)
- ✅ 多轮对话与会话管理
- ✅ 视频智能摘要
- ✅ 内容修正功能
- ✅ 主题聚类
- ✅ 学习路径推荐
- ✅ 多 LLM 提供商支持
- ✅ 本地 ASR 方案
- ✅ 答案引用来源
- ✅ 高级 RAG（多路召回、重排序）

### v1.0 (初始版本)
- ✅ B 站扫码登录
- ✅ 收藏夹同步
- ✅ ASR 音频转写
- ✅ 向量检索
- ✅ RAG 对话问答

---

## 📄 License

MIT License - 请勿用于商业或违规用途

---

## ⚠️ 免责声明

本项目仅供个人学习与技术研究，使用者需自行遵守 B 站服务条款及相关法律法规，禁止用于未授权的商业或违规用途。
