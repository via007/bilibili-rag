/**
 * 会话管理 API
 */

import { API_BASE_URL } from "./api";

// ==================== 通用请求函数 ====================

async function request<T>(
    endpoint: string,
    options: RequestInit = {}
): Promise<T> {
    const url = `${API_BASE_URL}${endpoint}`;

    const response = await fetch(url, {
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...options.headers,
        },
    });

    if (!response.ok) {
        const error = await response.text();
        throw new Error(error || `请求失败: ${response.status}`);
    }

    return response.json();
}

// ==================== 类型定义 ====================

export interface ChatSession {
    chat_session_id: string;
    title: string | null;
    folder_ids: number[] | null;
    message_count: number;
    last_message_at: string | null;
    created_at: string;
    is_archived: boolean;
}

export interface ChatMessage {
    id: number;
    role: "user" | "assistant";
    content: string;
    sources: Array<{
        bvid: string;
        title: string;
        url: string;
    }> | null;
    route: string | null;
    created_at: string;
}

export interface SessionListResponse {
    sessions: ChatSession[];
    total: number;
    page: number;
    page_size: number;
}

export interface MessageListResponse {
    messages: ChatMessage[];
    total: number;
    page: number;
    page_size: number;
}

export interface SessionCreateResponse {
    chat_session_id: string;
    title: string;
    created_at: string;
}

export interface SearchResult {
    chat_session_id: string;
    session_title: string | null;
    message_id: number;
    content: string;
    highlight: string | null;
    created_at: string;
}

export interface SearchResponse {
    results: SearchResult[];
    total: number;
    page: number;
    page_size: number;
}

// ==================== API 函数 ====================

export const conversationApi = {
    // 获取会话列表
    list: (
        userSessionId: string,
        page = 1,
        pageSize = 20,
        includeArchived = false
    ): Promise<SessionListResponse> =>
        request(
            `/conversation/list?user_session_id=${userSessionId}&page=${page}&page_size=${pageSize}&include_archived=${includeArchived}`
        ),

    // 创建新会话
    create: (
        userSessionId: string,
        title?: string,
        folderIds?: number[]
    ): Promise<SessionCreateResponse> =>
        request("/conversation/create", {
            method: "POST",
            body: JSON.stringify({
                user_session_id: userSessionId,
                title,
                folder_ids: folderIds,
            }),
        }),

    // 获取会话详情
    get: (chatSessionId: string, userSessionId: string): Promise<ChatSession> =>
        request(
            `/conversation/${chatSessionId}?user_session_id=${userSessionId}`
        ),

    // 更新会话
    update: (
        chatSessionId: string,
        userSessionId: string,
        data: { title?: string; is_archived?: boolean }
    ): Promise<ChatSession> =>
        request(`/conversation/${chatSessionId}?user_session_id=${userSessionId}`, {
            method: "PUT",
            body: JSON.stringify(data),
        }),

    // 删除会话
    delete: (chatSessionId: string, userSessionId: string): Promise<{ success: boolean; message: string }> =>
        request(`/conversation/${chatSessionId}?user_session_id=${userSessionId}`, {
            method: "DELETE",
        }),

    // 获取会话消息
    getMessages: (
        chatSessionId: string,
        userSessionId: string,
        page = 1,
        pageSize = 50
    ): Promise<MessageListResponse> =>
        request(
            `/conversation/${chatSessionId}/messages?user_session_id=${userSessionId}&page=${page}&page_size=${pageSize}`
        ),

    // 搜索对话
    search: (
        userSessionId: string,
        query: string,
        page = 1,
        pageSize = 20
    ): Promise<SearchResponse> =>
        request(
            `/conversation/search?user_session_id=${userSessionId}&query=${encodeURIComponent(query)}&page=${page}&page_size=${pageSize}`
        ),
};
