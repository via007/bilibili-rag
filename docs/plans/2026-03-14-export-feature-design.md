# 知识点导出功能设计

> 日期: 2026-03-14
> 状态: 已完成

## 1. 需求概述

用户需要将知识库中的内容导出为 Markdown 格式文件，支持多种导出范围和内容格式。

### 功能范围

| 范围 | 说明 | 触发位置 |
|------|------|----------|
| 单个视频 | 导出指定视频的完整/精简内容 | 视频详情页 |
| 整个收藏夹 | 导出收藏夹内所有视频内容 | 收藏夹列表（支持多选） |
| 当前会话 | 导出当前对话的问答记录 | 会话详情页 |
| 会话总结 | AI 知识点提取 + 缓存 | 会话详情页 |

### 内容格式

- **完整格式**: 包含摘要、内容提纲、原文内容
- **精简格式**: 仅包含摘要和核心要点

---

## 2. 导出格式示例

### 2.1 视频导出 - 完整格式

```markdown
# 视频标题

> 来源: B站 | 作者: xxx | 时长: xx:xx | 发布时间: xxxx-xx-xx

## 摘要
[AI 生成的视频摘要]

## 内容提纲
- 要点1
- 要点2

## 原文内容
[视频字幕完整内容]
```

### 2.2 视频导出 - 精简格式

```markdown
# 视频标题

## 摘要
[AI 生成的视频摘要]

## 核心要点
- 要点1
- 要点2
```

### 2.3 收藏夹导出

支持多选收藏夹，格式同上，每个收藏夹用 `---` 分隔。

### 2.4 会话导出（原版 - 问答格式）

```markdown
# 会话标题

> 创建时间: xxxx-xx-xx

## 对话记录

### 用户
问题内容

---
### AI回答
回答内容
*来源: BVxxxx*

---
```

### 2.5 会话总结导出（AI 知识点提取）

```markdown
# Python 学习总结

> 来源: 2 个视频 · 8 轮对话 · 2026-03-14

## 整体总结
介绍了 Python 核心数据结构的特点与使用场景...

## 核心知识点

### 列表（List）
- 有序可变的数据结构（支持增删改查）
- 常用方法：append/remove/pop

### 元组（Tuple）
- 有序不可变的集合
- 适合存储常量

## 相关视频
- [Python 入门教程](https://bilibili.com/xxx)
```

---

## 3. 后端 API

### 3.1 视频导出

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/export/video` | 导出单个视频 |

**请求**:
```json
{
  "bvid": "BVxxxx",
  "format": "full"
}
```

**响应**:
```json
{
  "success": true,
  "filename": "video_xxx.md",
  "content": "# markdown...",
  "size": 12345
}
```

### 3.2 收藏夹导出

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/export/folder` | 导出收藏夹（支持多选） |

**请求**:
```json
{
  "folder_ids": [1, 2, 3],
  "format": "full"
}
```

### 3.3 会话导出

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/export/session` | 导出会话（问答格式） |

### 3.4 会话总结导出

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/export/session-summary/{id}` | 获取缓存总结 |
| POST | `/export/session-summary/{id}/refresh` | 重新生成 |
| DELETE | `/export/session-summary/{id}` | 删除缓存 |

**GET 响应**:
```json
{
  "success": true,
  "has_cache": true,
  "data": {
    "content": "# 总结内容...",
    "version": 1,
    "source_video_count": 2,
    "message_count": 8,
    "created_at": "2026-03-14T10:00:00",
    "updated_at": "2026-03-14T10:00:00"
  }
}
```

---

## 4. 前端设计

### 4.1 导出按钮位置

| 位置 | 按钮行为 |
|------|----------|
| SourcesPanel | 常驻显示，需勾选收藏夹 |
| ChatPanel | 仅在有会话时显示 |

### 4.2 导出预览弹窗

- 左侧: Markdown 预览
- 右侧: 操作面板
  - 格式选择（视频/收藏夹）
  - 缓存状态（会话总结）
  - 下载按钮
  - 重新生成按钮（会话总结）
  - 复制按钮

---

## 5. 缓存机制

### 5.1 SessionSummary 表

```python
class SessionSummary(Base):
    id = Column(Integer, primary_key=True)
    chat_session_id = Column(String(64), index=True)
    content = Column(Text)           # Markdown 内容
    version = Column(Integer)        # 版本号
    source_video_count = Column(Integer)
    message_count = Column(Integer)
    token_used = Column(Integer)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
```

### 5.2 缓存逻辑

| 场景 | 处理 |
|------|------|
| 首次导出 | 调用 LLM → 存入缓存 → 返回 |
| 再次导出 | 直接返回缓存 |
| 点击重新生成 | 删除旧缓存 → LLM 生成 → 新缓存 |

---

## 6. LLM 提示词

### 6.1 知识提取提示词

详见 `app/services/export.py` 中的 `_extract_knowledge()` 方法。

**核心要点**:
- 角色: 资深知识整理专家
- 提取: 事实性知识点
- 归类: 按技术主题分类
- 精简: 每个要点不超过 25 字
- 禁止: 客套话、背景铺垫、冗余表达

### 6.2 Few-Shot 示例

提供正确和错误示例，确保输出质量。

---

## 7. 文件变更

### 后端

| 文件 | 变更 |
|------|------|
| `app/models.py` | 新增 SessionSummary 表 |
| `app/routers/export.py` | 新增 6 个 API 端点 |
| `app/services/export.py` | 新增导出方法和缓存逻辑 |

### 前端

| 文件 | 变更 |
|------|------|
| `frontend/lib/export.ts` | 新增 API 函数 |
| `frontend/components/ExportModal.tsx` | 新增缓存状态和重新生成 |
| `frontend/components/ChatPanel.tsx` | 按钮改为"导出总结" |
| `frontend/components/SourcesPanel.tsx` | 按钮常驻，需勾选 |

---

## 8. 状态

✅ 已完成
