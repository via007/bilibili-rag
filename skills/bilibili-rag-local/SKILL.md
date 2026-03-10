---
name: "bilibili-rag-local"
description: "使用本地 Bilibili RAG 服务进行检索与问答。用户询问 B 站收藏夹内容、视频要点总结、来源追溯、入库状态时使用。"
---

# Bilibili RAG Local

面向本地运行的 `bilibili-rag` 服务（默认 `http://127.0.0.1:8000`）。

## 执行前检查

1. 检查服务可达：优先调用 `GET /knowledge/stats`。
2. 若不可达，明确提示“本地服务未启动或端口不是 8000”，不要编造结果。

## 主要能力

1. 检索片段：调用 `POST /chat/search?query=<问题>&k=5`。
2. 问答总结：调用 `POST /chat/ask`，请求体包含：
`question`、`session_id`（可选）、`folder_ids`（可选）。
3. 入库状态：调用 `GET /knowledge/folders/status?session_id=<session_id>`。

## 返回格式要求

1. 先给结论，再给证据。
2. 证据优先来自接口返回的 `sources` 或 `search results`。
3. 每条证据给出 `title + url`，必要时补充 `bvid`。
4. 当无召回时，明确说明“当前知识库没有命中内容”，并建议用户同步/更新收藏夹后重试。

## 交互策略

1. 用户是闲聊或无关问题时，简短回复后再引导回收藏夹知识问答。
2. 用户问题具体且与视频内容相关时，优先调用 `/chat/ask`，不要只按标题猜测回答。

## 安全边界

1. 不输出任何 Cookie、Token、SESSDATA 等敏感信息。
2. 不执行与本地 `bilibili-rag` 无关的高风险系统命令。
3. 仅使用用户本机可访问的服务地址，不主动访问未知公网接口。
