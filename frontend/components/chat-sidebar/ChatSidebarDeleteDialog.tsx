"use client";

import { useEffect, useState } from "react";

interface DeleteDialogProps {
  open: boolean;
  sessionTitle: string;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void | Promise<void>;
}

export function ChatSidebarDeleteDialog({
  open,
  sessionTitle,
  onOpenChange,
  onConfirm,
}: DeleteDialogProps) {
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onOpenChange(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  useEffect(() => {
    if (!open) return;
    const original = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = original;
    };
  }, [open]);

  if (!open) return null;

  const handleConfirm = async () => {
    if (isDeleting) return;
    setIsDeleting(true);
    try {
      await onConfirm();
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={() => onOpenChange(false)}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-header">
          <div className="dialog-title">删除对话</div>
          <div className="dialog-desc">
            确定要删除对话「{sessionTitle || "未命名对话"}」吗？此操作不可恢复。
          </div>
        </div>

        <div className="dialog-footer">
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            disabled={isDeleting}
            className="btn-cancel"
          >
            取消
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={isDeleting}
            className="btn-danger"
          >
            {isDeleting ? "删除中..." : "删除"}
          </button>
        </div>
      </div>

      <style jsx>{`
        .modal-overlay {
          position: fixed;
          inset: 0;
          background: rgba(20, 16, 12, 0.4);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 50;
          animation: fadeIn 0.2s ease;
        }
        .modal-card {
          width: min(360px, 92vw);
          background: rgba(255, 255, 255, 0.96);
          border: 1px solid #dbeafe;
          border-radius: 20px;
          box-shadow: 0 22px 50px rgba(20, 16, 12, 0.25);
          animation: fadeUp 0.3s ease;
          overflow: hidden;
        }
        .dialog-header {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 8px;
          padding: 28px 28px 20px;
        }
        .dialog-title {
          font-size: 18px;
          font-weight: 600;
          color: #1e293b;
          text-align: center;
          line-height: 1.4;
        }
        .dialog-desc {
          font-size: 14px;
          color: #64748b;
          text-align: center;
          line-height: 1.6;
        }
        .dialog-footer {
          display: flex;
          justify-content: space-between;
          gap: 10px;
          padding: 0 28px 28px;
        }
        .btn-cancel {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          height: 38px;
          padding: 0 20px;
          border-radius: 10px;
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.15s ease;
          border: 1px solid #dbeafe;
          background: transparent;
          color: #3b82f6;
        }
        .btn-cancel:hover:not(:disabled) {
          background: #eff6ff;
        }
        .btn-cancel:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        .btn-danger {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          height: 38px;
          padding: 0 20px;
          border-radius: 10px;
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.15s ease;
          border: 1px solid transparent;
          background: #dc2626;
          color: #ffffff;
        }
        .btn-danger:hover:not(:disabled) {
          background: #b91c1c;
        }
        .btn-danger:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes fadeUp {
          from {
            opacity: 0;
            transform: translateY(10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>
    </div>
  );
}
