"use client";

import { useEffect, useRef, useState } from "react";

interface RenameDialogProps {
  open: boolean;
  currentTitle: string;
  onOpenChange: (open: boolean) => void;
  onConfirm: (title: string) => void | Promise<void>;
}

export function ChatSidebarRenameDialog({
  open,
  currentTitle,
  onOpenChange,
  onConfirm,
}: RenameDialogProps) {
  const [title, setTitle] = useState(currentTitle);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setTitle(currentTitle);
      setIsSubmitting(false);
      const id = requestAnimationFrame(() => {
        inputRef.current?.focus();
        inputRef.current?.select();
      });
      return () => cancelAnimationFrame(id);
    }
  }, [open, currentTitle]);

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

  const trimmed = title.trim();
  const canSubmit = trimmed.length > 0 && trimmed !== currentTitle.trim();

  const handleSubmit = async () => {
    if (!canSubmit || isSubmitting) return;
    setIsSubmitting(true);
    try {
      await onConfirm(trimmed);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSubmit();
    }
  };

  if (!open) return null;

  return (
    <div className="modal-overlay" onClick={() => onOpenChange(false)}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-header">
          <div className="dialog-title">重命名对话</div>
          <div className="dialog-desc">给这个会话起一个新名字</div>
        </div>

        <div className="dialog-content">
          <input
            ref={inputRef}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入会话名称"
            className="dialog-input"
            disabled={isSubmitting}
          />
        </div>

        <div className="dialog-footer">
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            disabled={isSubmitting}
            className="btn-cancel"
          >
            取消
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!canSubmit || isSubmitting}
            className="btn-confirm"
          >
            {isSubmitting ? "保存中..." : "确认"}
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
        .dialog-content {
          padding: 0 28px 20px;
        }
        .dialog-input {
          width: 100%;
          height: 42px;
          padding: 0 14px;
          border-radius: 12px;
          border: 1px solid #dbeafe;
          background: #f8fbff;
          font-size: 14px;
          color: #1e293b;
          outline: none;
          transition: border-color 0.15s ease, box-shadow 0.15s ease;
          font-family: inherit;
        }
        .dialog-input:focus {
          border-color: #3b82f6;
          box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
        }
        .dialog-input::placeholder {
          color: #94a3b8;
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
        .btn-confirm {
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
          background: #2563eb;
          color: #ffffff;
        }
        .btn-confirm:hover:not(:disabled) {
          background: #1d4ed8;
        }
        .btn-confirm:disabled {
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
