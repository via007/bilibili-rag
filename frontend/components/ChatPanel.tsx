"use client";

import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Tabs } from "@base-ui/react";
import { chatApi, knowledgeApi, KnowledgeStats, API_BASE_URL, WorkspacePage, ReasoningStep } from "@/lib/api";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Array<{ bvid: string; title: string; url: string }>;
  reasoningSteps?: ReasoningStep[];
  hopsUsed?: number;
  avgRecallScore?: number;
}

interface Props {
  statsKey?: number;
  sessionId?: string;
  folderIds?: number[];
  workspacePages?: WorkspacePage[];
}

export default function ChatPanel({ statsKey, sessionId, folderIds, workspacePages }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState<KnowledgeStats | null>(null);
  const [chatMode, setChatMode] = useState<"standard" | "agentic">("standard");
  const [showReasoning, setShowReasoning] = useState<Set<string>>(new Set());
  const endRef = useRef<HTMLDivElement>(null);
  const marker = "[[SOURCES_JSON]]";

  useEffect(() => {
    knowledgeApi.getStats().then(setStats).catch(() => { });
  }, [statsKey]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const toggleReasoning = (msgId: string) => {
    setShowReasoning((prev) => {
      const next = new Set(prev);
      next.has(msgId) ? next.delete(msgId) : next.add(msgId);
      return next;
    });
  };

  const send = async () => {
    if (!input.trim() || loading) return;
    const q = input.trim();
    setInput("");
    const userId = Date.now().toString();
    const assistantId = (Date.now() + 1).toString();
    setMessages((prev) => [
      ...prev,
      { id: userId, role: "user", content: q },
      { id: assistantId, role: "assistant", content: "", sources: [] },
    ]);
    setLoading(true);

    // Agentic 模式：非流式，直接返回完整结果
    if (chatMode === "agentic") {
      try {
        const res = await chatApi.askAgentic({
          question: q,
          session_id: sessionId,
          folder_ids: folderIds,
          workspace_pages: workspacePages,
        });
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  content: res.answer,
                  sources: res.sources,
                  reasoningSteps: res.reasoning_steps,
                  hopsUsed: res.hops_used,
                  avgRecallScore: res.avg_recall_score,
                }
              : m
          )
        );
      } catch (err) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: `错误: ${err instanceof Error ? err.message : "请求失败"}` }
              : m
          )
        );
      }
      setLoading(false);
      return;
    }

    // 标准模式：流式
    try {
      const response = await fetch(`${API_BASE_URL}/chat/ask/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          question: q,
          session_id: sessionId,
          folder_ids: folderIds,
          workspace_pages: workspacePages,
        }),
      });

      if (!response.ok || !response.body) {
        throw new Error("流式接口不可用");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let done = false;
      let buffer = "";
      let sourcesJson = "";
      let inSources = false;

      while (!done) {
        const { value, done: doneReading } = await reader.read();
        done = doneReading;
        if (value) {
          const chunk = decoder.decode(value, { stream: !done });
          if (chunk) {
            if (inSources) {
              sourcesJson += chunk;
            } else {
              buffer += chunk;
              const markerIndex = buffer.indexOf(marker);
              if (markerIndex !== -1) {
                const contentPart = buffer.slice(0, markerIndex);
                sourcesJson = buffer.slice(markerIndex + marker.length);
                buffer = contentPart;
                inSources = true;
              }
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, content: buffer } : m
                )
              );
            }
          }
        }
      }

      if (sourcesJson) {
        try {
          const parsed = JSON.parse(sourcesJson);
          if (Array.isArray(parsed)) {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, sources: parsed } : m
              )
            );
          }
        } catch {
          // 忽略解析错误，避免影响主文本
        }
      }
    } catch (e) {
      try {
        const res = await chatApi.ask({ question: q, session_id: sessionId, folder_ids: folderIds, workspace_pages: workspacePages });
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: res.answer, sources: res.sources } : m
          )
        );
      } catch (err) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  content: `错误: ${err instanceof Error ? err.message : "请求失败"}`,
                }
              : m
          )
        );
      }
    }
    setLoading(false);
  };

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
          <button onClick={() => setMessages([])} className="btn btn-ghost" title="清空">
            清空对话
          </button>
        )}
      </div>

      <div className="panel-body">
        <div className="chat-scroll">
          {messages.length === 0 ? (
            <div className="empty-state">
              <div>
                <div className="status-pill">检索就绪</div>
                <p className="text-sm text-[var(--muted)] mt-3">把收藏夹变成可提问的知识库</p>
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
                <div key={m.id} className={`message ${m.role}`}>
                  <div className="message-bubble">
                    <ReactMarkdown className="markdown" remarkPlugins={[remarkGfm]}>
                      {m.content}
                    </ReactMarkdown>
                    {m.reasoningSteps && m.reasoningSteps.length > 0 && (
                      <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px dashed rgba(0,0,0,0.15)" }}>
                        <button
                          onClick={() => toggleReasoning(m.id)}
                          style={{ fontSize: 12, color: "var(--accent-strong)", background: "none", border: "none", cursor: "pointer", padding: 0, display: "flex", alignItems: "center", gap: 4, fontFamily: "inherit" }}
                        >
                          <span>{showReasoning.has(m.id) ? "▼" : "▶"}</span>
                          推理过程 ({m.reasoningSteps.length} 步{m.avgRecallScore != null ? `, 召回 ${m.avgRecallScore.toFixed(2)}` : ""})
                        </button>
                        {showReasoning.has(m.id) && (
                          <div style={{ marginTop: 8, display: "grid", gap: 8 }}>
                            {m.reasoningSteps.map((step, i) => (
                              <div key={i} style={{ padding: "8px 10px", background: "rgba(47, 124, 120, 0.06)", borderRadius: 8, fontSize: 12, lineHeight: 1.5 }}>
                                <div style={{ fontWeight: 600, color: "var(--teal)", marginBottom: 4 }}>
                                  Step {step.step}: {step.action}
                                </div>
                                <div style={{ color: "var(--ink-soft)", marginBottom: 2 }}>
                                  <span style={{ opacity: 0.6 }}>Query: </span>{step.query}
                                </div>
                                <div style={{ color: "var(--ink-soft)", marginBottom: 2 }}>
                                  {step.reasoning}
                                </div>
                                {step.verdict && (
                                  <div style={{ color: step.verdict === "sufficient" ? "var(--teal)" : "var(--accent-strong)", fontWeight: 500 }}>
                                    Verdict: {step.verdict}
                                  </div>
                                )}
                                {step.recall_score != null && (
                                  <div style={{ opacity: 0.6 }}>
                                    Recall: {step.recall_score.toFixed(3)}
                                  </div>
                                )}
                                {step.sources.length > 0 && (
                                  <div style={{ marginTop: 4, display: "flex", flexWrap: "wrap", gap: 4 }}>
                                    {step.sources.map((s, j) => (
                                      <a key={j} href={s.url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 11, color: "var(--accent-strong)" }}>
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
                    {m.sources && m.sources.length > 0 && (
                      <div className="source-list">
                        {m.sources.map((s, i) => (
                          <a key={i} href={s.url} target="_blank" rel="noopener noreferrer" className="source-link">
                            {s.title}
                          </a>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {loading && (
                <div className="message assistant">
                  <div className="message-bubble">
                    <div className="flex gap-1">
                      {[0, 1, 2].map((i) => (
                        <div key={i} className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-pulse" style={{ animationDelay: `${i * 0.15}s` }} />
                      ))}
                    </div>
                  </div>
                </div>
              )}
              <div ref={endRef} />
            </div>
          )}
        </div>
      </div>

      <div className="panel-footer">
        <div className="mb-2">
          <Tabs.Root value={chatMode} onValueChange={(v) => setChatMode(v as "standard" | "agentic")}>
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
