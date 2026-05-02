"use client";

import { MessageSquarePlus } from "lucide-react";

interface ChatSidebarEmptyProps {
  onCreateSession: () => void;
  isCreating?: boolean;
}

export function ChatSidebarEmpty({
  onCreateSession,
  isCreating,
}: ChatSidebarEmptyProps) {
  return (
    <div className="sidebar-empty">
      <div className="sidebar-empty-icon">
        <MessageSquarePlus className="size-5" />
      </div>
      <div className="space-y-1">
        <p className="sidebar-empty-title">还没有历史对话</p>
        <p className="sidebar-empty-hint">点击上方按钮开始新对话</p>
      </div>
      <button
        type="button"
        onClick={onCreateSession}
        disabled={isCreating}
        className="sidebar-new-btn"
      >
        新建对话
      </button>
    </div>
  );
}
