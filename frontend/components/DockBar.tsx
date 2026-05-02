"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { DockModule } from "@/lib/dock-registry";

interface DockBarProps {
  modules: DockModule[];
  activePanelId: string | null;
  onTogglePanel: (id: string, originEl: HTMLElement | null) => void;
}

export default function DockBar({ modules, activePanelId, onTogglePanel }: DockBarProps) {
  const [isVisible, setIsVisible] = useState(false);
  const leaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isMouseOnDock = useRef(false);
  const iconRefs = useRef<Map<string, HTMLButtonElement>>(new Map());

  // 面板打开时强制显示；面板关闭时，若鼠标不在 dock 上则延迟隐藏
  useEffect(() => {
    if (activePanelId) {
      setIsVisible(true);
    } else if (!isMouseOnDock.current) {
      leaveTimerRef.current = setTimeout(() => {
        setIsVisible(false);
      }, 300);
    }
  }, [activePanelId]);

  // 清理定时器
  useEffect(() => {
    return () => {
      if (leaveTimerRef.current) {
        clearTimeout(leaveTimerRef.current);
      }
    };
  }, []);

  const clearLeaveTimer = () => {
    if (leaveTimerRef.current) {
      clearTimeout(leaveTimerRef.current);
      leaveTimerRef.current = null;
    }
  };

  const handleTriggerEnter = () => {
    clearLeaveTimer();
    setIsVisible(true);
  };

  const handleDockEnter = () => {
    isMouseOnDock.current = true;
    clearLeaveTimer();
  };

  const handleDockLeave = () => {
    isMouseOnDock.current = false;
    if (activePanelId) return;
    leaveTimerRef.current = setTimeout(() => {
      setIsVisible(false);
    }, 300);
  };

  return (
    <>
      {/* 底部触发区：鼠标移入时显示 dock */}
      <div
        className="dock-trigger-zone"
        onMouseEnter={handleTriggerEnter}
      />

      <AnimatePresence>
        {isVisible && (
          <motion.nav
            className="dock-bar"
            initial={{ y: 120, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 120, opacity: 0 }}
            transition={{ type: "spring", stiffness: 260, damping: 20 }}
            onMouseEnter={handleDockEnter}
            onMouseLeave={handleDockLeave}
          >
            <div className="dock-backdrop" />
            <div className="dock-items" role="toolbar" aria-label="功能面板">
              {modules.map((mod, index) => (
                <motion.div
                  key={mod.id}
                  initial={{ y: 20, opacity: 0 }}
                  animate={{ y: 0, opacity: 1 }}
                  transition={{
                    delay: index * 0.04,
                    type: "spring",
                    stiffness: 300,
                    damping: 20,
                  }}
                >
                  <DockIcon
                    module={mod}
                    isActive={activePanelId === mod.id}
                    ref={(el) => {
                      if (el) iconRefs.current.set(mod.id, el);
                      else iconRefs.current.delete(mod.id);
                    }}
                    onClick={() => {
                      const el = iconRefs.current.get(mod.id) ?? null;
                      onTogglePanel(mod.id, el);
                    }}
                  />
                </motion.div>
              ))}
            </div>
          </motion.nav>
        )}
      </AnimatePresence>
    </>
  );
}

interface DockIconProps {
  module: { id: string; icon: React.ComponentType<{ className?: string }>; title: string };
  isActive: boolean;
  ref: (el: HTMLButtonElement | null) => void;
  onClick: () => void;
}

function DockIcon({ module, isActive, ref, onClick }: DockIconProps) {
  const [hovered, setHovered] = useState(false);
  const Icon = module.icon;

  return (
    <motion.button
      ref={ref}
      className={`dock-icon ${isActive ? "active" : ""}`}
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      whileHover={{ scale: 1.25, y: -8 }}
      whileTap={{ scale: 0.92 }}
      transition={{ type: "spring", stiffness: 400, damping: 17 }}
      title={module.title}
      role="button"
      aria-pressed={isActive}
      aria-label={module.title}
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
    >
      <Icon className="w-6 h-6" />
      {isActive && <span className="dock-indicator" aria-hidden="true" />}
      {hovered && (
        <span className="dock-tooltip">
          {module.title}
        </span>
      )}
    </motion.button>
  );
}
