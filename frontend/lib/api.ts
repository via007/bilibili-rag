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
        const text = await response.text();
        let message = text || `请求失败: ${response.status}`;
        try {
            const parsed = JSON.parse(text);
            if (parsed.detail) {
                message = typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail);
            }
        } catch {}
        throw new Error(message);
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
    page_count?: number;
}

export interface VideoPageInfo {
    cid: number;
    page: number;       // 1-based
    title: string;     // B站 part 字段
    duration: number;
}

export interface VideoPagesResponse {
    bvid: string;
    title: string;
    pages: VideoPageInfo[];
    page_count: number;
}

export interface FavoriteVideosResponse {
    folder_info: Record<string, unknown>;
    videos: Video[];
    has_more: boolean;
    page: number;
    page_size: number;
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

export interface ReasoningStep {
    step: number;
    action: string;
    query: string;
    reasoning: string;
    verdict?: string | null;
    recall_score?: number | null;
    sources: Array<{
        bvid: string;
        title: string;
        url: string;
    }>;
    content_preview: string;
}

export interface AgenticChatResponse {
    answer: string;
    sources: Array<{
        bvid: string;
        title: string;
        url: string;
    }>;
    reasoning_steps: ReasoningStep[];
    synthesis_method: string;
    hops_used: number;
    avg_recall_score: number;
}

// 工作区页面（用户选中的已向量化分P）
export interface WorkspacePage {
    bvid: string;
    cid: number;
    page_index: number;
    page_title?: string;
}

// 聊天会话
export interface ChatSession {
    id: number;
    chat_session_id: string;
    session_id: string;
    title?: string;
    status: string;
    created_at: string;
    updated_at: string;
    last_message_at?: string;
}

// 聊天消息
export interface ChatMessage {
    id: number;
    chat_session_id: string;
    role: "user" | "assistant" | "system";
    content: string;
    status: "pending" | "completed" | "failed";
    sources?: Array<{ bvid: string; title: string; url?: string }>;
    tokens_used?: number;
    model?: string;
    latency_ms?: number;
    error?: string;
    created_at: string;
}

// 聊天历史响应
export interface ChatHistoryResponse {
    messages: ChatMessage[];
    total: number;
    page: number;
    page_size: number;
    has_more: boolean;
    next_cursor?: string | null;
}

// 会话列表响应
export interface ChatSessionListResponse {
    sessions: ChatSession[];
}

export interface ChatSessionUpdatePayload {
    title: string;
}

// 对话请求载荷（统一构造方式）
export interface ChatRequestPayload {
    question: string;
    session_id?: string;
    chat_session_id?: string;  // 新增：聊天会话 ID
    folder_ids?: number[];
    workspace_pages?: WorkspacePage[];
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

export interface VectorizedPageItem {
    bvid: string;
    cid: number;
    page_index: number;
    page_title?: string;
    video_title?: string;
    vector_chunk_count: number;
    vectorized_at?: string;
}
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

    // 获取视频分P列表
    getVideoPages: (bvid: string) =>
        request<VideoPagesResponse>(`/knowledge/video/${bvid}/pages`),

    // 获取已向量化的分P列表
    getVectorizedPages: (sessionId: string) =>
        request<VectorizedPageItem[]>(`/knowledge/pages/vectorized?session_id=${sessionId}`),
};

// 对话相关
export const chatApi = {
    // 提问（标准模式）
    ask: (payload: ChatRequestPayload) =>
        request<ChatResponse>("/chat/ask", {
            method: "POST",
            body: JSON.stringify(payload),
        }),

    // 提问（Agentic RAG 模式）
    askAgentic: (payload: ChatRequestPayload) =>
        request<AgenticChatResponse>("/chat/ask/agentic", {
            method: "POST",
            body: JSON.stringify(payload),
        }),

    // 搜索
    search: (query: string, k = 5) =>
        request<{ results: Array<{ bvid: string; title: string; url: string; content_preview: string }> }>(
            `/chat/search?query=${encodeURIComponent(query)}&k=${k}`,
            { method: "POST" }
        ),

    // === 新增：流式接口（替代裸调 fetch）===
    askStream: async (payload: ChatRequestPayload): Promise<ReadableStream<Uint8Array>> => {
        const res = await fetch(`${API_BASE_URL}/chat/ask/stream`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });

        // 会话失效时自动清除登录状态并刷新页面（与 request() 保持一致）
        if (res.status === 401) {
            if (typeof window !== "undefined") {
                localStorage.removeItem("bili_session");
                localStorage.removeItem("bili_user");
                window.location.href = "/";
            }
            throw new Error("会话已过期，请重新登录");
        }

        if (!res.ok || !res.body) {
            throw new Error("流式接口不可用");
        }
        return res.body;
    },

