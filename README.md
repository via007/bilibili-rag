# 🚀 Bilibili RAG：把收藏夹变成可对话的知识库

把你在 B 站收藏的访谈/演讲/课程，变成可检索、可追溯来源的**个人知识库**。  
适合：访谈/演讲/课程、技术视频与学习视频整理、公开课复盘、知识总结、会议/分享回顾、播客内容归档等。

> 亮点：自动拉取内容 → 语音转写 → 向量检索 → 对话问答

---

## ✨ 功能一览

- ✅ B 站扫码登录，读取收藏夹
- ✅ 音频转文字（ASR），自动兜底处理
- ✅ 语义检索（向量检索）
- ✅ 基于 RAG 的对话问答
- ✅ 本地 SQLite + ChromaDB 存储

---

## 🖼️ 演示与截图

![首页截图](assets/screenshots/home.png)
![对话界面截图](assets/screenshots/chat.png)

## B站演示视频：
[演示视频](https://b23.tv/bGXyhjU)

## ⭐ Star History
[![Star History Chart](https://api.star-history.com/svg?repos=via007/bilibili-rag&type=Date)](https://star-history.com/#via007/bilibili-rag&Date)

---

## ⚡ 快速开始（3 步）

0) 安装 ffmpeg（并确保在 PATH 中）  
- macOS: `brew install ffmpeg`  
- Windows: 下载安装包后将 `bin` 目录加入 PATH  
- Linux: `apt/yum/pacman` 安装 `ffmpeg`  

1) 安装依赖  
```bash
conda activate bilibili-rag
pip install -r requirements.txt
```

2) 配置环境变量  
```bash
cp .env.example .env
# 编辑 .env，填写 DashScope API Key 等配置
```

3) 启动服务  
```bash
python -m uvicorn app.main:app --reload
```
后端文档：`http://localhost:8000/docs`

前端：
```bash
cd frontend
npm install
npm run dev
```
前端页面：`http://localhost:3000`

---

## 🧠 工作流程

1. 选择收藏夹  
2. 拉取视频 → 音频转写（ASR）  
3. 生成向量 → 构建知识库  
4. 对话/检索问答  

---

## 🤖 OpenClaw Skill（本地接入）

本仓库已提供一个可直接使用的 Skill：`skills/bilibili-rag-local/SKILL.md`。  
作用：把本地运行的 `bilibili-rag` 服务接入 OpenClaw，让 OpenClaw 直接调用你的收藏夹知识库进行检索和问答。

### 前置条件

1. 先按上面的步骤完成本项目本地部署。  
2. 确认后端接口可访问：`http://127.0.0.1:8000/docs`。  
3. 确认 OpenClaw 已安装并可加载本地 Skills。  

### 接入方式

1. 将本仓库中的 `skills/bilibili-rag-local` 放到 OpenClaw 的 Skills 目录（例如 `~/.openclaw/skills/`）。  
2. 重启或刷新 OpenClaw Skills。  
3. 在 OpenClaw 中调用该 Skill，让它通过本地 API 执行：  
   - `POST /chat/ask`（问答）  
   - `POST /chat/search`（检索片段）  
   - `GET /knowledge/folders/status`（入库状态）  

### 使用建议

1. 先同步/入库收藏夹，再进行问答。  
2. 问题越具体，召回效果越好。  
3. 若出现“无命中”，优先检查是否完成入库或是否选错收藏夹。  

---

## 🧩 基于 Skill 的扩展示例

你可以在 `skills/` 目录继续开发更多 Skill，把收藏夹真正变成可持续运营的知识系统。  
例如结合 OpenClaw 的定时能力（Cron）做自动化：

1. 每日/每周统计收藏夹入库状态（新增、未入库、失败项）。  
2. 定时生成“新增收藏学习摘要”（按主题聚合要点）。  
3. 定时输出“待补全内容清单”（ASR 失败、内容过短、召回弱视频）。  
4. 将统计结果自动推送到你常用的消息渠道，形成固定复盘节奏。  

---

## 🧪 测试与诊断脚本

> 注意：`test/` 目录下的脚本需要 **移动到项目根目录** 再运行（依赖相对路径与配置）。

- `debug_asr_single.py`：测试单个视频是否能正确获取音频  
- `diagnose_rag.py`：测试向量检索召回是否准确  
- `sync_cache_vectors.py`：同步数据库缓存数据到向量库  

---

## 🎧 ASR 说明（音频不可达兜底）

部分 B 站音频 URL 可能返回 403（直链不可拉取），系统会自动执行兜底流程：

1. 本地下载音频（带 Cookie）
2. ffmpeg 转码为 16k 单声道
3. 上传到 DashScope 后再识别

> 请确保本机已安装 `ffmpeg` 并加入 PATH。

---

## 💰 费用说明（DashScope）

模型相关费用包括：
- LLM 对话（按 Token）
- Embedding（按 Token）
- ASR 音频转写（按时长）

建议：
- 部署/测试阶段先用 **短视频（约 10 分钟）**验证流程与费用  
- 正式使用按需启用，注意费用；大多数模型有免费额度，通常足够日常使用  

---

## 🧩 技术栈

- 后端：FastAPI  
- LLM：LangChain + DashScope  
- 向量库：ChromaDB  
- 前端：Next.js + Tailwind  
- 数据库：SQLite  

---

## 📂 目录结构（简版）

```
bilibili-rag/
├── app/                # 后端逻辑
├── frontend/           # 前端界面
├── data/               # 数据库与向量库
├── skills/             # OpenClaw Skills（含 bilibili-rag-local）
├── test/               # 测试脚本（需移动到根目录再运行）
└── README.md
```

---

## ✅ 常见问题

**Q：为什么有些音频 URL 可达、有些不可达？**  
A：B 站音频直链存在鉴权/过期/区域限制，只有公网可直接拉取的 URL 才可达。

---

> 免责声明：本项目仅供个人学习与技术研究，使用者需自行遵守相关平台协议与法律法规，禁止用于未授权的商业或违规用途。

---

## 📜 License

MIT

---

## 🧩 TodoList

- 对话存储、会话管理、检索历史对话记录
- 支持 B 站分 P 视频
- 适配更多 LLM 与向量模型
