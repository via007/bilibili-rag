"use client";

import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Tabs } from "@base-ui/react";
import { nanoid } from "nanoid";
import { Loader2, AlertCircle, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  chatApi,
  knowledgeApi,
  KnowledgeStats,
  ChatMessage,
  ChatRequestPayload,
} from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { useDockContext } from "@/lib/dock-context";
import { useAppStore, LocalChatMessage } from "@/stores/app-store";

interface Props {
  isOpen?: boolean;
  onClose?: () => void;
}

// 合并消息：按 id 或 clientId 去重，后端数据优先，按时间正序排列
function mergeMessages(
  existing: LocalChatMessage[],
  incoming: LocalChatMessage[]
): LocalChatMessage[] {
  const map = new Map<string, LocalChatMessage>();

  for (const m of existing) {
    const key = m.id ? String(m.id) : m.clientId!;
    map.set(key, m);
  }

  for (const m of incoming) {
    const key = m.id ? String(m.id) : m.clientId!;
    const existingMsg = map.get(key);
    map.set(key, existingMsg ? { ...existingMsg, ...m } : m);
  }

  return Array.from(map.values()).sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  );
}

export default function ChatPanel({ isOpen, onClose }: Props) {
  const { sessionId, workspacePages, activeChatSessionId: chatSessionId } = useDockContext();
  const statsKey = useAppStore((s) => s.statsKey);
  const messages = useAppStore((s) => s.chatMessages);
  const setChatMessages = useAppStore((s) => s.setChatMessages);
  const clearChatMessages = useAppStore((s) => s.clearChatMessages);

  const [folderIds] = useState<number[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState<KnowledgeStats | null>(null);
  const [chatMode, setChatMode] = useState<"standard" | "agentic">("standard");
  const [showReasoning, setShowReasoning] = useState<Set<string>>(new Set());

  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [hasMore, setHasMore] = useState(false);

  const endRef = useRef<HTMLDivElement>(null);

  // 加载知识库统计
  useEffect(() => {
    knowledgeApi.getStats().then(setStats).catch(() => {});
  }, [statsKey]);

  // 自动滚动到底部
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // 当 chatSessionId 变化时加载历史消息
  useEffect(() => {
    if (!chatSessionId) {
      clearChatMessages();
      return;
    }

    setIsHistoryLoading(true);
    chatApi
      .getHistory(chatSessionId)
      .then((history) => {
        setChatMessages(history.messages);
        setHasMore(history.has_more);
      })
      .catch((e) => console.error("加载历史失败", e))
      .finally(() => setIsHistoryLoading(false));
  }, [chatSessionId]);

  const toggleReasoning = (msgId: string) => {
    setShowReasoning((prev) => {
      const next = new Set(prev);
      next.has(msgId) ? next.delete(msgId) : next.add(msgId);
      return next;
    });
  };

  const handleClear = () => {
    if (chatSessionId) {
      chatApi.clearHistory(chatSessionId).catch(() => {});
    }
    clearChatMessages();
  };

  const send = async () => {
    if (!input.trim() || loading) return;
    if (!chatSessionId) {
      console.error("chatSessionId 未初始化");
      return;
    }

    const q = input.trim();
    setInput("");

    const clientId = `client-${nanoid()}`;
    const assistantClientId = `client-${nanoid()}`;
    const now = new Date().toISOString();

    // 乐观更新：先显示用户消息 + assistant 占位
    const optimisticUser: LocalChatMessage = {
      id: 0,
      clientId,
      chat_session_id: chatSessionId,
      role: "user",
      content: q,
      status: "completed",
      created_at: now,
    };
    const optimisticAssistant: LocalChatMessage = {
      id: 0,
      clientId: assistantClientId,
      chat_session_id: chatSessionId,
      role: "assistant",
      content: "",
      status: "pending",
      created_at: now,
    };

    setChatMessages((prev) => mergeMessages(prev, [optimisticUser, optimisticAssistant]));
    setLoading(true);

    const payload: ChatRequestPayload = {
      question: q,
      session_id: sessionId ?? undefined,
      chat_session_id: chatSessionId,
      folder_ids: folderIds,
      workspace_pages: workspacePages,
    };

    // Agentic 模式：非流式
    if (chatMode === "agentic") {
      try {
        const res = await chatApi.askAgentic(payload);
        setChatMessages((prev) =>
          prev.map((m) =>
            m.clientId === assistantClientId
              ? {
                  ...m,
                  content: res.answer,
                  sources: res.sources,
                  reasoningSteps: res.reasoning_steps,
                  hopsUsed: res.hops_used,
                  avgRecallScore: res.avg_recall_score,
                  status: "completed" as const,
                }
              : m
          )
        );
      } catch (err) {
        setChatMessages((prev) =>
          prev.map((m) =>
            m.clientId === assistantClientId
              ? {
                  ...m,
                  status: "failed" as const,
                  error: err instanceof Error ? err.message : "请求失败",
                }
              : m
          )
        );
      }
      setLoading(false);

      // 刷新历史，用后端正式 id 替换临时消息
      try {
        const history = await chatApi.getHistory(chatSessionId);
        setChatMessages((prev) => mergeMessages(prev, history.messages));
      } catch (e) {
        console.error("刷新历史失败", e);
      }
      return;
    }

    // 标准模式：流式（SSE 解析）
    try {
      const stream = await chatApi.askStream(payload);
      const reader = stream.getReader();
      const decoder = new TextDecoder("utf-8");
      let done = false;
      let sseBuffer = "";
      let contentBuffer = "";

      while (!done) {
        const { value, done: doneReading } = await reader.read();
        done = doneReading;
        if (!value) continue;

        sseBuffer += decoder.decode(value, { stream: !done });
        const events = sseBuffer.split("\n\n");
        sseBuffer = events.pop() || "";

        for (const event of events) {
          const lines = event.split("\n");
          let dataLine = "";
          for (const line of lines) {
            if (line.startsWith("data:")) {
              dataLine = line.slice(5).trim();
            }
          }
          if (!dataLine) continue;

          try {
            const payload = JSON.parse(dataLine);
            if (payload.type === "chunk") {
              contentBuffer += payload.content || "";
              setChatMessages((prev) =>
                prev.map((m) =>
                  m.clientId === assistantClientId
                    ? { ...m, content: contentBuffer }
                    : m
                )
              );
            } else if (payload.type === "sources") {
              const sources = Array.isArray(payload.sources) ? payload.sources : [];
              setChatMessages((prev) =>
                prev.map((m) =>
                  m.clientId === assistantClientId ? { ...m, sources } : m
                )
              );
            } else if (payload.type === "error") {
              setChatMessages((prev) =>
                prev.map((m) =>
                  m.clientId === assistantClientId
                    ? {
                        ...m,
                        status: "failed" as const,
                        error: payload.message || "流式生成失败",
                      }
                    : m
                )
              );
            }
            // type === "done" 无需处理
          } catch {
            // 忽略单行解析失败，继续处理后续事件
          }
        }
      }
    } catch (e) {
      // SSE 失败，尝试降级为非流式
      try {
        const res = await chatApi.ask(payload);
        setChatMessages((prev) =>
          prev.map((m) =>
            m.clientId === assistantClientId
              ? {
                  ...m,
                  content: res.answer,
                  sources: res.sources,
                  status: "completed" as const,
                }
              : m
          )
        );
      } catch (err) {
        setChatMessages((prev) =>
          prev.map((m) =>
            m.clientId === assistantClientId
              ? {
                  ...m,
                  status: "failed" as const,
                  error: err instanceof Error ? err.message : "请求失败",
                }
              : m
          )
        );
      }
    }

    setLoading(false);

    // SSE 结束后刷新历史，用后端正式 id 替换临时消息
    try {
      const history = await chatApi.getHistory(chatSessionId);
      setChatMessages((prev) => mergeMessages(prev, history.messages));
    } catch (e) {
      console.error("刷新历史失败", e);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="panel-inner">
        <div className="panel-header">
          <div>
            <div className="panel-title">对话工作台</div>
            {stats && stats.total_videos > 0 && (
              <div className="panel-subtitle">已收录 {stats.total_videos} 个视频</div>
            )}
          </div>
          {messages.length > 0 && (
            <button
              onClick={handleClear}
              className="btn btn-ghost btn-sm"
              style={{ display: "flex", alignItems: "center", gap: 4 }}
            >
              <Trash2 className="h-3.5 w-3.5" />
              清空对话
            </button>
          )}
        </div>

        <div className="panel-body">
          <div className="chat-scroll">
            {isHistoryLoading && messages.length === 0 && (
              <div className="flex flex-col gap-3 p-4">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-4 w-1/2" />
                <Skeleton className="h-4 w-2/3" />
              </div>
            )}

            {messages.length === 0 && !isHistoryLoading ? (
              <div className="empty-state">
                <div>
                  <div className="status-pill">检索就绪</div>
                  <p className="text-sm text-[var(--muted-foreground)] mt-3">
                    把收藏夹变成可提问的知识库
                  </p>
                </div>
                <div className="prompt-grid">
                  {[
                    "总结收藏夹里最有价值的内容",
                    "有哪些适合快速复习的系列？",
                    "列出与某个主题相关的视频并给出关键点",
                    "按主题整理我的收藏夹内容",
                    "用一句话概括每个视频的重点",
                    "推荐3个最适合入门的学习视频",
                  ].map((q, i) => (
                    <button key={i} onClick={() => setInput(q)} className="prompt-chip">
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="chat-window">
                {messages.map((m) => (
                  <div
                    key={m.id ? String(m.id) : m.clientId}
                    className={cn("message", m.role)}
                  >
                    <div
                      className={cn(
                        "message-bubble",
                        m.status === "failed" && "message-bubble-failed"
                      )}
                    >
                      {/* Pending 状态 */}
                      {m.role === "assistant" && m.status === "pending" && !m.content ? (
                        <div className="flex flex-col gap-2">
                          <div className="flex items-center gap-2" style={{ color: "var(--muted-foreground)" }}>
                            <Loader2 className="h-4 w-4 animate-spin" />
                            <span className="text-sm">AI 思考中...</span>
                          </div>
                          <div className="flex flex-col gap-1.5">
                            <Skeleton className="h-3 w-full" />
                            <Skeleton className="h-3 w-4/5" />
                          </div>
                        </div>
                      ) : (
                        <ReactMarkdown className="markdown" remarkPlugins={[remarkGfm]}>
                          {m.content || " "}
                        </ReactMarkdown>
                      )}

                      {/* Failed 状态 */}
                      {m.status === "failed" && (
                        <div
                          style={{
                            marginTop: 8,
                            display: "flex",
                            alignItems: "center",
                            gap: 6,
                            padding: "6px 10px",
                            background: "rgba(199, 68, 58, 0.08)",
                            borderRadius: 8,
                          }}
                        >
                          <AlertCircle className="h-3.5 w-3.5" style={{ color: "var(--danger)" }} />
                          <span style={{ fontSize: 12, color: "var(--danger)" }}>
                            {m.error || "回答生成失败"}
                          </span>
                        </div>
                      )}

                      {/* 推理过程 */}
                      {m.reasoningSteps && m.reasoningSteps.length > 0 && (
                        <div
                          style={{
                            marginTop: 10,
                            paddingTop: 10,
                            borderTop: "1px dashed rgba(0,0,0,0.15)",
                          }}
                        >
                          <button
                            onClick={() =>
                              toggleReasoning(m.id ? String(m.id) : m.clientId!)
                            }
                            style={{
                              fontSize: 12,
                              color: "var(--accent-strong)",
                              background: "none",
                              border: "none",
                              cursor: "pointer",
                              padding: 0,
                              display: "flex",
                              alignItems: "center",
                              gap: 4,
                              fontFamily: "inherit",
                            }}
                          >
                            <span>
                              {showReasoning.has(m.id ? String(m.id) : m.clientId!)
                                ? "▼"
                                : "▶"}
                            </span>
                            推理过程 ({m.reasoningSteps.length} 步
                            {m.avgRecallScore != null
                              ? `, 召回 ${m.avgRecallScore.toFixed(2)}`
                              : ""}
                            )
                          </button>
                          {showReasoning.has(
                            m.id ? String(m.id) : m.clientId!
                          ) && (
                            <div style={{ marginTop: 8, display: "grid", gap: 8 }}>
                              {m.reasoningSteps.map((step, i) => (
                                <div
                                  key={i}
                                  style={{
                                    padding: "8px 10px",
                                    background: "rgba(47, 124, 120, 0.06)",
                                    borderRadius: 8,
                                    fontSize: 12,
                                    lineHeight: 1.5,
                                  }}
                                >
                                  <div
                                    style={{
                                      fontWeight: 600,
                                      color: "var(--teal)",
                                      marginBottom: 4,
                                    }}
                                  >
                                    Step {step.step}: {step.action}
                                  </div>
                                  <div
                                    style={{
                                      color: "var(--ink-soft)",
                                      marginBottom: 2,
                                    }}
                                  >
                                    <span style={{ opacity: 0.6 }}>Query: </span>
                                    {step.query}
                                  </div>
                                  <div
                                    style={{
                                      color: "var(--ink-soft)",
                                      marginBottom: 2,
                                    }}
                                  >
                                    {step.reasoning}
                                  </div>
                                  {step.verdict && (
                                    <div
                                      style={{
                                        color:
                                          step.verdict === "sufficient"
                                            ? "var(--teal)"
                                            : "var(--accent-strong)",
                                        fontWeight: 500,
                                      }}
                                    >
                                      Verdict: {step.verdict}
                                    </div>
                                  )}
                                  {step.recall_score != null && (
                                    <div style={{ opacity: 0.6 }}>
                                      Recall: {step.recall_score.toFixed(3)}
                                    </div>
                                  )}
                                  {step.sources.length > 0 && (
                                    <div
                                      style={{
                                        marginTop: 4,
                                        display: "flex",
                                        flexWrap: "wrap",
                                        gap: 4,
                                      }}
                                    >
                                      {step.sources.map((s, j) => (
                                        <a
                                          key={j}
                                          href={s.url}
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          style={{
                                            fontSize: 11,
                                            color: "var(--accent-strong)",
                                          }}
                                        >
                                          {s.title}
                                        </a>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}

                      {/* 来源链接 */}
                      {m.sources && m.sources.length > 0 && (
                        <div className="source-list">
                          {m.sources.map((s, i) => (
                            <a
                              key={i}
                              href={s.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="source-link"
                            >
                              {s.title}
                            </a>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
                <div ref={endRef} />
              </div>
            )}
          </div>
        </div>

        <div className="panel-footer">
          <div className="mb-4">
            <Tabs.Root
              value={chatMode}
              onValueChange={(v) => setChatMode(v as "standard" | "agentic")}
            >
              <Tabs.List className="mode-tabs-list">
                <Tabs.Indicator className="mode-tabs-indicator" />
                <Tabs.Tab value="standard" className="mode-tabs-tab">
                  标准模式
                </Tabs.Tab>
                <Tabs.Tab value="agentic" className="mode-tabs-tab">
                  Agentic RAG
                </Tabs.Tab>
              </Tabs.List>
            </Tabs.Root>
          </div>
          <div className="flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send()}
              placeholder="输入问题..."
              className="input"
            />
            <button onClick={send} disabled={!input.trim() || loading} className="btn btn-primary">
              发送
            </button>
          </div>
        </div>
    </div>
  );
}
