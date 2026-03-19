/**
 * 导出 API
 */

import { API_BASE_URL } from "./api";

export interface ExportResponse {
    success: boolean;
    filename: string;
    content: string;
    size: number;
}

// 会话总结响应
export interface SessionSummaryResponse {
    success: boolean;
    has_cache?: boolean;
    regenerated?: boolean;
    data: {
        content: string;
        version: number;
        source_video_count: number;
        message_count: number;
        created_at: string;
        updated_at: string;
    };
}

// 通用请求函数
async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
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

// 导出视频
export async function exportVideo(bvid: string, format: "full" | "simple" = "full"): Promise<ExportResponse> {
    return request<ExportResponse>("/export/video", {
        method: "POST",
        body: JSON.stringify({ bvid, format }),
    });
}

// 导出收藏夹（支持单或多选）
export async function exportFolder(folderIds: number | number[], format: "full" | "simple" = "full"): Promise<ExportResponse> {
    const ids = Array.isArray(folderIds) ? folderIds : [folderIds];
    return request<ExportResponse>("/export/folder", {
        method: "POST",
        body: JSON.stringify({ folder_ids: ids, format }),
    });
}

// 导出会话
export async function exportSession(chatSessionId: string): Promise<ExportResponse> {
    return request<ExportResponse>("/export/session", {
        method: "POST",
        body: JSON.stringify({ chat_session_id: chatSessionId }),
    });
}

// 获取会话总结（优先缓存）
export async function getSessionSummary(chatSessionId: string): Promise<SessionSummaryResponse> {
    return request<SessionSummaryResponse>(`/export/session-summary/${chatSessionId}`, {
        method: "GET",
    });
}

// 刷新会话总结（重新生成）
export async function refreshSessionSummary(chatSessionId: string, format: "full" | "simple" = "full"): Promise<SessionSummaryResponse> {
    return request<SessionSummaryResponse>(`/export/session-summary/${chatSessionId}/refresh`, {
        method: "POST",
        body: JSON.stringify({ chat_session_id: chatSessionId, format }),
    });
}

// 删除会话总结缓存
export async function deleteSessionSummary(chatSessionId: string): Promise<{ success: boolean }> {
    return request<{ success: boolean }>(`/export/session-summary/${chatSessionId}`, {
        method: "DELETE",
    });
}

// 下载 Markdown 文件
export function downloadMarkdown(content: string, filename: string): void {
    const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}

// 复制到剪贴板
export async function copyToClipboard(text: string): Promise<boolean> {
    try {
        await navigator.clipboard.writeText(text);
        return true;
    } catch {
        return false;
    }
}
