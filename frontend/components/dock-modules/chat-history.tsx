"use client";

import { useCallback } from "react";
import { useDockContext } from "@/lib/dock-context";
import { ChatSidebar } from "@/components/chat-sidebar";
import type { DockPanelProps } from "@/lib/dock-registry";

export default function ChatHistoryPanel({ isOpen, onClose }: DockPanelProps) {
  const ctx = useDockContext();

  const handleSelect = useCallback(
    (id: string) => {
      ctx.onSelectSession(id);
      onClose();
    },
    [ctx, onClose]
  );

  const handleCreate = useCallback(async () => {
    await ctx.onCreateSession();
    onClose();
  }, [ctx, onClose]);

  if (!isOpen) return null;

  return (
    <ChatSidebar
      sessionId={ctx.sessionId}
      activeChatSessionId={ctx.activeChatSessionId}
      onSelectSession={handleSelect}
      onCreateSession={handleCreate}
      onClose={onClose}
      inPanel
    />
  );
}