    // === 新增：会话管理 ===
    createSession: (sessionId: string, title?: string) =>
        request<ChatSession>("/chat/sessions", {
            method: "POST",
            body: JSON.stringify({ session_id: sessionId, title }),
        }),

    listSessions: (sessionId: string) =>
        request<ChatSessionListResponse>(`/chat/sessions?session_id=${sessionId}`),

    updateSession: (chatSessionId: string, payload: ChatSessionUpdatePayload) =>
        request<ChatSession>(`/chat/sessions/${chatSessionId}`, {
            method: "PATCH",
            body: JSON.stringify(payload),
        }),

    deleteSession: (chatSessionId: string) =>
        request(`/chat/sessions/${chatSessionId}`, { method: "DELETE" }),

    // === 新增：历史消息 ===
    getHistory: (chatSessionId: string, page = 1, pageSize = 50) =>
        request<ChatHistoryResponse>(
            `/chat/history?chat_session_id=${chatSessionId}&page=${page}&page_size=${pageSize}`
        ),

    clearHistory: (chatSessionId: string) =>
        request(`/chat/history?chat_session_id=${chatSessionId}`, { method: "DELETE" }),
};

// ==================== 分P向量化相关 ====================

export interface VectorPageStatusResponse {
  exists: boolean;
  bvid?: string;
  cid?: number;
  page_index?: number;
  page_title?: string;
  is_processed: boolean;
  content_preview?: string;
  is_vectorized: "pending" | "processing" | "done" | "failed";
  vectorized_at?: string;
  vector_chunk_count: number;
  vector_error?: string;
  chroma_exists: boolean;
}

export interface VectorPageTaskStatus {
  task_id: string;
  status: "pending" | "processing" | "done" | "failed";
  progress: number;
  message: string;
  result?: { chunk_count?: number };
  error?: string;
}

export const vecPageApi = {
  // 查询向量状态
  getStatus: (bvid: string, cid: number) =>
    request<VectorPageStatusResponse>(
      `/vec/page/status?bvid=${bvid}&cid=${cid}`
    ),

  // 发起向量化（幂等）
  create: (params: { bvid: string; cid: number; page_index: number; page_title?: string }) =>
    request<{ task_id: string | null; message: string }>(
      "/vec/page/create",
      {
        method: "POST",
        body: JSON.stringify(params),
      }
    ),

  // 强制重新向量化
  revector: (params: { bvid: string; cid: number }) =>
    request<{ task_id: string; message: string }>(
      "/vec/page/revector",
      {
        method: "POST",
        body: JSON.stringify(params),
      }
    ),

  // 轮询任务状态
  getTaskStatus: (taskId: string) =>
    request<VectorPageTaskStatus>(`/vec/page/status/${taskId}`),
};

// ==================== ASR 分P相关 ====================

export interface ASRContentResponse {
    exists: boolean;
    bvid?: string;
    cid?: number;
    page_index?: number;
    page_title?: string;
    content?: string;
    content_source?: "asr" | "user_edit";
    version?: number;
    is_processed?: boolean;
}

export interface ASRTaskStatus {
    task_id: string;
    status: "pending" | "processing" | "done" | "failed";
    progress: number;
    message: string;
}

export interface VideoPageVersionInfo {
    version: number;
    content_source: string;
    content_preview: string;
    is_latest: boolean;
    created_at: string;
}

// ASR 分P相关
export const asrApi = {
    // 查询 ASR 内容
    getContent: (bvid: string, cid: number) =>
        request<ASRContentResponse>(`/asr/content?bvid=${bvid}&cid=${cid}`),

    // 发起 ASR（幂等）
    create: (params: { bvid: string; cid: number; page_index: number; page_title?: string }) =>
        request<{ task_id: string | null; message: string; version?: number }>(
            "/asr/create",
            {
                method: "POST",
                body: JSON.stringify(params),
            }
        ),

    // 手动编辑更新
    update: (params: { bvid: string; cid: number; page_index: number; content: string }) =>
        request<{ success: boolean; message: string }>(
            "/asr/update",
            {
                method: "POST",
                body: JSON.stringify(params),
            }
        ),

    // 强制重新 ASR
    reasr: (params: { bvid: string; cid: number; page_index: number }) =>
        request<{ task_id: string; message: string }>(
            "/asr/reasr",
            {
                method: "POST",
                body: JSON.stringify(params),
            }
        ),

    // 轮询任务状态
    getStatus: (taskId: string) =>
        request<ASRTaskStatus>(`/asr/status/${taskId}`),

    // 查询版本历史
    getVersions: (bvid: string, cid: number) =>
        request<VideoPageVersionInfo[]>(`/asr/versions?bvid=${bvid}&cid=${cid}`),
};

