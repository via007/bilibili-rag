/**
 * API 客户端
 */

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// 通用请求函数
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

    // 会话失效时自动清除登录状态并刷新页面
    if (response.status === 401) {
        if (typeof window !== "undefined") {
            localStorage.removeItem("bili_session");
            localStorage.removeItem("bili_user");
            window.location.href = "/";
        }
        throw new Error("会话已过期，请重新登录");
    }

    if (!response.ok) {
        const error = await response.text();
        throw new Error(error || `请求失败: ${response.status}`);
    }

    return response.json();
}

// ==================== 类型定义 ====================

export interface QRCodeResponse {
    qrcode_key: string;
    qrcode_url: string;
    qrcode_image_base64: string;
}

export interface LoginStatusResponse {
    status: "waiting" | "scanned" | "confirmed" | "expired";
    message: string;
    user_info?: UserInfo;
    session_id?: string;
}

export interface UserInfo {
    mid: number;
    uname: string;
    face: string;
    level?: number;
}

export interface FavoriteFolder {
    media_id: number;
    title: string;
    media_count: number;
    is_selected: boolean;
    is_default?: boolean;
}

export interface Video {
    bvid: string;
    title: string;
    cover?: string;
    duration?: number;
    owner?: string;
    play_count?: number;
    intro?: string;
    is_selected: boolean;
    original_bvid?: string;
    is_part?: boolean;
    part_id?: number;
    cid?: number;
}

export interface FavoriteVideosResponse {
    folder_info: Record<string, unknown>;
    videos: Video[];
    has_more: boolean;
    page: number;
    page_size: number;
    total: number;
}

export interface OrganizePreviewItem {
    bvid: string;
    title: string;
    resource_id: number;
    resource_type: number;
    target_folder_id: number | null;
    target_folder_title: string;
    reason?: string;
}

export interface OrganizePreviewResponse {
    default_folder_id: number;
    default_folder_title: string;
    folders: FavoriteFolder[];
    items: OrganizePreviewItem[];
    stats: {
        total: number;
        matched: number;
        unmatched: number;
    };
}

export interface BuildRequest {
    folder_ids: number[];
    exclude_bvids?: string[];
    include_bvids?: string[];
}

export interface BuildStatus {
    task_id: string;
    status: "pending" | "running" | "completed" | "failed";
    progress: number;
    current_step: string;
    total_videos: number;
    processed_videos: number;
    message: string;
}

export interface FolderStatus {
    media_id: number;
    indexed_count: number;
    media_count?: number;
    last_sync_at?: string;
    // 详细统计（新增）
    stats?: {
        pending: number;
        processing: number;
        completed: number;
        failed: number;
        no_content: number;
    };
    progress?: number;  // 0-100
}

// 视频详细状态
export interface VideoDetailStatus {
    bvid: string;
    title: string;
    cover?: string;
    owner?: string;
    duration?: number;
    processing_status: 'pending' | 'processing' | 'completed' | 'failed';
    processing_step?: string;
    processing_error?: string;
    content_preview?: string;
    asr_quality_score?: number;
    created_at?: string;
}

// 收藏夹详细状态（含视频列表）
export interface FolderDetailStatus {
    media_id: number;
    stats: {
        pending: number;
        processing: number;
        completed: number;
        failed: number;
        no_content: number;
    };
    videos: VideoDetailStatus[];
    progress: number;
    total: number;
    page: number;
    page_size: number;
    has_more: boolean;
}

// 批量重试请求
export interface RetryFailedRequest {
    folder_ids?: number[];
    bvids?: string[];
}

// 批量重试响应
export interface RetryFailedResponse {
    task_id: string;
    total: number;
    message: string;
}

export interface SyncRequest {
    folder_ids?: number[];
}

export interface SyncResult {
    folder_id: number;
    total: number;
    added: number;
    removed: number;
    indexed: number;
    message: string;
    last_sync_at: string;
}

export interface KnowledgeStats {
    total_chunks: number;
    total_videos: number;
    collection_name: string;
}

