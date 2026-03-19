# 会话总结导出功能设计

> 日期: 2026-03-14
> 目标: 导出会话中 AI 回答的知识点总结（非问答格式）

## 需求理解

- 导出不包含用户提问，只导出 AI 回答内容
- 让 AI 总结自己的回答，罗列为知识点
- 按主题/类别自动分组
- 带上相关视频来源

## 导出格式

```markdown
# Python 学习总结

> 来源: 5 个视频 · 8 轮对话 · 2024-01-15

## 整体总结
本文档总结了用户在学习 Python 编程过程中涉及的核心知识点...

## 核心知识点

### 基础语法
- Python 使用缩进控制代码块
- 变量定义无需声明类型

### 数据类型
- 列表：有序可变集合
- 元组：有序不可变集合

### 函数定义
- 使用 def 关键字定义
- 支持默认参数和可变参数

## 相关视频
- [Python 入门教程](https://bilibili.com/xxx)
- [Python 进阶技巧](https://bilibili.com/xxx)
```

## API 设计

### 请求
```
POST /export/session-summary
Content-Type: application/json

{
  "chat_session_id": "xxx",
  "format": "full"  // full | simple
}
```

### 响应
```json
{
  "success": true,
  "filename": "session_summary_xxx.md",
  "content": "...",
  "size": 1234
}
```

## LLM 提示词

### 第一步：知识提取（JSON）

```
# 任务：对话知识提取与结构化

你是专业的知识整理专家，负责从 AI 对话记录中提取、组织和归类知识点。

## 输入内容
<AI 回答内容>

## 输出规范

### JSON Schema：
```json
{
  "summary": "整体总结，50-100 字",
  "categories": [
    {
      "name": "分类名称",
      "points": [
        {"content": "核心知识点，不超过 30 字", "detail": "补充说明，不超过 20 字"}
      ]
    }
  ],
  "sources": [{"title": "视频标题", "bvid": "BV号"}]
}
```

## 提取规则
1. 去重：相同知识点只保留最完整的
2. 归类：每个分类至少 2 个要点，否则合并
3. 精简：要点不超过 30 字
4. 排序：按重要程度和逻辑顺序

## 禁止包含
- 客套话（"下面为您介绍..."）
- 重复内容
- 背景铺垫
```

### 第二步：Markdown 生成

基于 JSON 生成 Markdown 格式文档。

## 后端实现

### 文件变更
1. `app/routers/export.py` - 新增 `/export/session-summary` 接口
2. `app/services/export.py` - 新增 `export_session_summary` 方法
3. 调用 LLM 进行知识提取

### 实现步骤
1. 获取会话所有 AI 回答（role=assistant）
2. 提取回答内容和来源
3. 调用 LLM 提取知识点（JSON 格式）
4. 生成 Markdown
5. 返回文件

## 前端实现

### 文件变更
1. `frontend/lib/export.ts` - 新增 `exportSessionSummary` 函数
2. `frontend/components/ChatPanel.tsx` - 导出按钮常驻，只有在有会话时才启用

### 接口对齐
- 前端调用 `/export/session-summary`
- 传入 `chat_session_id`
- 返回 `filename`, `content`, `size`

## 边界情况

| 情况 | 处理 |
|------|------|
| AI 回答为空 | 返回空知识点，保留基本信息 |
| 知识点太少 | 归为"综合"分类 |
| 无来源 | sources 为空数组 |
| 回答含代码 | 提取要点，代码保留在 detail |
