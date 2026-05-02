"use client";

import { useState, useEffect, useCallback } from "react";
import { AlertCircle } from "lucide-react";
import { chatApi, type ChatSession } from "@/lib/api";
import { useDockContext } from "@/lib/dock-context";
import { ChatSidebarHeader } from "./ChatSidebarHeader";
import { ChatSidebarList } from "./ChatSidebarList";

interface ChatSidebarProps {
  sessionId: string | null;
  activeChatSessionId: string | null;
  onSelectSession: (id: string) => void;
  onCreateSession: () => Promise<void>;
  onClose?: () => void;
  inPanel?: boolean;
}

export function ChatSidebar({
  sessionId,
  activeChatSessionId,
  onSelectSession,
  onCreateSession,
  onClose,
  inPanel,
}: ChatSidebarProps) {
  const ctx = useDockContext();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSessions = useCallback(async () => {
    if (!sessionId) return;
    setIsLoading(true);
    setError(null);
    try {
      const res = await chatApi.listSessions(sessionId);
      setSessions(res.sessions);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "获取会话列表失败";
      setError(msg);
      console.error("获取会话列表失败", e);
    } finally {
      setIsLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  // 监听 page.tsx 的刷新信号（重命名/删除成功后触发）
  useEffect(() => {
    fetchSessions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ctx.sessionRefreshKey]);

  const handleCreate = async () => {
    setIsCreating(true);
    setError(null);
    try {
      await onCreateSession();
      await fetchSessions();
      onClose?.();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "创建会话失败";
      setError(msg);
      console.error("创建会话失败", e);
    } finally {
      setIsCreating(false);
    }
  };

  const handleRenameRequest = (id: string) => {
    const s = sessions.find((x) => x.chat_session_id === id);
    if (s) {
      ctx.setRenameDialog({ sessionId: s.chat_session_id, title: s.title ?? "" });
    }
  };

  const handleDeleteRequest = (id: string) => {
    const s = sessions.find((x) => x.chat_session_id === id);
    if (s) {
      ctx.setDeleteDialog({ sessionId: s.chat_session_id, title: s.title ?? "" });
    }
  };

  return (
    <aside className="sidebar-shell">
      <ChatSidebarHeader
        sessionCount={sessions.length}
        onCreateSession={handleCreate}
        isCreating={isCreating}
        showTitle={!inPanel}
      />

      {error && (
        <div className="sidebar-error">
          <AlertCircle className="size-3.5 shrink-0" />
          <span className="truncate">{error}</span>
        </div>
      )}

      <ChatSidebarList
        sessions={sessions}
        activeId={activeChatSessionId}
        isLoading={isLoading}
        onSelect={(id) => {
          onSelectSession(id);
          onClose?.();
        }}
        onRename={handleRenameRequest}
        onDelete={handleDeleteRequest}
        onCreateSession={handleCreate}
        isCreating={isCreating}
      />
    </aside>
  );
}