// ==================== 用户 API Key 设置 ====================

export interface CredentialsStatus {
    llm_is_configured: boolean;
    llm_masked_key: string | null;
    llm_base_url: string | null;
    llm_model: string | null;
    embedding_is_configured: boolean;
    embedding_masked_key: string | null;
    embedding_base_url: string | null;
    embedding_model: string | null;
    asr_is_configured: boolean;
    asr_masked_key: string | null;
    asr_base_url: string | null;
    asr_model: string | null;
    updated_at: string | null;
}

export interface SetCredentialsParams {
    llm_api_key?: string;
    llm_base_url?: string;
    llm_model?: string;
    embedding_api_key?: string;
    embedding_base_url?: string;
    embedding_model?: string;
    asr_api_key?: string;
    asr_base_url?: string;
    asr_model?: string;
}

export const settingsApi = {
    getCredentialsStatus: (sessionId: string) =>
        request<CredentialsStatus>(`/settings/credentials/status?session_id=${sessionId}`),

    setCredentials: (sessionId: string, params: SetCredentialsParams) =>
        request<{ message: string }>(
            `/settings/credentials?session_id=${sessionId}`,
            {
                method: "POST",
                body: JSON.stringify(params),
            }
        ),

    deleteCredentials: (sessionId: string) =>
        request<{ message: string }>(
            `/settings/credentials?session_id=${sessionId}`,
            { method: "DELETE" }
        ),
};

// ==================== 多 Provider Credential 管理 ====================

export interface CredentialItem {
    id: number;
    name: string;
    provider: string;
    masked_key: string;
    base_url: string | null;
    default_model: string | null;
    is_default: boolean;
    created_at: string;
    updated_at: string;
}

export interface CredentialCreateParams {
    name: string;
    provider: string;
    api_key: string;
    base_url?: string;
    default_model?: string;
    is_default?: boolean;
}

export interface CredentialUpdateParams {
    name?: string;
    api_key?: string;
    base_url?: string;
    default_model?: string;
    is_default?: boolean;
}

export const credentialsApi = {
    list: (sessionId: string) =>
        request<CredentialItem[]>(`/credentials?session_id=${sessionId}`),

    create: (sessionId: string, data: CredentialCreateParams) =>
        request<CredentialItem>(`/credentials?session_id=${sessionId}`, {
            method: "POST",
            body: JSON.stringify(data),
        }),

    update: (sessionId: string, id: number, data: CredentialUpdateParams) =>
        request<CredentialItem>(`/credentials/${id}?session_id=${sessionId}`, {
            method: "PATCH",
            body: JSON.stringify(data),
        }),

    delete: (sessionId: string, id: number) =>
        request(`/credentials/${id}?session_id=${sessionId}`, { method: "DELETE" }),

    setDefault: (sessionId: string, id: number) =>
        request(`/credentials/${id}/default?session_id=${sessionId}`, { method: "POST" }),
};

// ==================== 计费/用量 ====================

export interface ProviderUsage {
    provider: string;
    total_tokens: number;
    api_calls: number;
    cost_estimate: number;
}

export interface CredentialUsageItem {
    credential_id: number | null;
    name: string;
    provider: string;
    total_tokens: number;
    api_calls: number;
    cost_estimate: number;
}

export interface UsageSummary {
    total_tokens: number;
    total_api_calls: number;
    by_provider: ProviderUsage[];
    by_credential: CredentialUsageItem[];
}

export const billingApi = {
    getSummary: (sessionId: string, days = 30) =>
        request<UsageSummary>(`/billing/summary?session_id=${sessionId}&days=${days}`),
};

// ==================== Quiz 题目训练系统 ====================

