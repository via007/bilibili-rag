"use client";

import { ChatSession } from "@/lib/api";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ChatSidebarEmpty } from "./ChatSidebarEmpty";
import { ChatSidebarItem } from "./ChatSidebarItem";

interface ChatSidebarListProps {
  sessions: ChatSession[];
  activeId: string | null;
  isLoading: boolean;
  onSelect: (id: string) => void;
  onRename: (id: string) => void;
  onDelete: (id: string) => void;
  onCreateSession: () => void;
  isCreating?: boolean;
}

export function ChatSidebarList({
  sessions,
  activeId,
  isLoading,
  onSelect,
  onRename,
  onDelete,
  onCreateSession,
  isCreating,
}: ChatSidebarListProps) {
  if (isLoading) {
    return (
      <div className="sidebar-skeleton-box">
        <Skeleton className="h-11 rounded-xl" />
        <Skeleton className="h-11 rounded-xl" />
        <Skeleton className="h-11 rounded-xl" />
      </div>
    );
  }

  if (sessions.length === 0) {
    return (
      <ScrollArea className="flex-1">
        <ChatSidebarEmpty
          onCreateSession={onCreateSession}
          isCreating={isCreating}
        />
      </ScrollArea>
    );
  }

  return (
    <TooltipProvider delay={300}>
      <ScrollArea className="sidebar-list">
        <div className="sidebar-list-inner">
          {sessions.map((session) => (
            <ChatSidebarItem
              key={session.chat_session_id}
              session={session}
              isActive={session.chat_session_id === activeId}
              onSelect={() => onSelect(session.chat_session_id)}
              onRename={() => onRename(session.chat_session_id)}
              onDelete={() => onDelete(session.chat_session_id)}
            />
          ))}
        </div>
      </ScrollArea>
    </TooltipProvider>
  );
}