export interface ChatResponse {
    answer: string;
    sources: Array<{
        bvid: string;
        title: string;
        url: string;
    }>;
}

export interface ASRStatus {
    bvid: string;
    asr_status: "pending" | "processing" | "completed" | "failed";
    asr_model?: string;
    asr_duration?: number;
    asr_quality_score?: number;
    asr_quality_flags?: string[];
    content?: string;
    is_corrected?: boolean;
}

// ==================== API 函数 ====================

// 认证相关
export const authApi = {
    // 获取登录二维码
    getQRCode: () => request<QRCodeResponse>("/auth/qrcode"),

    // 轮询登录状态
    pollQRCode: (qrcodeKey: string) =>
        request<LoginStatusResponse>(`/auth/qrcode/poll/${qrcodeKey}`),

    // 获取会话信息
    getSession: (sessionId: string) =>
        request<{ valid: boolean; user_info: UserInfo }>(`/auth/session/${sessionId}`),

    // 退出登录
    logout: (sessionId: string) =>
        request(`/auth/session/${sessionId}`, { method: "DELETE" }),
};

// 收藏夹相关
export const favoritesApi = {
    // 获取收藏夹列表
    getList: (sessionId: string) =>
        request<FavoriteFolder[]>(`/favorites/list?session_id=${sessionId}`),

    // 获取收藏夹视频（分页）
    getVideos: (mediaId: number, sessionId: string, page = 1) =>
        request<FavoriteVideosResponse>(
            `/favorites/${mediaId}/videos?session_id=${sessionId}&page=${page}`
        ),

    // 获取收藏夹全部视频
    getAllVideos: (mediaId: number, sessionId: string) =>
        request<{ total: number; videos: Video[] }>(
            `/favorites/${mediaId}/all-videos?session_id=${sessionId}`
        ),

    // 预览整理
    organizePreview: (folderId: number, sessionId: string) =>
        request<OrganizePreviewResponse>(
            `/favorites/organize/preview?session_id=${sessionId}`,
            {
                method: "POST",
                body: JSON.stringify({ folder_id: folderId }),
            }
        ),

    // 执行整理
    organizeExecute: (
        data: {
            default_folder_id: number;
            moves: Array<{ resource_id: number; resource_type: number; target_folder_id: number }>;
        },
        sessionId: string
    ) =>
        request<{ message: string; moved: number; groups: number }>(
            `/favorites/organize/execute?session_id=${sessionId}`,
            {
                method: "POST",
                body: JSON.stringify(data),
            }
        ),

    // 清理失效内容
    cleanInvalid: (folderId: number, sessionId: string) =>
        request<{ message: string; data: Record<string, unknown> }>(
            `/favorites/organize/clean-invalid?session_id=${sessionId}`,
            {
                method: "POST",
                body: JSON.stringify({ folder_id: folderId }),
            }
        ),
};