export interface QuizGenerateParams {
    session_id: string;
    folder_ids?: number[];
    pages?: Array<{ bvid: string; cid: number; page_index: number; page_title?: string }>;
    question_count?: number;
    difficulty?: string;
    title?: string;
}

export interface QuizGenerateResponse {
    quiz_uuid: string;
    question_count: number;
    estimated_cost_tokens: number;
}

export interface QuizQuestion {
    question_uuid: string;
    question_type: string;
    difficulty: string;
    question_text: string;
    options?: string[];
    correct_answer?: string | string[];
    explanation?: string;
    keywords?: string[];
}

export interface QuizSetData {
    quiz_uuid: string;
    title: string;
    status: string;
    question_count: number;
    type_distribution?: Record<string, number>;
    difficulty: string;
    total_score: number;
    passing_score: number;
    source_type?: string;
    source_pages?: Array<{ bvid: string; cid: number; page_index: number; page_title?: string }>;
    created_at: string;
    questions: QuizQuestion[];
}

export interface QuizAnswerItem {
    question_uuid: string;
    answer: string | string[];
}

export interface QuizAnswerResult {
    question_uuid: string;
    is_correct: boolean | null;
    auto_score: number | null;
    correct_answer: string | string[];
    grading_note?: string;
}

export interface QuizSubmissionResult {
    submission_uuid: string;
    score: number | null;
    passed: boolean | null;
    correct_count: number;
    total_count: number;
    results: QuizAnswerResult[];
}

export interface QuizHistoryItem {
    submission_uuid: string | null;
    quiz_uuid: string;
    title: string;
    status?: string;
    question_count?: number;
    difficulty?: string;
    source_type?: string;
    score: number | null;
    passed: boolean | null;
    correct_count: number;
    total_question_count: number;
    time_spent_seconds: number | null;
    submitted_at: string | null;
    created_at?: string;
}

export interface QuizHistoryResponse {
    submissions: QuizHistoryItem[];
    total: number;
    page: number;
    page_size: number;
    has_more: boolean;
}

export interface WrongAnswerItem {
    question_uuid: string;
    quiz_uuid: string;
    question_type: string;
    question_text: string;
    options?: string[];
    user_answer: string | string[];
    correct_answer: string | string[];
    explanation?: string;
    times_wrong: number;
    last_attempt_at: string;
}

export interface WrongAnswerResponse {
    wrong_answers: WrongAnswerItem[];
    total: number;
}

export const quizApi = {
    generate: (params: QuizGenerateParams) => {
        const sp = new URLSearchParams();
        sp.set("session_id", params.session_id);
        if (params.folder_ids?.length) sp.set("folder_ids", params.folder_ids.join(","));
        if (params.question_count) sp.set("question_count", String(params.question_count));
        if (params.difficulty) sp.set("difficulty", params.difficulty);
        if (params.title) sp.set("title", params.title);
        const body = params.pages?.length ? JSON.stringify(params.pages) : undefined;
        return request<QuizGenerateResponse>(`/quiz/generate?${sp.toString()}`, {
            method: "POST",
            ...(body ? { body, headers: { "Content-Type": "application/json" } } : {}),
        });
    },

    getQuiz: (quizUuid: string, includeAnswers = false) =>
        request<QuizSetData>(`/quiz/${quizUuid}${includeAnswers ? "?include_answers=true" : ""}`),

    submit: (params: {
        quiz_uuid: string;
        session_id: string;
        answers: QuizAnswerItem[];
        time_spent_seconds?: number;
    }) =>
        request<QuizSubmissionResult>("/quiz/submit", {
            method: "POST",
            body: JSON.stringify(params),
        }),

    getHistory: (sessionId: string, page = 1, pageSize = 10) =>
        request<QuizHistoryResponse>(
            `/quiz/history?session_id=${sessionId}&page=${page}&page_size=${pageSize}`
        ),

    getWrongAnswers: (sessionId: string, folderIds?: number[]) =>
        request<WrongAnswerResponse>(
            `/quiz/wrong-answers?session_id=${sessionId}${folderIds?.length ? `&folder_ids=${folderIds.join(",")}` : ""}`
        ),

    exportData: async (sessionId: string, format: "jsonl" | "csv" | "sft" = "jsonl", folderIds?: number[]) => {
        const url = `${API_BASE_URL}/quiz/export?session_id=${encodeURIComponent(sessionId)}&format=${format}${folderIds?.length ? `&folder_ids=${folderIds.join(",")}` : ""}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error("导出失败");
        return res.blob();
    },
};
