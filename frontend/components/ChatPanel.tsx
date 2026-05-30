"use client";

import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { chatApi, knowledgeApi, KnowledgeStats, API_BASE_URL } from "@/lib/api";
import {
  ChatMessage,
  ConversationMeta,
  createConversationMeta,
  loadConversationMessages,
  loadConversations,
  normalizeUserKey,
  persistConversationMessages,
  persistConversations,
  removeConversationMessages,
  trimConversationTitle,
} from "@/lib/chatStorage";

interface Props {
  statsKey?: number;
  sessionId?: string;
  userKey?: string;
  folderIds?: number[];
}

const SAVE_THROTTLE_MS = 400;

export default function ChatPanel({ statsKey, sessionId, userKey, folderIds }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversations, setConversations] = useState<ConversationMeta[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<string>("");
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [stats, setStats] = useState<KnowledgeStats | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const saveTimerRef = useRef<number | null>(null);
  const hasLoadedRef = useRef(false);
  const marker = "[[SOURCES_JSON]]";
  const contentStartMarker = "[[CONTENT_START]]";

  const storageUserKey = normalizeUserKey(userKey);

  const persistMessagesNow = (conversationId: string, nextMessages: ChatMessage[]) => {
    persistConversationMessages(storageUserKey, conversationId, nextMessages);
  };

  const upsertConversationMeta = (conversationId: string, updater: (old: ConversationMeta) => ConversationMeta) => {
    setConversations((prev) => {
      const next = prev.map((item) => (item.id === conversationId ? updater(item) : item));
      persistConversations(storageUserKey, next);
      return next;
    });
  };

  const ensureConversation = () => {
    if (currentConversationId) return currentConversationId;
    const created = createConversationMeta();
    setConversations((prev) => {
      const next = [created, ...prev];
      persistConversations(storageUserKey, next);
      return next;
    });
    setCurrentConversationId(created.id);
    setMessages([]);
    return created.id;
  };

  useEffect(() => {
    knowledgeApi.getStats().then(setStats).catch(() => { });
  }, [statsKey]);

  useEffect(() => {
    if (!storageUserKey) {
      setConversations([]);
      setCurrentConversationId("");
      setMessages([]);
      hasLoadedRef.current = false;
      return;
    }

    const loaded = loadConversations(storageUserKey);

    if (loaded.length === 0) {
      const created = createConversationMeta();
      setConversations([created]);
      persistConversations(storageUserKey, [created]);
      setCurrentConversationId(created.id);
      setMessages([]);
      hasLoadedRef.current = true;
      return;
    }

    const active = loaded[0];
    setConversations(loaded);
    setCurrentConversationId(active.id);
    setMessages(loadConversationMessages(storageUserKey, active.id));
    hasLoadedRef.current = true;
  }, [storageUserKey]);

  useEffect(() => {
    if (!hasLoadedRef.current || !storageUserKey || !currentConversationId) return;
    if (saveTimerRef.current !== null) {
      window.clearTimeout(saveTimerRef.current);
    }
    saveTimerRef.current = window.setTimeout(() => {
      persistConversationMessages(storageUserKey, currentConversationId, messages);
      saveTimerRef.current = null;
    }, SAVE_THROTTLE_MS);

    return () => {
      if (saveTimerRef.current !== null) {
        window.clearTimeout(saveTimerRef.current);
        saveTimerRef.current = null;
      }
    };
  }, [messages, currentConversationId, storageUserKey]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // 点击下拉外部关闭
  useEffect(() => {
    if (!dropdownOpen) return;
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [dropdownOpen]);

  const switchConversation = (targetId: string) => {
    if (loading || targetId === currentConversationId) return;
    if (!storageUserKey) return;
    persistMessagesNow(currentConversationId, messages);
    setCurrentConversationId(targetId);
    setMessages(loadConversationMessages(storageUserKey, targetId));
  };

  const createNewConversation = () => {
    if (loading) return;
    const created = createConversationMeta();
    setConversations((prev) => {
      const next = [created, ...prev];
      persistConversations(storageUserKey, next);
      return next;
    });
    setCurrentConversationId(created.id);
    setMessages([]);
  };

  const clearCurrentConversation = () => {
    if (!currentConversationId) return;
    setMessages([]);
    persistMessagesNow(currentConversationId, []);
    upsertConversationMeta(currentConversationId, (old) => ({
      ...old,
      updatedAt: Date.now(),
    }));
  };

  const deleteCurrentConversation = () => {
    if (!currentConversationId || !storageUserKey || loading) return;
    if (!window.confirm("确认删除当前会话吗？")) return;

    removeConversationMessages(storageUserKey, currentConversationId);

    setConversations((prev) => {
      const next = prev.filter((item) => item.id !== currentConversationId);
      persistConversations(storageUserKey, next);
      if (next.length === 0) {
        const created = createConversationMeta();
        persistConversations(storageUserKey, [created]);
        setCurrentConversationId(created.id);
        setMessages([]);
        return [created];
      }
      setCurrentConversationId(next[0].id);
      setMessages(loadConversationMessages(storageUserKey, next[0].id));
      return next;
    });
  };

  const clearAllConversations = () => {
    if (!storageUserKey || loading) return;
    if (!window.confirm("确认清空全部会话吗？此操作不可撤销。")) return;

    conversations.forEach((item) => {
      removeConversationMessages(storageUserKey, item.id);
    });

    const created = createConversationMeta();
    persistConversations(storageUserKey, [created]);
    setConversations([created]);
    setCurrentConversationId(created.id);
    setMessages([]);
  };

  const send = async () => {
    if (!input.trim() || loading) return;
    const q = input.trim();
    setInput("");
    const activeConversationId = ensureConversation();
    const userId = Date.now().toString();
    const assistantId = (Date.now() + 1).toString();
    const needsTitle = (conversations.find((c) => c.id === activeConversationId)?.title ?? "新对话") === "新对话";
    setMessages((prev) => [
      ...prev,
      { id: userId, role: "user", content: q },
      { id: assistantId, role: "assistant", content: "", sources: [] },
    ]);
    upsertConversationMeta(activeConversationId, (old) => ({
      ...old,
      updatedAt: Date.now(),
    }));
    setLoading(true);

    // 流式完成后用于生成标题的 answer 文本
    let finalAnswer = "";

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
        }),
      });

      if (!response.ok || !response.body) {
        throw new Error("流式接口不可用");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let done = false;
      let answerBuffer = "";
      let pendingBuffer = "";
      let metadataParsed = false;
      let legacySourcesJson = "";
      let inLegacySources = false;
      let pendingSources: Array<{ bvid: string; title: string; url: string }> = [];

      const parseSources = (raw: string) => {
        if (!raw) return [];
        try {
          const parsed = JSON.parse(raw);
          if (Array.isArray(parsed)) {
            return parsed;
          }
        } catch {
          // 忽略解析错误，避免影响主文本
        }
        return [];
      };

      const revealSources = () => {
        if (pendingSources.length === 0) return;
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, sources: pendingSources } : m
          )
        );
      };

      const applyContent = () => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: answerBuffer } : m
          )
        );
      };

      while (!done) {
        const { value, done: doneReading } = await reader.read();
        done = doneReading;
        if (value) {
          const chunk = decoder.decode(value, { stream: !done });
          if (chunk) {
            if (!metadataParsed) {
              pendingBuffer += chunk;
              const markerIndex = pendingBuffer.indexOf(marker);
              const contentStartIndex = pendingBuffer.indexOf(contentStartMarker);

              if (markerIndex !== -1 && contentStartIndex !== -1 && markerIndex < contentStartIndex) {
                const rawSources = pendingBuffer.slice(markerIndex + marker.length, contentStartIndex);
                pendingSources = parseSources(rawSources);
                answerBuffer += pendingBuffer.slice(contentStartIndex + contentStartMarker.length);
                pendingBuffer = "";
                metadataParsed = true;
                applyContent();
              } else if (markerIndex === -1 && pendingBuffer.length > marker.length + contentStartMarker.length) {
                // 兼容没有元数据头的旧流式响应。
                answerBuffer += pendingBuffer;
                pendingBuffer = "";
                metadataParsed = true;
                applyContent();
              }
            } else {
              if (inLegacySources) {
                legacySourcesJson += chunk;
              } else {
                answerBuffer += chunk;
                const legacyMarkerIndex = answerBuffer.indexOf(marker);
                if (legacyMarkerIndex !== -1) {
                  legacySourcesJson = answerBuffer.slice(legacyMarkerIndex + marker.length);
                  answerBuffer = answerBuffer.slice(0, legacyMarkerIndex);
                  inLegacySources = true;
                }
              }
              applyContent();
            }
          }
        }
      }

      if (!metadataParsed && pendingBuffer) {
        const markerIndex = pendingBuffer.indexOf(marker);
        const contentStartIndex = pendingBuffer.indexOf(contentStartMarker);
        if (markerIndex !== -1 && contentStartIndex !== -1 && markerIndex < contentStartIndex) {
          pendingSources = parseSources(pendingBuffer.slice(markerIndex + marker.length, contentStartIndex));
          answerBuffer += pendingBuffer.slice(contentStartIndex + contentStartMarker.length);
        } else {
          answerBuffer += pendingBuffer;
        }
        applyContent();
      }
      if (legacySourcesJson) {
        pendingSources = parseSources(legacySourcesJson);
      }
      revealSources();
      finalAnswer = answerBuffer;
    } catch {
      try {
        const res = await chatApi.ask(q, sessionId, folderIds);
        finalAnswer = res.answer;
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

    // 自动生成标题：首轮问答结束后用 AI 生成
    if (needsTitle && finalAnswer) {
      try {
        const titleRes = await chatApi.generateTitle(q, finalAnswer);
        if (titleRes.title) {
          upsertConversationMeta(activeConversationId, (old) => ({
            ...old,
            title: titleRes.title,
            updatedAt: Date.now(),
          }));
        }
      } catch {
        // 生成标题失败时静默降级，不影响主流程
      }
    }
  };

  return (
    <div className="panel-inner">
      <div className="panel-header">
        <div className="chat-header-title">
          <div className="panel-title">对话工作台</div>
          {stats && stats.total_videos > 0 && (
            <div className="panel-subtitle">已收录 {stats.total_videos} 个视频</div>
          )}
        </div>
        <div className="panel-actions chat-actions">
          {/* 自定义对话下拉选择器 */}
          <div className={`conversation-dropdown${dropdownOpen ? " open" : ""}`} ref={dropdownRef}>
            <button
              className="conversation-dropdown-trigger"
              onClick={() => setDropdownOpen((v) => !v)}
              disabled={loading}
              title={conversations.find((c) => c.id === currentConversationId)?.title ?? "选择对话"}
            >
              <span className="conversation-dropdown-trigger-text">
                {conversations.find((c) => c.id === currentConversationId)?.title ?? "新对话"}
              </span>
              <span className="conversation-dropdown-chevron">
                ▼
              </span>
            </button>

            {dropdownOpen && (
              <div className="conversation-dropdown-menu">
                {conversations.length === 0 ? (
                  <div className="conversation-dropdown-empty">暂无对话</div>
                ) : (
                  <div className="conversation-dropdown-list">
                    {conversations.map((item) => (
                      <button
                        key={item.id}
                        className={`conversation-dropdown-item${item.id === currentConversationId ? " active" : ""}`}
                        onClick={() => {
                          switchConversation(item.id);
                          setDropdownOpen(false);
                        }}
                        title={item.title}
                      >
                        <span className="conversation-dropdown-item-label">{item.title}</span>
                        {conversations.length > 1 && (
                          <span
                            className="conversation-dropdown-item-delete"
                            title="删除此对话"
                            onClick={(e) => {
                              e.stopPropagation();
                              if (!storageUserKey || loading) return;
                              if (!window.confirm("确认删除此对话吗？")) return;
                              removeConversationMessages(storageUserKey, item.id);
                              setConversations((prev) => {
                                const next = prev.filter((c) => c.id !== item.id);
                                persistConversations(storageUserKey, next);
                                if (next.length === 0) {
                                  const created = createConversationMeta();
                                  persistConversations(storageUserKey, [created]);
                                  setCurrentConversationId(created.id);
                                  setMessages([]);
                                  setDropdownOpen(false);
                                  return [created];
                                }
                                if (item.id === currentConversationId) {
                                  setCurrentConversationId(next[0].id);
                                  setMessages(loadConversationMessages(storageUserKey, next[0].id));
                                }
                                setDropdownOpen(false);
                                return next;
                              });
                            }}
                          >
                            ×
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                )}
                <div className="conversation-dropdown-divider" />
                <button
                  className="conversation-dropdown-item-new"
                  onClick={() => {
                    createNewConversation();
                    setDropdownOpen(false);
                  }}
                  disabled={loading}
                >
                  + 新建对话
                </button>
              </div>
            )}
          </div>

          <button onClick={deleteCurrentConversation} disabled={loading || conversations.length === 0} className="btn btn-ghost" title="删除当前会话">
            删除
          </button>
          <button onClick={clearAllConversations} disabled={loading || conversations.length === 0} className="btn btn-ghost" title="清空全部会话">
            清空全部
          </button>
          {messages.length > 0 && (
            <button onClick={clearCurrentConversation} disabled={loading} className="btn btn-ghost" title="清空当前会话消息">
              清空当前
            </button>
          )}
        </div>
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
