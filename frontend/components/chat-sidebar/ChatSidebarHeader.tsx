"use client";

import { Plus } from "lucide-react";

interface ChatSidebarHeaderProps {
  sessionCount: number;
  onCreateSession: () => void;
  isCreating: boolean;
  showTitle?: boolean;
}

export function ChatSidebarHeader({
  sessionCount,
  onCreateSession,
  isCreating,
  showTitle = true,
}: ChatSidebarHeaderProps) {
  return (
    <div className="sidebar-header">
      {showTitle && (
        <div className="sidebar-header-title">
          <span>历史对话</span>
          <span className="sidebar-header-badge">{sessionCount}</span>
        </div>
      )}
      <button
        type="button"
        onClick={onCreateSession}
        disabled={isCreating}
        className="sidebar-new-btn"
      >
        <Plus className="size-4" />
        新建对话
      </button>
    </div>
  );
}