// 知识库相关
export const knowledgeApi = {
    // 获取统计信息
    getStats: () => request<KnowledgeStats>("/knowledge/stats"),

    // 构建知识库
    build: (data: BuildRequest, sessionId: string) =>
        request<{ task_id: string; message: string }>(
            `/knowledge/build?session_id=${sessionId}`,
            {
                method: "POST",
                body: JSON.stringify(data),
            }
        ),

    // 获取构建状态
    getBuildStatus: (taskId: string) =>
        request<BuildStatus>(`/knowledge/build/status/${taskId}`),

    // 获取收藏夹入库状态
    getFolderStatus: (sessionId: string) =>
        request<FolderStatus[]>(`/knowledge/folders/status?session_id=${sessionId}`),

    // 同步收藏夹到向量库
    syncFolders: (data: SyncRequest, sessionId: string) =>
        request<SyncResult[]>(
            `/knowledge/folders/sync?session_id=${sessionId}`,
            {
                method: "POST",
                body: JSON.stringify(data),
            }
        ),

    // 清空知识库
    clear: () =>
        request<{ message: string }>("/knowledge/clear", { method: "DELETE" }),

    // 删除视频
    deleteVideo: (bvid: string) =>
        request<{ message: string }>(`/knowledge/video/${bvid}`, { method: "DELETE" }),

    // 获取 ASR 状态
    getASRStatus: (bvid: string) =>
        request<ASRStatus>(`/knowledge/video/${bvid}/asr-status`),

    // ASR 纠错
    correctASR: (bvid: string, correctedContent: string) =>
        request<ASRStatus>(`/knowledge/video/${bvid}/asr-correct`, {
            method: "POST",
            body: JSON.stringify({ corrected_content: correctedContent }),
        }),

    // 获取收藏夹详细状态（含视频列表）
    getFolderDetailStatus: (
        mediaId: number,
        sessionId: string,
        options?: { status_filter?: string; page?: number; page_size?: number }
    ) => {
        const params = new URLSearchParams({ session_id: sessionId });
        if (options?.status_filter) params.append("status_filter", options.status_filter);
        if (options?.page) params.append("page", String(options.page));
        if (options?.page_size) params.append("page_size", String(options.page_size));
        return request<FolderDetailStatus>(
            `/knowledge/folders/${mediaId}/status?${params.toString()}`
        );
    },

    // 获取视频详情
    getVideoDetail: (bvid: string) =>
        request<VideoDetailStatus>(`/knowledge/video/${bvid}/detail`),

    // 批量重试失败视频
    retryFailedVideos: (data: RetryFailedRequest, sessionId: string) =>
        request<RetryFailedResponse>(
            `/knowledge/retry-failed?session_id=${sessionId}`,
            {
                method: "POST",
                body: JSON.stringify(data),
            }
        ),
};

// 对话相关
export const chatApi = {
    // 提问
    ask: (question: string, sessionId?: string, folderIds?: number[]) =>
        request<ChatResponse>("/chat/ask", {
            method: "POST",
            body: JSON.stringify({ question, session_id: sessionId, folder_ids: folderIds }),
        }),

    // 搜索
    search: (query: string, k = 5) =>
        request<{ results: Array<{ bvid: string; title: string; url: string; content_preview: string }> }>(
            `/chat/search?query=${encodeURIComponent(query)}&k=${k}`,
            { method: "POST" }
        ),
};

// LLM 配置类型
export interface LLMConfig {
    provider: string;
    llm_model: string;
    embedding_model: string;
}

export interface LLMConfigUpdate {
    provider: string;
    llm_model: string;
    embedding_model: string;
    api_key?: string;
}

// ==================== 会话管理类型 ====================

export interface ChatSessionInfo {
    chat_session_id: string;
    title: string | null;
    folder_ids: number[] | null;
    message_count: number;
    last_message_at: string | null;
    created_at: string;
    is_archived: boolean;
}

export interface ChatSessionListResponse {
    sessions: ChatSessionInfo[];
    total: number;
    page: number;
    page_size: number;
}

export interface ChatSessionCreateResponse {
    chat_session_id: string;
    title: string;
    created_at: string;
}

export interface ChatMessageInfo {
    id: number;
    role: string;
    content: string;
    sources: Array<{
        bvid: string;
        title: string;
        url: string;
    }> | null;
    route: string | null;
    created_at: string;
}

export interface ChatMessageListResponse {
    messages: ChatMessageInfo[];
    total: number;
    page: number;
    page_size: number;
}

export interface ConversationSearchResult {
    chat_session_id: string;
    session_title: string;
    message_id: number;
    content: string;
    highlight: string;
    created_at: string;
}

export interface ConversationSearchResponse {
    results: ConversationSearchResult[];
    total: number;
    page: number;
    page_size: number;
}

