"use client";

import { WorkspacePage } from "@/lib/api";

interface Props {
  workspacePages: WorkspacePage[];
  onRemove?: (bvid: string, cid: number) => void;
  onClear?: () => void;
  onOpenVideo?: (bvid: string) => void;
}

export default function WorkspacePanel({ workspacePages, onRemove, onClear, onOpenVideo }: Props) {
  if (workspacePages.length === 0) {
    return (
      <div className="workspace-empty">
        <div className="text-base mb-2 opacity-40">📌</div>
        <div>工作区为空</div>
        <div className="text-xs mt-1 opacity-60">从左侧收藏夹勾选分P加入工作区</div>
      </div>
    );
  }

  return (
    <div className="workspace-list">
      {workspacePages.map((page) => (
        <div key={`${page.bvid}-${page.cid}`} className="workspace-item">
          <div className="flex-1 min-w-0">
            <div
              className="workspace-item-title cursor-pointer hover:text-[var(--accent)]"
              onClick={() => onOpenVideo?.(page.bvid)}
              title={page.page_title || `P${page.page_index + 1}`}
            >
              {page.page_title || `P${page.page_index + 1}`}
            </div>
            <div className="workspace-item-meta">
              {page.bvid}
            </div>
          </div>
          <button
            className="remove-btn"
            onClick={() => onRemove?.(page.bvid, page.cid)}
            title="移出工作区"
          >
            ×
          </button>
        </div>
      ))}
      {workspacePages.length > 1 && (
        <button
          onClick={onClear}
          className="text-xs text-[var(--muted)] hover:text-[var(--danger)] text-center mt-2 py-1 border border-dashed border-[var(--border)] rounded-lg transition-colors"
        >
          清空全部 ({workspacePages.length})
        </button>
      )}
    </div>
  );
}
