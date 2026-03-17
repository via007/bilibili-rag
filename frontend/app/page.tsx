"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import LoginModal from "@/components/LoginModal";
import DemoFlowModal from "@/components/DemoFlowModal";
import SourcesPanel from "@/components/SourcesPanel";
import ChatPanel from "@/components/ChatPanel";
import SessionList from "@/components/SessionList";
import { SessionManager, useSession } from "@/components/SessionManager";
import ModelSelector from "@/components/ModelSelector";
import { UserInfo, authApi } from "@/lib/api";

// WorkspaceContent 的 props 类型
interface WorkspaceContentProps {
  session: string;
  selectedFolderIds: number[];
  setSelectedFolderIds: React.Dispatch<React.SetStateAction<number[]>>;
  statsKey: number;
  setStatsKey: React.Dispatch<React.SetStateAction<number>>;
  isMobile: boolean;
  mobilePanel: 'sessions' | 'sources' | 'chat';
  setMobilePanel: React.Dispatch<React.SetStateAction<'sessions' | 'sources' | 'chat'>>;
  currentSessionId: string | null;
  selectSession: (id: string | null) => void;
  createSession: (title?: string, folderIds?: number[]) => Promise<string>;
  sessions?: import("@/lib/conversation").ChatSession[];
  sessionsLoading?: boolean;
  onRefreshSessions?: () => void;
}

