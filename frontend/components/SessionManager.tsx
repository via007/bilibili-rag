/**
 * 会话管理器组件
 */

"use client";

import { createContext, useContext, useState, ReactNode, useCallback, useEffect } from "react";
import { conversationApi, ChatSession, ChatMessage } from "@/lib/conversation";

interface SessionContextType {
    currentSessionId: string | null;
    sessions: ChatSession[];
    messages: ChatMessage[];
    loading: boolean;
    messagesLoading: boolean;
    createSession: (title?: string, folderIds?: number[]) => Promise<string>;
    selectSession: (sessionId: string | null) => void;
    deleteSession: (sessionId: string) => Promise<void>;
    updateSession: (sessionId: string, title: string) => Promise<void>;
    loadMessages: (sessionId: string) => Promise<void>;
    refreshSessions: () => Promise<void>;
}

const SessionContext = createContext<SessionContextType | null>(null);

interface Props {
    children: ReactNode;
    userSessionId: string;
}

export function SessionManager({ children, userSessionId }: Props) {
    const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
    const [sessions, setSessions] = useState<ChatSession[]>([]);
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [loading, setLoading] = useState(false);
    const [messagesLoading, setMessagesLoading] = useState(false);

    // 加载会话列表
    const refreshSessions = useCallback(async () => {
        try {
            setLoading(true);
            const data = await conversationApi.list(userSessionId);
            setSessions(data.sessions);
        } catch (error) {
            console.error("加载会话列表失败:", error);
        } finally {
            setLoading(false);
        }
    }, [userSessionId]);

    // 加载会话消息
    const loadMessages = useCallback(async (sessionId: string) => {
        try {
            setMessagesLoading(true);
            const data = await conversationApi.getMessages(sessionId, userSessionId);
            setMessages(data.messages);
        } catch (error) {
            console.error("加载会话消息失败:", error);
        } finally {
            setMessagesLoading(false);
        }
    }, [userSessionId]);

    // 创建会话
    const createSession = useCallback(async (title?: string, folderIds?: number[]): Promise<string> => {
        try {
            const data = await conversationApi.create(userSessionId, title, folderIds);
            await refreshSessions();
            setCurrentSessionId(data.chat_session_id);
            setMessages([]);
            return data.chat_session_id;
        } catch (error) {
            console.error("创建会话失败:", error);
            throw error;
        }
    }, [userSessionId, refreshSessions]);

    // 选择会话
    const selectSession = useCallback(async (sessionId: string | null) => {
        setCurrentSessionId(sessionId);
        if (sessionId) {
            await loadMessages(sessionId);
        } else {
            setMessages([]);
        }
    }, [loadMessages]);

    // 删除会话
    const deleteSession = useCallback(async (sessionId: string) => {
        try {
            await conversationApi.delete(sessionId, userSessionId);
            if (currentSessionId === sessionId) {
                setCurrentSessionId(null);
                setMessages([]);
            }
            await refreshSessions();
        } catch (error) {
            console.error("删除会话失败:", error);
            throw error;
        }
    }, [currentSessionId, userSessionId, refreshSessions]);

    // 更新会话
    const updateSession = useCallback(async (sessionId: string, title: string) => {
        try {
            await conversationApi.update(sessionId, userSessionId, { title });
            await refreshSessions();
        } catch (error) {
            console.error("更新会话失败:", error);
            throw error;
        }
    }, [userSessionId, refreshSessions]);

    // 初始加载
    useEffect(() => {
        if (userSessionId) {
            refreshSessions();
        }
    }, [userSessionId, refreshSessions]);

    return (
        <SessionContext.Provider
            value={{
                currentSessionId,
                sessions,
                messages,
                loading,
                messagesLoading,
                createSession,
                selectSession,
                deleteSession,
                updateSession,
                loadMessages,
                refreshSessions,
            }}
        >
            {children}
        </SessionContext.Provider>
    );
}

export function useSession() {
    const context = useContext(SessionContext);
    if (!context) {
        throw new Error("useSession must be used within SessionManager");
    }
    return context;
}
