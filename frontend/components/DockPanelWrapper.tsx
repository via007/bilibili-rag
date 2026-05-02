"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import FloatingPanel from "./FloatingPanel";

interface DockPanelWrapperProps {
  panelKey: string;
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  originEl?: HTMLElement | null;
  defaultSize?: { width: number; height: number };
  className?: string;
}

export default function DockPanelWrapper({
  panelKey,
  isOpen,
  onClose,
  title,
  children,
  originEl,
  defaultSize = { width: 380, height: 600 },
  className,
}: DockPanelWrapperProps) {
  const [origin, setOrigin] = useState({ x: 0, y: 0 });

  useEffect(() => {
    if (originEl && isOpen) {
      const rect = originEl.getBoundingClientRect();
      setOrigin({
        x: rect.left + rect.width / 2,
        y: rect.top,
      });
    }
  }, [originEl, isOpen]);

  // 默认 origin 为屏幕中心（避免第一帧从左上角缩放）
  const defaultOrigin = typeof window !== "undefined"
    ? { x: window.innerWidth / 2, y: window.innerHeight }
    : { x: 0, y: 0 };

  const activeOrigin = origin.x === 0 && origin.y === 0 ? defaultOrigin : origin;

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          key={panelKey}
          className="dock-panel-wrapper"
          initial={{ scale: 0.08, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.08, opacity: 0 }}
          transition={{
            type: "spring",
            stiffness: 280,
            damping: 22,
          }}
          style={{
            position: "fixed",
            zIndex: 49,
            transformOrigin: `${activeOrigin.x}px ${activeOrigin.y}px`,
          }}
        >
          <FloatingPanel
            isOpen={true}
            onClose={onClose}
            title={title}
            defaultSize={defaultSize}
            className={className}
          >
            {children}
          </FloatingPanel>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