// 顶层组件：从 Home 提取出来，避免每次 Home 渲染都重新创建
function WorkspaceContent({
  session,
  selectedFolderIds,
  setSelectedFolderIds,
  statsKey,
  setStatsKey,
  isMobile,
  mobilePanel,
  setMobilePanel,
  currentSessionId,
  selectSession,
  createSession,
  sessions,
  sessionsLoading,
  onRefreshSessions,
}: WorkspaceContentProps) {
  // 拖拽调整宽度
  const [leftWidth, setLeftWidth] = useState(320);
  const [sessionSidebarExpanded, setSessionSidebarExpanded] = useState(true);
  const sessionListWidth = sessionSidebarExpanded ? 260 : 64;
  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef<HTMLElement>(null);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isDragging || !containerRef.current) return;
    const containerRect = containerRef.current.getBoundingClientRect();
    const newWidth = e.clientX - containerRect.left;
    // 限制最小 200px，最大 50% 容器宽度
    const min = 200;
    const max = containerRect.width * 0.5;
    setLeftWidth(Math.max(min, Math.min(max, newWidth)));
  }, [isDragging]);

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  useEffect(() => {
    if (isDragging) {
      window.addEventListener("mousemove", handleMouseMove);
      window.addEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    } else {
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    }
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isDragging, handleMouseMove, handleMouseUp]);

  const handleCreateSession = useCallback(async () => {
    try {
      const newSessionId = await createSession(undefined, selectedFolderIds.length > 0 ? selectedFolderIds : undefined);
      selectSession(newSessionId);
    } catch (error) {
      console.error("创建会话失败:", error);
      alert("创建会话失败: " + (error instanceof Error ? error.message : String(error)));
    }
  }, [selectedFolderIds, createSession, selectSession]);

  const handleSelectSession = useCallback((sessionId: string | null) => {
    if (sessionId) {
      selectSession(sessionId);
    } else {
      selectSession(null);
    }
  }, [selectSession]);

  // 构建完成回调，刷新统计
  const handleBuildDone = useCallback(() => {
    setStatsKey((v) => v + 1);
  }, [setStatsKey]);

  // 移动端面板渲染
  const renderMobilePanel = () => {
    switch (mobilePanel) {
      case 'sessions':
        return (
          <div className="panel panel-sources h-full">
            <SessionList
              userSessionId={session}
              currentSessionId={currentSessionId || undefined}
              onSelectSession={handleSelectSession}
              onCreateSession={handleCreateSession}
              externalSessions={sessions}
              externalLoading={sessionsLoading}
              onSessionChange={onRefreshSessions}
            />
          </div>
        );
      case 'sources':
        return (
          <div className="panel panel-sources h-full">
            <SourcesPanel
              sessionId={session}
              onBuildDone={handleBuildDone}
              onSelectionChange={setSelectedFolderIds}
            />
          </div>
        );
      case 'chat':
        return (
          <div className="panel panel-chat h-full">
            <ChatPanel
              statsKey={statsKey}
              sessionId={session}
              folderIds={selectedFolderIds}
              chatSessionId={currentSessionId || undefined}
            />
          </div>
        );
    }
  };

  // Apple 风格移动端底部导航栏
  const MobileNav = () => (
    <div className="fixed bottom-0 left-0 right-0 flex justify-around py-2 px-4 z-50 lg:hidden"
         style={{ background: 'var(--glass-bg-solid)', borderTop: '0.5px solid var(--border-subtle)', backdropFilter: 'blur(20px)' }}>
      <button
        onClick={() => setMobilePanel('sessions')}
        className={`flex flex-col items-center gap-1 px-4 py-2 rounded-lg transition-all ${mobilePanel === 'sessions' ? 'text-[var(--accent)]' : 'text-[var(--text-tertiary)]'}`}
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
        <span className="text-xs">会话</span>
      </button>
      <button
        onClick={() => setMobilePanel('sources')}
        className={`flex flex-col items-center gap-1 px-4 py-2 rounded-lg transition-all ${mobilePanel === 'sources' ? 'text-[var(--accent)]' : 'text-[var(--text-tertiary)]'}`}
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
        </svg>
        <span className="text-xs">收藏夹</span>
      </button>
      <button
        onClick={() => setMobilePanel('chat')}
        className={`flex flex-col items-center gap-1 px-4 py-2 rounded-lg transition-all ${mobilePanel === 'chat' ? 'text-[var(--accent)]' : 'text-[var(--text-tertiary)]'}`}
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
        </svg>
        <span className="text-xs">对话</span>
      </button>
    </div>
  );

  // 桌面端布局
  if (!isMobile) {
    return (
      <section className="workspace" ref={containerRef}>
        {/* 左侧：会话列表 */}
        <aside
          className="panel panel-sources relative"
          style={{ width: sessionListWidth, flexShrink: 0, transition: 'width 0.3s ease' }}
        >
          {/* 展开/收起按钮 - macOS 侧边栏风格 */}
          <button
            onClick={() => setSessionSidebarExpanded(!sessionSidebarExpanded)}
            className="absolute top-1/2 -translate-y-1/2 right-0 z-10 flex items-center justify-center w-5 h-12 transition-all duration-200 hover:bg-[var(--bg-hover)] rounded-l-md group"
            style={{ background: 'var(--bg-secondary)' }}
            title={sessionSidebarExpanded ? '收起侧边栏' : '展开侧边栏'}
          >
            <svg
              className={`w-2.5 h-2.5 transition-all duration-300 ${sessionSidebarExpanded ? 'opacity-60 group-hover:opacity-100 group-hover:-translate-x-0.5' : 'rotate-180 opacity-40 group-hover:opacity-80 group-hover:translate-x-0.5'}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <SessionList
            userSessionId={session}
            currentSessionId={currentSessionId || undefined}
            onSelectSession={handleSelectSession}
            onCreateSession={handleCreateSession}
            isExpanded={sessionSidebarExpanded}
            externalSessions={sessions}
            externalLoading={sessionsLoading}
            onSessionChange={onRefreshSessions}
          />
        </aside>

        {/* 拖拽分隔条 */}
        <div
          className="resizer"
          onMouseDown={handleMouseDown}
          style={{ cursor: "col-resize" }}
        />

        <aside className="panel panel-sources" style={{ width: leftWidth, flexShrink: 0 }}>
          <SourcesPanel
            sessionId={session}
            onBuildDone={handleBuildDone}
            onSelectionChange={setSelectedFolderIds}
          />
        </aside>

        {/* 拖拽分隔条 */}
        <div
          className="resizer"
          onMouseDown={handleMouseDown}
          style={{ cursor: "col-resize" }}
        />

        <section className="panel panel-chat" style={{ flex: 1 }}>
          <ChatPanel
            statsKey={statsKey}
            sessionId={session}
            folderIds={selectedFolderIds}
            chatSessionId={currentSessionId || undefined}
          />
        </section>
      </section>
    );
  }

  // 移动端布局
  return (
    <div className="flex flex-col h-full pb-16">
      <div className="flex-1 overflow-hidden">
        {renderMobilePanel()}
      </div>
      <MobileNav />
    </div>
  );
}

// 会话管理包装器：从 SessionManager 获取 session 上下文
function WorkspaceWithSession({
  session,
  selectedFolderIds,
  setSelectedFolderIds,
  statsKey,
  setStatsKey,
  isMobile,
  mobilePanel,
  setMobilePanel,
}: {
  session: string;
  selectedFolderIds: number[];
  setSelectedFolderIds: React.Dispatch<React.SetStateAction<number[]>>;
  statsKey: number;
  setStatsKey: React.Dispatch<React.SetStateAction<number>>;
  isMobile: boolean;
  mobilePanel: 'sessions' | 'sources' | 'chat';
  setMobilePanel: React.Dispatch<React.SetStateAction<'sessions' | 'sources' | 'chat'>>;
}) {
  const { currentSessionId, selectSession, createSession, sessions, loading, refreshSessions } = useSession();

  return (
    <WorkspaceContent
      session={session}
      selectedFolderIds={selectedFolderIds}
      setSelectedFolderIds={setSelectedFolderIds}
      statsKey={statsKey}
      setStatsKey={setStatsKey}
      isMobile={isMobile}
      mobilePanel={mobilePanel}
      setMobilePanel={setMobilePanel}
      currentSessionId={currentSessionId}
      selectSession={selectSession}
      createSession={createSession}
      sessions={sessions}
      sessionsLoading={loading}
      onRefreshSessions={refreshSessions}
    />
  );
}

export default function Home() {
  const [session, setSession] = useState<string | null>(null);
  const [user, setUser] = useState<string | null>(null);
  const [showLogin, setShowLogin] = useState(false);
  const [showDemo, setShowDemo] = useState(false);
  const [showModelSelector, setShowModelSelector] = useState(false);
  const [statsKey, setStatsKey] = useState(0);
  const [selectedFolderIds, setSelectedFolderIds] = useState<number[]>([]);
  // 移动端当前显示的面板: 'sessions' | 'sources' | 'chat'
  const [mobilePanel, setMobilePanel] = useState<'sessions' | 'sources' | 'chat'>('sources');
  const [isMobile, setIsMobile] = useState(false);

  // 检测移动端
  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 1024);
    };
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  useEffect(() => {
    const s = localStorage.getItem("bili_session");
    const u = localStorage.getItem("bili_user");
    if (s && u) {
      setSession(s);
      setUser(u);
    }
  }, []);

  const onLogin = (sid: string, info: UserInfo) => {
    setSession(sid);
    setUser(info.uname);
    setShowLogin(false);
    localStorage.setItem("bili_session", sid);
    localStorage.setItem("bili_user", info.uname);
  };

  const onLogout = () => {
    if (session) authApi.logout(session).catch(() => { });
    setSession(null);
    setUser(null);
    localStorage.removeItem("bili_session");
    localStorage.removeItem("bili_user");
  };

  return (
    <div className="app-shell">
      <header className="app-topbar">
        <div className="brand">
          <div className="brand-mark">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
              <path d="M4 6h16M4 12h16M4 18h10" />
            </svg>
          </div>
          <div>
            <span className="brand-title">BiliMind·收藏夹知识库</span>
            <span className="brand-subtitle">Save • Learn • Ask</span>
          </div>
        </div>

        <div className="topbar-actions">
          <button
            onClick={() => setShowModelSelector(true)}
            className="btn-icon"
            title="模型设置"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 15a3 3 0 100-6 3 3 0 000 6z" />
              <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z" />
            </svg>
          </button>
          {user ? (
            <>
              <span className="user-chip">
                <span>已登录</span>
                <strong>{user}</strong>
              </span>
              <button onClick={onLogout} className="btn-icon" title="退出">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                </svg>
              </button>
            </>
          ) : (
            <button onClick={() => setShowLogin(true)} className="btn btn-primary">
              扫码登录
            </button>
          )}
        </div>
      </header>

      <main className="app-main">
        {!session ? (
          <section className="hero">
            <div className="hero-content">
              <span className="hero-kicker">让你的B站收藏夹不再吃灰</span>
              <h1 className="hero-title">把"收藏"变成真正可用的知识</h1>
              <p className="hero-desc">
                很多人收藏了大量学习视频，却迟迟没看、没整理、也找不到重点。<br />
                这里把碎片化内容接入 AI：自动提炼、语义检索、对话式回顾，让收藏真正提升效率。
              </p>

              <div className="hero-actions">
                <button className="btn btn-primary btn-lg" onClick={() => setShowLogin(true)}>
                  扫码登录开始构建
                </button>
                <button className="btn btn-outline" onClick={() => setShowDemo(true)}>
                  体验检索流程
                </button>
              </div>
            </div>

            <div className="hero-features">
              <div className="pipeline-row">
                {[
                  { icon: "1", title: "同步", desc: "接入收藏夹" },
                  { icon: "2", title: "提炼", desc: "整理要点" },
                  { icon: "3", title: "检索", desc: "语义查找" },
                  { icon: "4", title: "回顾", desc: "对话复习" },
                ].map((item, i) => (
                  <div key={i} className="pipeline-card">
                    <span className="pipeline-icon">{item.icon}</span>
                    <div className="pipeline-text">
                      <strong>{item.title}</strong>
                      <span>{item.desc}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>
        ) : (
          <SessionManager userSessionId={session}>
            <WorkspaceWithSession
              session={session}
              selectedFolderIds={selectedFolderIds}
              setSelectedFolderIds={setSelectedFolderIds}
              statsKey={statsKey}
              setStatsKey={setStatsKey}
              isMobile={isMobile}
              mobilePanel={mobilePanel}
              setMobilePanel={setMobilePanel}
            />
          </SessionManager>
        )}
      </main>

      <footer className="app-footer">
        <p>BiliMind © 2026 · 基于 Bilibili API 构建 · 由 AI 驱动</p>
      </footer>

      <LoginModal isOpen={showLogin} onClose={() => setShowLogin(false)} onSuccess={onLogin} />
      <DemoFlowModal isOpen={showDemo} onClose={() => setShowDemo(false)} />
      <ModelSelector isOpen={showModelSelector} onClose={() => setShowModelSelector(false)} />
    </div>
  );
}
