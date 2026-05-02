"use client";

import { useState, useRef, useCallback, useEffect, ReactNode } from "react";

type ResizeDir = "none" | "e" | "s" | "se";

interface FloatingPanelProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  defaultPosition?: { x: number; y: number };
  defaultSize?: { width: number; height: number };
  className?: string;
}

const MIN_WIDTH = 280;
const MIN_HEIGHT = 320;

function clampPosition(x: number, y: number, w: number, h: number) {
  const maxX = typeof window !== "undefined" ? window.innerWidth - w : x;
  const maxY = typeof window !== "undefined" ? window.innerHeight - h : y;
  return {
    x: Math.max(0, Math.min(x, maxX)),
    y: Math.max(0, Math.min(y, maxY)),
  };
}

function clampSize(w: number, h: number) {
  const maxW = typeof window !== "undefined" ? window.innerWidth : w;
  const maxH = typeof window !== "undefined" ? window.innerHeight : h;
  return {
    width: Math.max(MIN_WIDTH, Math.min(w, maxW)),
    height: Math.max(MIN_HEIGHT, Math.min(h, maxH)),
  };
}

export default function FloatingPanel({
  isOpen,
  onClose,
  title,
  children,
  defaultPosition = { x: 80, y: 80 },
  defaultSize = { width: 380, height: 600 },
  className,
}: FloatingPanelProps) {
  const [position, setPosition] = useState(() =>
    clampPosition(defaultPosition.x, defaultPosition.y, defaultSize.width, defaultSize.height)
  );
  const [size, setSize] = useState(() => clampSize(defaultSize.width, defaultSize.height));
  const [isDragging, setIsDragging] = useState(false);
  const [isResizing, setIsResizing] = useState(false);

  const modeRef = useRef<"drag" | "resize" | "none">("none");
  const resizeDirRef = useRef<ResizeDir>("none");
  const dragStartRef = useRef({ x: 0, y: 0, posX: 0, posY: 0 });
  const resizeStartRef = useRef({ x: 0, y: 0, width: 0, height: 0 });

  // Pointer event handlers via ref to avoid closure staleness
  const handlePointerMoveRef = useRef<(e: PointerEvent) => void>(() => {});
  const handlePointerUpRef = useRef<() => void>(() => {});

  handlePointerMoveRef.current = (e: PointerEvent) => {
    if (modeRef.current === "drag") {
      const dx = e.clientX - dragStartRef.current.x;
      const dy = e.clientY - dragStartRef.current.y;
      const nextX = dragStartRef.current.posX + dx;
      const nextY = dragStartRef.current.posY + dy;
      setPosition(clampPosition(nextX, nextY, size.width, size.height));
    } else if (modeRef.current === "resize") {
      const dx = e.clientX - resizeStartRef.current.x;
      const dy = e.clientY - resizeStartRef.current.y;
      const dir = resizeDirRef.current;
      const nextW =
        dir === "e" || dir === "se"
          ? resizeStartRef.current.width + dx
          : size.width;
      const nextH =
        dir === "s" || dir === "se"
          ? resizeStartRef.current.height + dy
          : size.height;
      setSize(clampSize(nextW, nextH));
    }
  };

  handlePointerUpRef.current = () => {
    modeRef.current = "none";
    resizeDirRef.current = "none";
    setIsDragging(false);
    setIsResizing(false);
    document.body.style.userSelect = "";
    document.body.style.cursor = "";
    if (typeof window !== "undefined") {
      window.removeEventListener("pointermove", handlePointerMoveRef.current);
      window.removeEventListener("pointerup", handlePointerUpRef.current);
    }
  };

  useEffect(() => {
    if (!isDragging && !isResizing) return;

    const onMove = (e: PointerEvent) => handlePointerMoveRef.current(e);
    const onUp = () => handlePointerUpRef.current();

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    document.body.style.userSelect = "none";

    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
    };
  }, [isDragging, isResizing]);

  const handleHeaderPointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      dragStartRef.current = {
        x: e.clientX,
        y: e.clientY,
        posX: position.x,
        posY: position.y,
      };
      modeRef.current = "drag";
      setIsDragging(true);
      document.body.style.cursor = "grabbing";
    },
    [position]
  );

  const handleResizePointerDown = useCallback(
    (e: React.PointerEvent, dir: ResizeDir) => {
      e.preventDefault();
      e.stopPropagation();
      resizeStartRef.current = {
        x: e.clientX,
        y: e.clientY,
        width: size.width,
        height: size.height,
      };
      resizeDirRef.current = dir;
      modeRef.current = "resize";
      setIsResizing(true);
      document.body.style.cursor =
        dir === "se" ? "nwse-resize" : dir === "e" ? "ew-resize" : "ns-resize";
    },
    [size]
  );

  if (!isOpen) return null;

  return (
    <div
      className={`floating-panel${className ? ` ${className}` : ""}`}
      style={{
        position: "fixed",
        left: position.x,
        top: position.y,
        width: size.width,
        height: size.height,
        zIndex: 49,
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* 可拖拽标题栏 */}
      <div
        className="floating-panel-header"
        onPointerDown={handleHeaderPointerDown}
        style={{ cursor: isDragging ? "grabbing" : "grab" }}
      >
        <span className="floating-panel-title">{title}</span>
        <button
          onClick={onClose}
          className="floating-panel-close"
          aria-label="关闭"
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      {/* 内容区 */}
      <div className="floating-panel-body">{children}</div>

      {/* 右边缘 resize */}
      <div
        className="resize-handle resize-handle-e"
        onPointerDown={(e) => handleResizePointerDown(e, "e")}
        title="左右拖拽调整宽度"
      />

      {/* 下边缘 resize */}
      <div
        className="resize-handle resize-handle-s"
        onPointerDown={(e) => handleResizePointerDown(e, "s")}
        title="上下拖拽调整高度"
      />

      {/* 右下角 resize */}
      <div
        className="resize-handle resize-handle-se"
        onPointerDown={(e) => handleResizePointerDown(e, "se")}
        title="拖拽调整大小"
      >
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
          <path d="M10 14L14 10V14H10Z" fill="currentColor" opacity="0.5"/>
          <path d="M5 14L14 5V10L10 14H5Z" fill="currentColor" opacity="0.3"/>
        </svg>
      </div>
    </div>
  );
}