// 会话管理相关
export const conversationApi = {
    // 获取会话列表
    list: (
        userSessionId: string,
        page = 1,
        pageSize = 20,
        includeArchived = false
    ) =>
        request<ChatSessionListResponse>(
            `/conversation/list?user_session_id=${userSessionId}&page=${page}&page_size=${pageSize}&include_archived=${includeArchived}`
        ),

    // 创建会话
    create: (
        userSessionId: string,
        title?: string,
        folderIds?: number[]
    ) =>
        request<ChatSessionCreateResponse>("/conversation/create", {
            method: "POST",
            body: JSON.stringify({
                user_session_id: userSessionId,
                title,
                folder_ids: folderIds,
            }),
        }),

    // 获取会话详情
    get: (chatSessionId: string, userSessionId: string) =>
        request<ChatSessionInfo>(
            `/conversation/${chatSessionId}?user_session_id=${userSessionId}`
        ),

    // 更新会话
    update: (
        chatSessionId: string,
        userSessionId: string,
        data: { title?: string; is_archived?: boolean }
    ) =>
        request<ChatSessionInfo>(`/conversation/${chatSessionId}`, {
            method: "PUT",
            body: JSON.stringify(data),
        }),

    // 删除会话
    delete: (chatSessionId: string, userSessionId: string) =>
        request<{ success: boolean; message: string }>(
            `/conversation/${chatSessionId}?user_session_id=${userSessionId}`,
            { method: "DELETE" }
        ),

    // 获取会话消息
    getMessages: (
        chatSessionId: string,
        userSessionId: string,
        page = 1,
        pageSize = 50
    ) =>
        request<ChatMessageListResponse>(
            `/conversation/${chatSessionId}/messages?user_session_id=${userSessionId}&page=${page}&page_size=${pageSize}`
        ),

    // 搜索对话
    search: (
        userSessionId: string,
        query: string,
        page = 1,
        pageSize = 20
    ) =>
        request<ConversationSearchResponse>(
            `/conversation/search?user_session_id=${userSessionId}&query=${encodeURIComponent(query)}&page=${page}&page_size=${pageSize}`
        ),
};

// 配置相关
export const configApi = {
    // 获取当前模型配置
    getLLMConfig: () => request<LLMConfig>("/config/llm"),

    // 更新模型配置
    updateLLMConfig: (data: LLMConfigUpdate) =>
        request<{ message: string }>("/config/llm", {
            method: "PUT",
            body: JSON.stringify(data),
        }),
};

// ==================== 视频摘要类型 ====================

export interface VideoSummaryResponse {
    bvid: string;
    title?: string;
    short_intro?: string;
    key_points?: string[];
    target_audience?: string;
    difficulty_level?: string;
    tags?: string[];
    is_generated: boolean;
    generated_at?: string;
}

export interface SummaryGenerateRequest {
    bvid: string;
}

export interface SummaryGenerateResponse {
    bvid: string;
    message: string;
    task_id?: string;
}

// 视频摘要相关
export const summaryApi = {
    // 获取视频摘要
    getSummary: (bvid: string) =>
        request<VideoSummaryResponse>(`/knowledge/summary/${bvid}`),

    // 生成视频摘要
    generateSummary: (bvid: string) =>
        request<SummaryGenerateResponse>("/knowledge/summary/generate", {
            method: "POST",
            body: JSON.stringify({ bvid }),
        }),
};

// ==================== 主题聚类类型 ====================

export interface ClusterVideoItem {
    bvid: string;
    title?: string;
    short_intro?: string;
    difficulty_level?: string;
}

export interface TopicClusterResponse {
    cluster_id: number;
    topic_name?: string;
    keywords?: string[];
    video_count: number;
    difficulty_distribution?: Record<string, number>;
    videos: ClusterVideoItem[];
}

export interface ClustersResponse {
    folder_id: number;
    clusters: TopicClusterResponse[];
    generated_at?: string;
}

export interface ClusterGenerateRequest {
    folder_id: number;
    n_clusters?: number;
}

export interface ClusterGenerateResponse {
    folder_id: number;
    message: string;
    task_id?: string;
}

// 主题聚类相关
export const clusteringApi = {
    // 获取聚类结果
    getClusters: (folderId: number) =>
        request<ClustersResponse>(`/knowledge/clusters/${folderId}`),

    // 生成聚类
    generateClusters: (folderId: number, nClusters?: number) =>
        request<ClusterGenerateResponse>("/knowledge/clusters/generate", {
            method: "POST",
            body: JSON.stringify({ folder_id: folderId, n_clusters: nClusters }),
        }),
};

