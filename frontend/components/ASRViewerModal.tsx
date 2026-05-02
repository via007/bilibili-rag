"use client";

import { useState, useEffect, useCallback } from "react";
import {
  asrApi,
  vecPageApi,
  ASRContentResponse,
  ASRTaskStatus,
  VectorPageStatusResponse,
} from "@/lib/api";

interface ASRViewerModalProps {
  isOpen: boolean;
  onClose: () => void;
  bvid: string;
  cid: number;
  pageIndex: number;
  pageTitle: string;
  onVectorizationDone?: (bvid: string, cid: number, status: VectorPageStatusResponse) => void;
}

type ModalMode = "view" | "edit" | "loading" | "saving";

export default function ASRViewerModal({
  isOpen,
  onClose,
  bvid,
  cid,
  pageIndex,
  pageTitle,
  onVectorizationDone,
}: ASRViewerModalProps) {
  const [mode, setMode] = useState<ModalMode>("loading");
  const [content, setContent] = useState<string>("");
  const [editContent, setEditContent] = useState<string>("");
  const [source, setSource] = useState<string>("");
  const [version, setVersion] = useState<number>(0);
  const [isProcessed, setIsProcessed] = useState<boolean>(false);
  const [taskStatus, setTaskStatus] = useState<ASRTaskStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 向量化状态
  const [vecStatus, setVecStatus] = useState<VectorPageStatusResponse | null>(null);
  const [vecError, setVecError] = useState<string | null>(null);
  const [isVecLoading, setIsVecLoading] = useState(false);

  // 加载向量状态
  const loadVecStatus = useCallback(async () => {
    try {
      const status = await vecPageApi.getStatus(bvid, cid);
      setVecStatus(status);
      setVecError(status.vector_error || null);
    } catch {
      // 向量状态获取失败不影响主流程
    }
  }, [bvid, cid]);

  // 加载内容
  const loadContent = useCallback(async () => {
    setMode("loading");
    setError(null);
    try {
      const data = await asrApi.getContent(bvid, cid);
      if (data.exists) {
        setContent(data.content || "");
        setSource(data.content_source || "unknown");
        setVersion(data.version || 0);
        setIsProcessed(data.is_processed || false);
        setEditContent(data.content || "");
        setMode("view");
      } else {
        setContent("");
        setSource("");
        setVersion(0);
        setIsProcessed(false);
        setMode("view");
      }
    } catch (e) {
      setError("加载失败，请稍后重试");
      setMode("view");
    }
  }, [bvid, cid]);

  // 打开弹窗时加载
  useEffect(() => {
    if (isOpen) {
      loadContent();
      loadVecStatus();
    }
  }, [isOpen, loadContent, loadVecStatus]);

  // 轮询任务状态
  const pollStatus = useCallback(async (taskId: string) => {
    const poll = async () => {
      const status = await asrApi.getStatus(taskId);
      setTaskStatus(status);
      if (status.status === "done") {
        await loadContent();
        setTaskStatus(null);
      } else if (status.status === "failed") {
        await loadContent();
        setTaskStatus(null);
      } else {
        setTimeout(poll, 1000);
      }
    };
    poll();
  }, [loadContent]);

  // 发起 ASR
  const handleCreate = async () => {
    setError(null);
    try {
      const res = await asrApi.create({
        bvid,
        cid,
        page_index: pageIndex,
        page_title: pageTitle,
      });
      if (res.task_id) {
        pollStatus(res.task_id);
      } else {
        // 已是最新（幂等返回 task_id=null）
        await loadContent();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "ASR 启动失败");
    }
  };

  // 向量化
  const handleVectorize = async () => {
    setVecError(null);
    try {
      const resp = await vecPageApi.create({
        bvid,
        cid,
        page_index: pageIndex,
        page_title: pageTitle,
      });
      if (resp.task_id) {
        setIsVecLoading(true);
        for (let i = 0; i < 60; i++) {
          await new Promise((r) => setTimeout(r, 1000));
          const taskStatus = await vecPageApi.getTaskStatus(resp.task_id);
          if (taskStatus.status === "done") {
            const newStatus = await vecPageApi.getStatus(bvid, cid);
            setVecStatus(newStatus);
            onVectorizationDone?.(bvid, cid, newStatus);
            setIsVecLoading(false);
            return;
          }
          if (taskStatus.status === "failed") {
            setVecError(taskStatus.message);
            const latestStatus = await vecPageApi.getStatus(bvid, cid);
            setVecStatus(latestStatus);
            onVectorizationDone?.(bvid, cid, latestStatus);
            setIsVecLoading(false);
            return;
          }
        }
        setVecError("向量化超时");
        setIsVecLoading(false);
        const latestStatus = await vecPageApi.getStatus(bvid, cid);
        setVecStatus(latestStatus);
        onVectorizationDone?.(bvid, cid, latestStatus);
      } else {
        await loadVecStatus();
        const latestStatus = await vecPageApi.getStatus(bvid, cid);
        setVecStatus(latestStatus);
        onVectorizationDone?.(bvid, cid, latestStatus);
      }
    } catch {
      setVecError("向量化请求失败");
    }
  };

  // 重新 ASR
  const handleReasr = async () => {
    setError(null);
    try {
      const res = await asrApi.reasr({ bvid, cid, page_index: pageIndex });
      if (res.task_id) {
        pollStatus(res.task_id);
      }
    } catch (e) {
      setError("重新 ASR 失败");
    }
  };

  // 保存编辑
  const handleSave = async () => {
    setMode("saving");
    setError(null);
    try {
      await asrApi.update({ bvid, cid, page_index: pageIndex, content: editContent });
      await loadContent();
    } catch (e) {
      setError("保存失败");
      setMode("edit");
    }
  };

  // 取消编辑
  const handleCancelEdit = () => {
    setEditContent(content);
    setMode("view");
  };

  // 关闭弹窗
  const handleClose = () => {
    setContent("");
    setEditContent("");
    setSource("");
    setVersion(0);
    setIsProcessed(false);
    setTaskStatus(null);
    setError(null);
    setVecStatus(null);
    setVecError(null);
    setIsVecLoading(false);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={handleClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        {/* 头部 */}
        <div className="modal-header">
          <h3 className="modal-title">{pageTitle}</h3>
          <button className="modal-close" onClick={handleClose}>
            ×
          </button>
        </div>

        {/* 元信息栏 */}
        <div className="modal-meta">
          <span>版本: v{version}</span>
          <span>来源: {source === "asr" ? "ASR" : source === "user_edit" ? "用户编辑" : "未知"}</span>
          <span>状态: {isProcessed ? "已处理" : "未处理"}</span>
          {taskStatus && (
            <span className="text-[var(--accent)]">
              {taskStatus.status === "processing" && `ASR: ${taskStatus.message}`}
              {taskStatus.status === "pending" && `ASR: ${taskStatus.message}`}
              {taskStatus.status === "done" && "ASR完成"}
              {taskStatus.status === "failed" && `ASR失败: ${taskStatus.message}`}
            </span>
          )}
          {mode === "view" && isProcessed && (
            <button className="modal-reasr-btn" onClick={handleReasr}>
              重新ASR
            </button>
          )}
          {/* 向量化状态 pill */}
          <span
            className={`status-pill ${
              vecStatus?.is_vectorized === "done"
                ? "ok"
                : vecStatus?.is_vectorized === "failed"
                ? "error"
                : vecStatus?.is_vectorized === "processing"
                ? "partial"
                : "empty"
            }`}
          >
            向量:{" "}
            {vecStatus?.is_vectorized === "done"
              ? `已入库(${vecStatus.vector_chunk_count}块)`
              : vecStatus?.is_vectorized === "failed"
              ? "失败"
              : vecStatus?.is_vectorized === "processing"
              ? "处理中"
              : "未处理"}
          </span>
          {isVecLoading && <span className="text-[var(--accent)]">向量化中...</span>}
          {vecError && (
            <span className="text-xs text-red-500" title={vecError}>
              ⚠ {vecError.slice(0, 30)}
            </span>
          )}
        </div>

        {/* 错误提示 */}
        {error && <div className="modal-error">{error}</div>}

        {/* 内容区 */}
        <div className="modal-content-wrapper">
          {mode === "loading" && (
            <div className="modal-loading">加载中...</div>
          )}
          {mode === "saving" && (
            <div className="modal-loading">保存中...</div>
          )}
          {(mode === "view" || mode === "edit") && (
            <>
              {mode === "view" ? (
                <div className="modal-content-text">
                  {content ? (
                    <pre className="whitespace-pre-wrap">{content}</pre>
                  ) : (
                    <div className="text-[var(--muted-foreground)] text-sm">
                      暂无内容
                      <button className="modal-start-btn ml-4" onClick={handleCreate}>
                        开始ASR
                      </button>
                    </div>
                  )}
                </div>
              ) : (
                <textarea
                  className="modal-edit-textarea"
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  placeholder="输入内容..."
                />
              )}
            </>
          )}
        </div>

        {/* 底部按钮 */}
        <div className="modal-footer">
          {mode === "view" && !isVecLoading && (
            <button
              className="modal-vector-btn"
              onClick={handleVectorize}
              style={{
                marginRight: "auto",
                padding: "8px 20px",
                fontSize: "14px",
                background: "var(--accent, #00a1d6)",
                color: "white",
                border: "none",
                borderRadius: "6px",
                cursor: "pointer",
              }}
            >
              {!isProcessed
                ? "ASR+Vector"
                : vecStatus?.is_vectorized === "done"
                ? "Revector"
                : vecStatus?.is_vectorized === "processing"
                ? "Vectorizing..."
                : "Vectorize"}
            </button>
          )}
          {isVecLoading && (
            <span className="text-sm text-[var(--muted-foreground)]" style={{ marginRight: "auto" }}>
              向量化中...
            </span>
          )}
          {mode === "view" && isProcessed && (
            <button className="modal-edit-btn" onClick={() => setMode("edit")}>
              编辑
            </button>
          )}
          {mode === "edit" && (
            <>
              <button className="modal-cancel-btn" onClick={handleCancelEdit}>
                取消
              </button>
              <button className="modal-save-btn" onClick={handleSave}>
                保存编辑
              </button>
            </>
          )}
        </div>
      </div>

      <style jsx>{`
        .modal-overlay {
          position: fixed;
          inset: 0;
          background: rgba(0, 0, 0, 0.5);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 50;
        }
        .modal-card {
          background: var(--paper, #f7f1e8);
          border-radius: 12px;
          max-width: 640px;
          width: 90vw;
          max-height: 80vh;
          overflow: hidden;
          display: flex;
          flex-direction: column;
          box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
        }
        .modal-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 16px 20px;
          border-bottom: 1px solid rgba(0,0,0,0.1);
        }
        .modal-title {
          font-size: 16px;
          font-weight: 600;
          color: var(--text-primary, #1a1a1a);
          margin: 0;
        }
        .modal-close {
          width: 28px;
          height: 28px;
          border: none;
          background: transparent;
          font-size: 20px;
          cursor: pointer;
          color: var(--muted, #666);
          border-radius: 4px;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .modal-close:hover {
          background: rgba(0,0,0,0.05);
        }
        .modal-meta {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 12px 20px;
          font-size: 12px;
          color: var(--muted, #666);
          border-bottom: 1px solid rgba(0,0,0,0.05);
          flex-wrap: wrap;
        }
        .modal-reasr-btn {
          margin-left: auto;
          padding: 4px 12px;
          font-size: 12px;
          background: var(--accent, #00a1d6);
          color: white;
          border: none;
          border-radius: 4px;
          cursor: pointer;
        }
        .modal-reasr-btn:hover {
          opacity: 0.9;
        }
        .modal-error {
          padding: 8px 20px;
          font-size: 12px;
          color: #e74c3c;
          background: rgba(231, 76, 60, 0.1);
        }
        .modal-content-wrapper {
          flex: 1;
          overflow: auto;
          padding: 16px 20px;
        }
        .modal-loading {
          text-align: center;
          padding: 40px;
          color: var(--muted, #666);
          font-size: 14px;
        }
        .modal-content-text {
          font-size: 14px;
          line-height: 1.6;
          color: var(--text-primary, #1a1a1a);
        }
        .modal-content-text pre {
          margin: 0;
          white-space: pre-wrap;
          word-break: break-word;
        }
        .modal-start-btn {
          padding: 4px 12px;
          font-size: 12px;
          background: var(--accent, #00a1d6);
          color: white;
          border: none;
          border-radius: 4px;
          cursor: pointer;
        }
        .modal-edit-textarea {
          width: 100%;
          min-height: 200px;
          padding: 12px;
          font-size: 14px;
          line-height: 1.6;
          border: 1px solid rgba(0,0,0,0.15);
          border-radius: 8px;
          resize: vertical;
          font-family: inherit;
          background: white;
        }
        .modal-edit-textarea:focus {
          outline: none;
          border-color: var(--accent, #00a1d6);
        }
        .modal-footer {
          display: flex;
          justify-content: flex-end;
          gap: 8px;
          padding: 16px 20px;
          border-top: 1px solid rgba(0,0,0,0.1);
        }
        .modal-edit-btn {
          padding: 8px 20px;
          font-size: 14px;
          background: var(--accent, #00a1d6);
          color: white;
          border: none;
          border-radius: 6px;
          cursor: pointer;
        }
        .modal-edit-btn:hover {
          opacity: 0.9;
        }
        .modal-cancel-btn {
          padding: 8px 20px;
          font-size: 14px;
          background: transparent;
          color: var(--muted, #666);
          border: 1px solid rgba(0,0,0,0.15);
          border-radius: 6px;
          cursor: pointer;
        }
        .modal-cancel-btn:hover {
          background: rgba(0,0,0,0.03);
        }
        .modal-save-btn {
          padding: 8px 20px;
          font-size: 14px;
          background: var(--accent, #00a1d6);
          color: white;
          border: none;
          border-radius: 6px;
          cursor: pointer;
        }
        .modal-save-btn:hover {
          opacity: 0.9;
        }
      `}</style>
    </div>
  );
}
