# 会话总结缓存功能设计

> 日期: 2026-03-14
> 目标: 导出会话总结时缓存结果，避免重复消耗 Token

## 需求背景

- 当前每次导出总结都调用 LLM，浪费 Token
- 用户希望：导出后缓存结果，下次直接使用缓存
- 用户不满意时可手动刷新重新生成

## 数据模型

### 新建 SessionSummary 表

```python
class SessionSummary(Base):
    """会话总结缓存表"""
    __tablename__ = 'session_summaries'

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_session_id = Column(String(64), index=True, nullable=False)

    # 总结内容（Markdown 格式）
    content = Column(Text, nullable=False)

    # 元信息
    version = Column(Integer, default=1)          # 版本号
    source_video_count = Column(Integer)         # 关联视频数
    message_count = Column(Integer)              # 对话轮次
    token_used = Column(Integer)                 # 消耗的 token

    # 状态
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime)

    # 唯一约束
    __table_args__ = (
        UniqueConstraint('chat_session_id', 'version', name='uq_session_summary_session_version'),
    )
```

## API 设计

### 接口列表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/export/session-summary/{session_id}` | 获取总结（优先缓存） |
| POST | `/export/session-summary/{session_id}/refresh` | 强制刷新，重新生成 |
| DELETE | `/export/session-summary/{session_id}` | 删除总结缓存 |

### GET /export/session-summary/{session_id}

**响应：**
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

### POST /export/session-summary/{session_id}/refresh

**请求：**
```json
{
  "format": "full"
}
```

**响应：**
```json
{
  "success": true,
  "regenerated": true,
  "data": {
    "content": "# 新总结内容...",
    "version": 2,
    "source_video_count": 2,
    "message_count": 10,
    "created_at": "2026-03-14T10:05:00",
    "updated_at": "2026-03-14T10:05:00"
  }
}
```

## 后端实现

### 文件变更

1. `app/models.py` - 新增 SessionSummary 表
2. `app/routers/export.py` - 新增 3 个接口
3. `app/services/export.py` - 修改导出逻辑，增加缓存读写

### 核心逻辑

```python
async def get_session_summary(session_id: str) -> dict:
    # 1. 查询缓存
    summary = await db.get(SessionSummary, session_id)
    if summary:
        return {"has_cache": True, "data": summary}

    # 2. 无缓存，调用 LLM 生成
    content = await generate_summary(session_id)

    # 3. 存入缓存
    summary = SessionSummary(
        chat_session_id=session_id,
        content=content,
        version=1,
        ...
    )
    db.add(summary)
    await db.commit()

    return {"has_cache": False, "data": summary}

async def refresh_session_summary(session_id: str) -> dict:
    # 1. 删除旧缓存
    await db.delete(SessionSummary, session_id)

    # 2. 调用 LLM 生成新总结
    content = await generate_summary(session_id)

    # 3. 存入新缓存（版本号+1）
    summary = SessionSummary(
        chat_session_id=session_id,
        content=content,
        version=old_version + 1,
        ...
    )
    db.add(summary)
    await db.commit()

    return {"regenerated": True, "data": summary}
```

## 前端实现

### 文件变更

1. `frontend/lib/export.ts` - 新增 API 函数
2. `frontend/components/ExportModal.tsx` - 添加"重新生成"按钮

### UI 布局

```
┌─────────────────────────────────────────┐
│  导出总结                      [X]      │
├─────────────────────────────────────────┤
│                                         │
│  整体总结                               │
│  ...                                    │
│                                         │
│  核心知识点                             │
│  - 知识点1                             │
│  - 知识点2                             │
│                                         │
│  相关视频                               │
│  - 视频1                               │
│                                         │
├─────────────────────────────────────────┤
│  来源: 2个视频 · 8轮对话  版本: v1     │
│  [导出 Markdown]     [重新生成]         │
└─────────────────────────────────────────┘
```

### 按钮逻辑

- **导出 Markdown**：直接下载当前内容
- **重新生成**：弹出确认"重新生成会消耗 Token，是否继续？" → 调用刷新 API → 更新预览

## 缓存失效策略

| 场景 | 处理 |
|------|------|
| 首次导出 | 调用 LLM → 存入缓存 → 返回 |
| 再次导出 | 直接返回缓存 |
| 点击重新生成 | 删除旧缓存 → LLM 生成 → 新缓存 |
| 删除会话 | 级联删除缓存（可选） |

## 边界情况

| 情况 | 处理 |
|------|------|
| 缓存不存在 | 自动生成并缓存 |
| LLM 生成失败 | 返回错误，缓存不变 |
| 并发刷新 | 数据库事务保护 |
| 缓存过大 | 内容存 Text，限制长度 |