// ==================== 学习路径类型 ====================

export interface PathVideoItem {
    bvid: string;
    title?: string;
    short_intro?: string;
    difficulty_level?: string;
    duration?: number;
}

export interface LearningStageResponse {
    stage_id: number;
    name: string;
    description: string;
    videos: PathVideoItem[];
    prerequisites: string[];
    estimated_time: number;
}

export interface LearningPathResponse {
    folder_id: number;
    user_level: string;
    total_videos: number;
    estimated_hours: number;
    intro: string;
    stages: LearningStageResponse[];
    generated_at?: string;
}

// 学习路径相关
export const learningPathApi = {
    // 获取学习路径
    getLearningPath: (folderId: number, userLevel: string = "beginner", sessionId: string) =>
        request<LearningPathResponse>(
            `/knowledge/path/${folderId}?user_level=${userLevel}&session_id=${sessionId}`
        ),

    // 触发学习路径生成
    triggerPathGeneration: (folderId: number, userLevel: string = "beginner", sessionId: string) =>
        request<{ message: string; folder_id: number; user_level: string }>(
            `/knowledge/path/generate?folder_id=${folderId}&user_level=${userLevel}&session_id=${sessionId}`,
            { method: "POST" }
        ),
};

// ==================== 内容修正类型 ====================

export interface Sentence {
    id: number;
    text: string;
    start: number;
    end: number;
    confidence: number;
    is_flagged: boolean;
}

export interface QualityReport {
    quality_score: number;
    quality_grade: string;
    flags: string[];
    confidence_avg: number;
    confidence_min: number;
    audio_quality: string;
    speech_ratio: number;
    suggestions: string[];
}

export interface CorrectionVideo {
    bvid: string;
    title?: string;
    asr_quality_score?: number;
    asr_quality_flags?: string[];
    content_preview?: string;
    is_corrected: boolean;
    created_at: string;
}

export interface CorrectionListResponse {
    videos: CorrectionVideo[];
    total: number;
    page: number;
    page_size: number;
}

export interface CorrectionDetail {
    bvid: string;
    title: string;
    content: string;
    sentences: Sentence[];
    quality_report?: QualityReport;
}

export interface CorrectionSubmitRequest {
    content: string;
}

export interface CorrectionSubmitResponse {
    success: boolean;
    message: string;
    is_corrected: boolean;
}

export interface CorrectionHistoryItem {
    id: number;
    original_content: string;
    corrected_content: string;
    char_diff: number;
    word_diff: number;
    correction_type: string;
    created_at: string;
}

export interface CorrectionHistoryResponse {
    history: CorrectionHistoryItem[];
    total: number;
    page: number;
    page_size: number;
}

// 内容修正相关
export const correctionApi = {
    // 获取修正列表
    listCorrections: (
        userSessionId: string,
        minQuality: number = 0.7,
        page: number = 1,
        pageSize: number = 20,
        includeCorrected: boolean = false
    ) =>
        request<CorrectionListResponse>(
            `/correction/list?user_session_id=${userSessionId}&min_quality=${minQuality}&page=${page}&page_size=${pageSize}&include_corrected=${includeCorrected}`
        ),

    // 获取修正详情
    getCorrection: (bvid: string, userSessionId: string) =>
        request<CorrectionDetail>(
            `/correction/${bvid}?user_session_id=${userSessionId}`
        ),

    // 提交修正
    submitCorrection: (
        bvid: string,
        userSessionId: string,
        content: string
    ) =>
        request<CorrectionSubmitResponse>(`/correction/${bvid}?user_session_id=${userSessionId}`, {
            method: "POST",
            body: JSON.stringify({ content }),
        }),

    // 获取修正历史
    getCorrectionHistory: (
        bvid: string,
        userSessionId: string,
        page: number = 1,
        pageSize: number = 20
    ) =>
        request<CorrectionHistoryResponse>(
            `/correction/${bvid}/history?user_session_id=${userSessionId}&page=${page}&page_size=${pageSize}`
        ),
};
