"use client";

import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { chatApi, knowledgeApi, KnowledgeStats, API_BASE_URL } from "@/lib/api";
import { useSession } from "./SessionManager";
import ExportModal from "./ExportModal";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Array<{ bvid: string; title: string; url: string }>;
}

interface Props {
  statsKey?: number;
  sessionId?: string;
  folderIds?: number[];
  chatSessionId?: string;
  onSessionUpdate?: (sessionId: string) => void;
}

export default function ChatPanel({ statsKey, sessionId, folderIds, chatSessionId, onSessionUpdate }: Props) {
  const { messages: sessionMessages, messagesLoading, loadMessages } = useSession();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState<KnowledgeStats | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const marker = "[[SOURCES_JSON]]";

  // 加载知识库统计
  useEffect(() => {
    knowledgeApi.getStats().then(setStats).catch(() => { });
  }, [statsKey]);

  // 加载会话历史消息
  useEffect(() => {
    if (chatSessionId) {
      loadMessages(chatSessionId);
    }
  }, [chatSessionId, loadMessages]);

  // 将会话消息转换为界面消息
  useEffect(() => {
    if (sessionMessages.length > 0) {
      const convertedMessages: Message[] = sessionMessages.map((m, index) => ({
        id: `msg-${m.id}`,
        role: m.role,
        content: m.content,
        sources: m.sources as Message["sources"],
      }));
      setMessages(convertedMessages);
    }
  }, [sessionMessages]);

  // 自动滚动到底部
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

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
          chat_session_id: chatSessionId || null,
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

      // 如果有 chatSessionId，刷新消息列表
      if (chatSessionId) {
        loadMessages(chatSessionId);
      }
    } catch (e) {
      try {
        const res = await chatApi.ask(q, sessionId, folderIds);
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
        {chatSessionId && (
          <button
            onClick={() => setExportOpen(true)}
            className="btn btn-ghost"
            title="导出AI总结"
          >
            导出总结
          </button>
        )}
      </div>

      <div className="panel-body">
        <div className="chat-scroll">
          {messagesLoading ? (
            <div className="flex items-center justify-center h-full">
              <div style={{ color: 'var(--text-tertiary)' }}>加载历史消息...</div>
            </div>
          ) : messages.length === 0 ? (
            <div className="empty-state">
              <div>
                <div className="status-pill">检索就绪</div>
                <p className="text-sm mt-3" style={{ color: 'var(--text-secondary)' }}>把收藏夹变成可提问的知识库</p>
              </div>
              <div className="prompt-grid">
                {[
                  { icon: "📚", q: "总结收藏夹里最有价值的内容" },
                  { icon: "🔄", q: "有哪些适合快速复习的系列？" },
                  { icon: "🔍", q: "列出与某个主题相关的视频并给出关键点" },
                  { icon: "📋", q: "按主题整理我的收藏夹内容" },
                  { icon: "⚡", q: "用一句话概括每个视频的重点" },
                  { icon: "🎯", q: "推荐3个最适合入门的学习视频" },
                ].map((item, i) => (
                  <button key={i} onClick={() => setInput(item.q)} className="prompt-chip">
                    <span className="prompt-chip-icon">{item.icon}</span>
                    <span className="prompt-chip-text">{item.q}</span>
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
                        <div key={i} className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ backgroundColor: 'var(--text-tertiary)', animationDelay: `${i * 0.15}s` }} />
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

      {/* 导出弹窗 - 会话总结 */}
      <ExportModal
        isOpen={exportOpen}
        onClose={() => setExportOpen(false)}
        type="session-summary"
        chatSessionId={chatSessionId}
      />
    </div>
  );
}
