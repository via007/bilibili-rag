"use client";

import {
  MessageSquareText,
  MoreHorizontal,
  Pencil,
  Trash2,
} from "lucide-react";
import { ChatSession } from "@/lib/api";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Card, CardContent } from "@/components/ui/card";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface ChatSidebarItemProps {
  session: ChatSession;
  isActive: boolean;
  onSelect: () => void;
  onRename: () => void;
  onDelete: () => void;
}

function formatSessionTitle(session: ChatSession): string {
  return session.title?.trim() || "新对话";
}

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return "";

  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);

  if (diffSec < 60) return "刚刚";
  if (diffMin < 60) return `${diffMin}分钟前`;
  if (diffHour < 24) return `${diffHour}小时前`;
  if (diffDay === 1) return "昨天";
  if (diffDay < 7) return `${diffDay}天前`;

  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${month}-${day}`;
}

export function ChatSidebarItem({
  session,
  isActive,
  onSelect,
  onRename,
  onDelete,
}: ChatSidebarItemProps) {
  const title = formatSessionTitle(session);
  const time = formatRelativeTime(session.updated_at);

  return (
    <div
      className="sidebar-item"
      onClick={onSelect}
      role="button"
      tabIndex={0}
      aria-pressed={isActive}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect();
        }
      }}
    >
      {isActive && <div className="sidebar-item-active-bar" />}

      <div className="sidebar-item-icon">
        <MessageSquareText className="size-4" />
      </div>

      <div className="sidebar-item-text">
        <Tooltip>
          <TooltipTrigger asChild>
            <p className="sidebar-item-title">{title}</p>
          </TooltipTrigger>
          <TooltipContent side="top" align="start">
            {title}
          </TooltipContent>
        </Tooltip>
        <p className="sidebar-item-time">{time}</p>
      </div>

      <div className="sidebar-item-actions">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              onClick={(e) => e.stopPropagation()}
              className="sidebar-action-btn"
            >
              <MoreHorizontal className="size-4" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="end"
            sideOffset={4}
            className="min-w-0 overflow-visible border-none bg-transparent p-0 shadow-none"
          >
            <Card className="min-w-[156px] overflow-visible rounded-xl border border-slate-100 bg-white py-0 shadow-lg shadow-black/[0.04] ring-0">
              <CardContent className="flex flex-col gap-1.5 p-2">
                <DropdownMenuItem
                  onSelect={onRename}
                  className="cursor-pointer gap-3 text-[13px] text-slate-600 hover:bg-slate-50/50 data-[highlighted]:bg-slate-50/50 data-[highlighted]:text-slate-600"
                >
                  <div className="ml-0.5 flex h-7 w-7 items-center justify-center rounded-md bg-slate-50">
                    <Pencil className="size-3.5 text-slate-400" />
                  </div>
                  重命名
                </DropdownMenuItem>
                <DropdownMenuItem
                  onSelect={onDelete}
                  className="cursor-pointer gap-3 text-[13px] text-red-500 hover:bg-red-50/40 data-[highlighted]:bg-red-50/40 data-[highlighted]:text-red-500"
                >
                  <div className="ml-0.5 flex h-7 w-7 items-center justify-center rounded-md bg-red-50">
                    <Trash2 className="size-3.5 text-red-400" />
                  </div>
                  删除
                </DropdownMenuItem>
              </CardContent>
            </Card>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}
