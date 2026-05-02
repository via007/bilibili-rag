"use client";

import { useState, useEffect, useCallback } from "react";
import { Loader2, CheckCircle, XCircle, Download, Database, Layers, History, Eye, ArrowLeft } from "lucide-react";
import {
    quizApi,
    favoritesApi,
    knowledgeApi,
    type QuizSetData,
    type QuizQuestion,
    type QuizAnswerResult,
    type QuizSubmissionResult,
    type FavoriteFolder,
    type FolderStatus,
    type VectorizedPageItem,
    type QuizHistoryItem,
} from "@/lib/api";
import { type DockPanelProps } from "@/lib/dock-registry";
import { useDockContext } from "@/lib/dock-context";

const TYPE_LABELS: Record<string, string> = {
    single_choice: "单选",
    multi_choice: "多选",
    short_answer: "简答",
    essay: "主观",
};

interface FolderInfo {
    media_id: number;
    title: string;
    media_count: number;
    indexed_count: number;
}

export default function QuizPanel({ isOpen }: DockPanelProps) {
    const { sessionId } = useDockContext();

    // Mode
    const [mode, setMode] = useState<"folder" | "pages">("folder");

    // Folder list
    const [folders, setFolders] = useState<FolderInfo[]>([]);
    const [loadingFolders, setLoadingFolders] = useState(false);
    const [selectedFolderIds, setSelectedFolderIds] = useState<Set<number>>(new Set());

    // Pages mode: vectorized pages list
    const [vectorizedPages, setVectorizedPages] = useState<VectorizedPageItem[]>([]);
    const [loadingPages, setLoadingPages] = useState(false);
    const [selectedPageKeys, setSelectedPageKeys] = useState<Set<string>>(new Set());

    // Generation config
    const [questionCount, setQuestionCount] = useState(10);
    const [difficulty, setDifficulty] = useState("medium");
    const [generating, setGenerating] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Current quiz
    const [currentQuiz, setCurrentQuiz] = useState<QuizSetData | null>(null);
    const [userAnswers, setUserAnswers] = useState<Map<string, string | string[]>>(new Map());
    const [submitting, setSubmitting] = useState(false);
    const [submitResult, setSubmitResult] = useState<QuizSubmissionResult | null>(null);

    // Review mode (viewing a past quiz)
    const [isReviewMode, setIsReviewMode] = useState(false);
    const [reviewCorrectAnswers, setReviewCorrectAnswers] = useState<Map<string, string | string[]>>(new Map());

    // History
    const [showHistory, setShowHistory] = useState(false);
    const [historyItems, setHistoryItems] = useState<QuizHistoryItem[]>([]);
    const [loadingHistory, setLoadingHistory] = useState(false);

    // Fetch folders on open
    useEffect(() => {
        if (!isOpen || !sessionId) return;
        setLoadingFolders(true);
        Promise.all([
            favoritesApi.getList(sessionId),
            knowledgeApi.getFolderStatus(sessionId),
        ])
            .then(([favList, statusList]) => {
                const statusMap = new Map<number, FolderStatus>();
                for (const s of statusList) statusMap.set(s.media_id, s);

                const merged: FolderInfo[] = favList.map((f: FavoriteFolder) => ({
                    media_id: f.media_id,
                    title: f.title,
                    media_count: f.media_count,
                    indexed_count: statusMap.get(f.media_id)?.indexed_count ?? 0,
                }));
                setFolders(merged);

                // Pre-select folders that have indexed data
                const preSelected = new Set<number>();
                for (const f of merged) {
                    if (f.indexed_count > 0) preSelected.add(f.media_id);
                }
                setSelectedFolderIds(preSelected);
            })
            .catch(() => setError("获取收藏夹列表失败"))
            .finally(() => setLoadingFolders(false));
    }, [isOpen, sessionId]);

    // Reset when closed
    useEffect(() => {
        if (!isOpen) {
            setCurrentQuiz(null);
            setSubmitResult(null);
            setUserAnswers(new Map());
            setError(null);
            setVectorizedPages([]);
            setSelectedPageKeys(new Set());
            setIsReviewMode(false);
            setReviewCorrectAnswers(new Map());
            setShowHistory(false);
        }
    }, [isOpen]);

    const toggleFolder = useCallback((id: number) => {
        setSelectedFolderIds((prev) => {
            const next = new Set(prev);
            next.has(id) ? next.delete(id) : next.add(id);
            return next;
        });
    }, []);

    // ────── Pages mode: fetch vectorized pages on mode switch ──────
    const fetchVectorizedPages = useCallback(async () => {
        if (!sessionId) return;
        setLoadingPages(true);
        setError(null);
        try {
            const pages = await knowledgeApi.getVectorizedPages(sessionId);
            setVectorizedPages(pages);
            // Pre-select all vectorized pages
            const keys = new Set<string>();
            for (const p of pages) {
                keys.add(`${p.bvid}:${p.page_index}`);
            }
            setSelectedPageKeys(keys);
        } catch (e) {
            setError(e instanceof Error ? e.message : "获取分P列表失败");
        } finally {
            setLoadingPages(false);
        }
    }, [sessionId]);

    // Fetch pages when switching to pages mode
    useEffect(() => {
        if (mode === "pages" && isOpen && sessionId) {
            fetchVectorizedPages();
        }
    }, [mode, isOpen, sessionId, fetchVectorizedPages]);

    const togglePage = useCallback((bvid: string, pageIndex: number) => {
        setSelectedPageKeys((prev) => {
            const next = new Set(prev);
            const key = `${bvid}:${pageIndex}`;
            next.has(key) ? next.delete(key) : next.add(key);
            return next;
        });
    }, []);

    const toggleAllPages = useCallback(() => {
        if (vectorizedPages.length === 0) return;
        const allKeys = vectorizedPages.map((p) => `${p.bvid}:${p.page_index}`);
        const allSelected = allKeys.every((k) => selectedPageKeys.has(k));
        setSelectedPageKeys(new Set(allSelected ? [] : allKeys));
    }, [vectorizedPages, selectedPageKeys]);

    // ────── Generate ──────
    const handleGenerate = useCallback(async () => {
        if (!sessionId) {
            setError("未登录");
            return;
        }

        setGenerating(true);
        setError(null);
        setCurrentQuiz(null);
        setSubmitResult(null);
        setUserAnswers(new Map());
        setIsReviewMode(false);

        try {
            if (mode === "pages") {
                const pages = vectorizedPages
                    .filter((p) => selectedPageKeys.has(`${p.bvid}:${p.page_index}`))
                    .map((p) => ({
                        bvid: p.bvid,
                        cid: p.cid,
                        page_index: p.page_index,
                        page_title: p.page_title || p.video_title || "",
                    }));

                if (pages.length === 0) {
                    setError("请选择至少一个分P");
                    setGenerating(false);
                    return;
                }

                const res = await quizApi.generate({
                    session_id: sessionId,
                    pages,
                    question_count: questionCount,
                    difficulty,
                });
                const quiz = await pollUntilReady(res.quiz_uuid);
                setCurrentQuiz(quiz);
            } else {
                const fids = Array.from(selectedFolderIds);
                if (fids.length === 0) {
                    setError("请选择至少一个收藏夹");
                    setGenerating(false);
                    return;
                }

                const res = await quizApi.generate({
                    session_id: sessionId,
                    folder_ids: fids,
                    question_count: questionCount,
                    difficulty,
                });
                const quiz = await pollUntilReady(res.quiz_uuid);
                setCurrentQuiz(quiz);
            }
        } catch (e) {
            setError(e instanceof Error ? e.message : "生成失败");
        } finally {
            setGenerating(false);
        }
    }, [mode, selectedFolderIds, selectedPageKeys, vectorizedPages, questionCount, difficulty, sessionId]);

    const handleSubmit = useCallback(async () => {
        if (!currentQuiz || !sessionId) return;

        const answers = currentQuiz.questions
            .map((q) => ({
                question_uuid: q.question_uuid,
                answer: userAnswers.get(q.question_uuid) ?? "",
            }))
            .filter((a) => a.answer !== "");

        setSubmitting(true);
        try {
            const result = await quizApi.submit({
                quiz_uuid: currentQuiz.quiz_uuid,
                session_id: sessionId,
                answers,
            });
            setSubmitResult(result);
        } catch (e) {
            setError(e instanceof Error ? e.message : "提交失败");
        } finally {
            setSubmitting(false);
        }
    }, [currentQuiz, sessionId, userAnswers]);

    const handleExport = useCallback(
        async (format: "jsonl" | "csv" | "sft") => {
            if (!sessionId) return;
            try {
                const blob = await quizApi.exportData(sessionId, format);
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = `quiz_export.${format}`;
                a.click();
                URL.revokeObjectURL(url);
            } catch (e) {
                setError(e instanceof Error ? e.message : "导出失败");
            }
        },
        [sessionId]
    );

    // Download a specific quiz with answers
    const handleDownloadQuiz = useCallback(async (quizUuid: string, title: string) => {
        try {
            const quiz = await quizApi.getQuiz(quizUuid, true);
            const blob = new Blob([JSON.stringify(quiz, null, 2)], { type: "application/json" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `${title || "quiz"}.json`;
            a.click();
            URL.revokeObjectURL(url);
        } catch (e) {
            setError(e instanceof Error ? e.message : "下载失败");
        }
    }, []);

    // Fetch quiz history
    const fetchHistory = useCallback(async () => {
        if (!sessionId) return;
        setLoadingHistory(true);
        try {
            const res = await quizApi.getHistory(sessionId, 1, 50);
            setHistoryItems(res.submissions);
        } catch (e) {
            setError(e instanceof Error ? e.message : "获取历史失败");
        } finally {
            setLoadingHistory(false);
        }
    }, [sessionId]);

    // View a past quiz (review mode)
    const handleViewPastQuiz = useCallback(async (quizUuid: string) => {
        try {
            const quiz = await quizApi.getQuiz(quizUuid, true);
            // Build correct answers map
            const answers = new Map<string, string | string[]>();
            for (const q of quiz.questions) {
                if (q.correct_answer !== undefined) {
                    answers.set(q.question_uuid, q.correct_answer);
                }
            }
            setReviewCorrectAnswers(answers);
            setCurrentQuiz(quiz);
            setIsReviewMode(true);
            setSubmitResult(null);
            setUserAnswers(new Map());
        } catch (e) {
            setError(e instanceof Error ? e.message : "加载题目失败");
        }
    }, []);

    // Back to generate from review
    const handleBackToGenerate = useCallback(() => {
        setCurrentQuiz(null);
        setIsReviewMode(false);
        setSubmitResult(null);
        setUserAnswers(new Map());
        setReviewCorrectAnswers(new Map());
    }, []);

    const isAllAnswered =
        currentQuiz?.questions.every((q) => {
            const ans = userAnswers.get(q.question_uuid);
            if (!ans) return false;
            if (Array.isArray(ans)) return ans.length > 0;
            return String(ans).trim().length > 0;
        }) ?? false;

    if (!isOpen) return null;

    const selectedFolderCount = selectedFolderIds.size;
    const hasIndexedFolders = folders.some((f) => f.indexed_count > 0);

    // Pages mode stats
    const totalPageCount = vectorizedPages.length;
    const selectedPageCount = selectedPageKeys.size;
    const allPagesSelected = totalPageCount > 0 && selectedPageCount === totalPageCount;

    return (
        <div style={{ color: "var(--foreground)", padding: "16px", overflow: "auto", flex: 1 }}>
            {error && (
                <div
                    style={{
                        color: "var(--danger)",
                        background: "var(--danger-bg)",
                        padding: "8px 12px",
                        borderRadius: "8px",
                        marginBottom: "12px",
                        fontSize: "14px",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                    }}
                >
                    <span>{error}</span>
                    <button
                        onClick={() => setError(null)}
                        style={{
                            background: "none",
                            border: "none",
                            color: "var(--danger)",
                            cursor: "pointer",
                            fontSize: "16px",
                        }}
                    >
                        ✕
                    </button>
                </div>
            )}

            {!currentQuiz ? (
                <div>
                    {/* Mode toggle */}
                    <div
                        style={{
                            display: "flex",
                            background: "var(--card)",
                            borderRadius: "10px",
                            padding: "3px",
                            marginBottom: "16px",
                            border: "1px solid var(--border)",
                        }}
                    >
                        <button
                            onClick={() => setMode("folder")}
                            style={{
                                flex: 1,
                                padding: "8px 0",
                                borderRadius: "8px",
                                border: "none",
                                cursor: "pointer",
                                fontSize: "13px",
                                fontWeight: 600,
                                background: mode === "folder"
                                    ? "linear-gradient(180deg, rgba(6,182,212,0.18) 0%, rgba(6,182,212,0.1) 100%)"
                                    : "transparent",
                                color: mode === "folder" ? "var(--accent)" : "var(--muted-foreground)",
                            }}
                        >
                            <Database size={14} style={{ display: "inline", marginRight: "4px" }} />
                            按收藏夹
                        </button>
                        <button
                            onClick={() => setMode("pages")}
                            style={{
                                flex: 1,
                                padding: "8px 0",
                                borderRadius: "8px",
                                border: "none",
                                cursor: "pointer",
                                fontSize: "13px",
                                fontWeight: 600,
                                background: mode === "pages"
                                    ? "linear-gradient(180deg, rgba(6,182,212,0.18) 0%, rgba(6,182,212,0.1) 100%)"
                                    : "transparent",
                                color: mode === "pages" ? "var(--accent)" : "var(--muted-foreground)",
                            }}
                        >
                            <Layers size={14} style={{ display: "inline", marginRight: "4px" }} />
                            按分P
                        </button>
                    </div>

                    {/* ────── Folder mode ────── */}
                    {mode === "folder" && (
                        <>
                            <p
                                style={{
                                    fontSize: "13px",
                                    color: "var(--muted-foreground)",
                                    marginBottom: "8px",
                                }}
                            >
                                选择已入库的收藏夹出题
                            </p>

                            {loadingFolders ? (
                                <div
                                    style={{
                                        display: "flex",
                                        alignItems: "center",
                                        gap: "8px",
                                        padding: "16px",
                                        color: "var(--muted-foreground)",
                                        fontSize: "14px",
                                    }}
                                >
                                    <Loader2 size={16} className="animate-spin" />
                                    加载收藏夹...
                                </div>
                            ) : folders.length === 0 ? (
                                <div
                                    style={{
                                        padding: "16px",
                                        color: "var(--muted-foreground)",
                                        fontSize: "14px",
                                        textAlign: "center",
                                    }}
                                >
                                    暂无收藏夹，请先在收藏夹面板中同步数据
                                </div>
                            ) : (
                                <div
                                    style={{
                                        maxHeight: "240px",
                                        overflow: "auto",
                                        marginBottom: "16px",
                                        borderRadius: "10px",
                                        border: "1px solid var(--border)",
                                    }}
                                >
                                    {folders.map((f) => (
                                        <label
                                            key={f.media_id}
                                            style={{
                                                display: "flex",
                                                alignItems: "center",
                                                justifyContent: "space-between",
                                                padding: "10px 14px",
                                                cursor: "pointer",
                                                borderBottom: "1px solid var(--border)",
                                                background: selectedFolderIds.has(f.media_id)
                                                    ? "rgba(6,182,212,0.08)"
                                                    : "transparent",
                                            }}
                                        >
                                            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                                                <input
                                                    type="checkbox"
                                                    checked={selectedFolderIds.has(f.media_id)}
                                                    onChange={() => toggleFolder(f.media_id)}
                                                    style={{ accentColor: "var(--accent)" }}
                                                />
                                                <div>
                                                    <div style={{ fontSize: "14px", fontWeight: 500 }}>
                                                        {f.title}
                                                    </div>
                                                    <div
                                                        style={{
                                                            fontSize: "12px",
                                                            color: "var(--muted-foreground)",
                                                        }}
                                                    >
                                                        {f.media_count} 个视频
                                                    </div>
                                                </div>
                                            </div>
                                            <span
                                                style={{
                                                    fontSize: "12px",
                                                    padding: "2px 8px",
                                                    borderRadius: "6px",
                                                    background: f.indexed_count > 0
                                                        ? "var(--success-bg)"
                                                        : "rgba(107,114,128,0.1)",
                                                    color: f.indexed_count > 0
                                                        ? "var(--success)"
                                                        : "var(--muted-foreground)",
                                                }}
                                            >
                                                <Database size={10} style={{ display: "inline", marginRight: "3px" }} />
                                                {f.indexed_count > 0 ? `${f.indexed_count} 已入库` : "未入库"}
                                            </span>
                                        </label>
                                    ))}
                                </div>
                            )}

                            <GenerateButton
                                generating={generating}
                                disabled={selectedFolderCount === 0}
                                onClick={handleGenerate}
                                label={`生成题目 (${selectedFolderCount} 个收藏夹)`}
                            />

                            {!hasIndexedFolders && folders.length > 0 && !loadingFolders && (
                                <p
                                    style={{
                                        fontSize: "12px",
                                        color: "var(--warning)",
                                        textAlign: "center",
                                        marginTop: "4px",
                                    }}
                                >
                                    提示：需要先在收藏夹面板中将视频入库，才能生成题目
                                </p>
                            )}
                        </>
                    )}

                    {/* ────── Pages mode ────── */}
                    {mode === "pages" && (
                        <>
                            <div
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "space-between",
                                    marginBottom: "8px",
                                }}
                            >
                                <p
                                    style={{
                                        fontSize: "13px",
                                        color: "var(--muted-foreground)",
                                        margin: 0,
                                    }}
                                >
                                    选择已向量化的分P出题
                                </p>
                                {totalPageCount > 0 && (
                                    <button
                                        onClick={toggleAllPages}
                                        style={{
                                            fontSize: "12px",
                                            padding: "3px 10px",
                                            borderRadius: "6px",
                                            background: "var(--card)",
                                            color: "var(--muted-foreground)",
                                            border: "1px solid var(--border)",
                                            cursor: "pointer",
                                        }}
                                    >
                                        {allPagesSelected ? "取消全选" : "全选"}
                                    </button>
                                )}
                            </div>

                            {loadingPages ? (
                                <div
                                    style={{
                                        display: "flex",
                                        alignItems: "center",
                                        gap: "8px",
                                        padding: "16px",
                                        color: "var(--muted-foreground)",
                                        fontSize: "14px",
                                    }}
                                >
                                    <Loader2 size={16} className="animate-spin" />
                                    加载分P列表...
                                </div>
                            ) : vectorizedPages.length === 0 ? (
                                <div
                                    style={{
                                        padding: "16px",
                                        color: "var(--muted-foreground)",
                                        fontSize: "14px",
                                        textAlign: "center",
                                    }}
                                >
                                    暂无已入库的分P，请先在收藏夹面板中同步入库
                                </div>
                            ) : (
                                <div
                                    style={{
                                        maxHeight: "300px",
                                        overflow: "auto",
                                        marginBottom: "16px",
                                        borderRadius: "10px",
                                        border: "1px solid var(--border)",
                                    }}
                                >
                                    {vectorizedPages.map((p) => {
                                        const key = `${p.bvid}:${p.page_index}`;
                                        const isSelected = selectedPageKeys.has(key);
                                        return (
                                            <label
                                                key={key}
                                                style={{
                                                    display: "flex",
                                                    alignItems: "center",
                                                    justifyContent: "space-between",
                                                    padding: "10px 14px",
                                                    cursor: "pointer",
                                                    borderBottom: "1px solid var(--border)",
                                                    background: isSelected
                                                        ? "rgba(6,182,212,0.08)"
                                                        : "transparent",
                                                }}
                                            >
                                                <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                                                    <input
                                                        type="checkbox"
                                                        checked={isSelected}
                                                        onChange={() => togglePage(p.bvid, p.page_index)}
                                                        style={{ accentColor: "var(--accent)" }}
                                                    />
                                                    <div>
                                                        <div style={{ fontSize: "14px", fontWeight: 500 }}>
                                                            {p.page_title || `P${p.page_index + 1}`}
                                                        </div>
                                                        <div
                                                            style={{
                                                                fontSize: "12px",
                                                                color: "var(--muted-foreground)",
                                                            }}
                                                        >
                                                            {p.video_title || p.bvid}
                                                        </div>
                                                    </div>
                                                </div>
                                                <span
                                                    style={{
                                                        fontSize: "12px",
                                                        padding: "2px 8px",
                                                        borderRadius: "6px",
                                                        background: "var(--success-bg)",
                                                        color: "var(--success)",
                                                        flexShrink: 0,
                                                    }}
                                                >
                                                    <Database size={10} style={{ display: "inline", marginRight: "3px" }} />
                                                    {p.vector_chunk_count} 块
                                                </span>
                                            </label>
                                        );
                                    })}
                                </div>
                            )}

                            <GenerateButton
                                generating={generating}
                                disabled={selectedPageCount === 0}
                                onClick={handleGenerate}
                                label={`生成题目 (${selectedPageCount} 个分P)`}
                            />
                        </>
                    )}

                    {/* Config — shared between modes */}
                    <div style={{ display: "flex", gap: "12px", marginTop: "12px", marginBottom: "12px" }}>
                        <div style={{ flex: 1 }}>
                            <label
                                style={{
                                    fontSize: "13px",
                                    color: "var(--muted-foreground)",
                                    display: "block",
                                    marginBottom: "6px",
                                }}
                            >
                                题目数量
                            </label>
                            <input
                                type="number"
                                min={1}
                                max={50}
                                value={questionCount}
                                onChange={(e) => setQuestionCount(Number(e.target.value))}
                                style={{
                                    width: "100%",
                                    padding: "10px 12px",
                                    borderRadius: "8px",
                                    background: "var(--background)",
                                    color: "var(--foreground)",
                                    border: "1px solid var(--border)",
                                    fontSize: "14px",
                                }}
                            />
                        </div>
                        <div style={{ flex: 1 }}>
                            <label
                                style={{
                                    fontSize: "13px",
                                    color: "var(--muted-foreground)",
                                    display: "block",
                                    marginBottom: "6px",
                                }}
                            >
                                难度
                            </label>
                            <select
                                value={difficulty}
                                onChange={(e) => setDifficulty(e.target.value)}
                                style={{
                                    width: "100%",
                                    padding: "10px 12px",
                                    borderRadius: "8px",
                                    background: "var(--background)",
                                    color: "var(--foreground)",
                                    border: "1px solid var(--border)",
                                    fontSize: "14px",
                                }}
                            >
                                <option value="easy">简单</option>
                                <option value="medium">中等</option>
                                <option value="hard">困难</option>
                            </select>
                        </div>
                    </div>

                    {/* Export area */}
                    <div
                        style={{
                            marginTop: "24px",
                            borderTop: "1px solid var(--border)",
                            paddingTop: "16px",
                        }}
                    >
                        <p
                            style={{
                                fontSize: "13px",
                                color: "var(--muted-foreground)",
                                marginBottom: "8px",
                            }}
                        >
                            导出训练数据
                        </p>
                        <div style={{ display: "flex", gap: "8px" }}>
                            {(["jsonl", "csv", "sft"] as const).map((fmt) => (
                                <button
                                    key={fmt}
                                    onClick={() => handleExport(fmt)}
                                    style={{
                                        flex: 1,
                                        padding: "8px",
                                        borderRadius: "8px",
                                        background: "var(--card)",
                                        color: "var(--muted-foreground)",
                                        border: "1px solid var(--border)",
                                        cursor: "pointer",
                                        fontSize: "13px",
                                        fontWeight: 600,
                                        textTransform: "uppercase",
                                    }}
                                >
                                    <Download
                                        size={14}
                                        style={{ display: "inline", marginRight: "4px" }}
                                    />
                                    {fmt}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* History section */}
                    <div
                        style={{
                            marginTop: "24px",
                            borderTop: "1px solid var(--border)",
                            paddingTop: "16px",
                        }}
                    >
                        <button
                            onClick={() => {
                                const willShow = !showHistory;
                                setShowHistory(willShow);
                                if (willShow) fetchHistory();
                            }}
                            style={{
                                display: "flex",
                                alignItems: "center",
                                gap: "6px",
                                background: "none",
                                border: "none",
                                color: "var(--muted-foreground)",
                                cursor: "pointer",
                                fontSize: "13px",
                                fontWeight: 600,
                                padding: 0,
                                marginBottom: showHistory ? "12px" : 0,
                            }}
                        >
                            <History size={14} />
                            题目历史
                            <span style={{ fontSize: "11px", transform: showHistory ? "rotate(90deg)" : "rotate(0deg)", transition: "transform 0.2s" }}>
                                ▶
                            </span>
                        </button>

                        {showHistory && (
                            loadingHistory ? (
                                <div style={{ display: "flex", alignItems: "center", gap: "8px", padding: "12px", color: "var(--muted-foreground)", fontSize: "13px" }}>
                                    <Loader2 size={14} className="animate-spin" />
                                    加载历史...
                                </div>
                            ) : historyItems.length === 0 ? (
                                <div style={{ padding: "12px", color: "var(--muted-foreground)", fontSize: "13px", textAlign: "center" }}>
                                    暂无历史记录
                                </div>
                            ) : (
                                <div style={{ maxHeight: "260px", overflow: "auto", borderRadius: "10px", border: "1px solid var(--border)" }}>
                                    {historyItems.map((item) => (
                                        <div
                                            key={item.submission_uuid}
                                            style={{
                                                display: "flex",
                                                alignItems: "center",
                                                justifyContent: "space-between",
                                                padding: "10px 14px",
                                                borderBottom: "1px solid var(--border)",
                                            }}
                                        >
                                            <div style={{ flex: 1, minWidth: 0 }}>
                                                <div style={{ fontSize: "13px", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                                    {item.title}
                                                </div>
                                                <div style={{ fontSize: "11px", color: "var(--muted-foreground)", marginTop: "2px" }}>
                                                    {item.question_count ?? item.total_question_count} 题
                                                    {item.submission_uuid ? (
                                                        <>
                                                            {item.score != null && ` · ${item.score}分`}
                                                            {item.passed != null && (item.passed ? " · 通过" : " · 未通过")}
                                                        </>
                                                    ) : (
                                                        " · 未作答"
                                                    )}
                                                    {item.created_at && ` · ${new Date(item.created_at).toLocaleDateString()}`}
                                                </div>
                                            </div>
                                            <div style={{ display: "flex", gap: "6px", flexShrink: 0, marginLeft: "8px" }}>
                                                <button
                                                    onClick={() => handleViewPastQuiz(item.quiz_uuid)}
                                                    style={{
                                                        padding: "5px 10px",
                                                        borderRadius: "6px",
                                                        background: "var(--card)",
                                                        color: "var(--accent)",
                                                        border: "1px solid rgba(6,182,212,0.25)",
                                                        cursor: "pointer",
                                                        fontSize: "12px",
                                                        fontWeight: 600,
                                                    }}
                                                >
                                                    <Eye size={12} style={{ display: "inline", marginRight: "3px" }} />
                                                    查看
                                                </button>
                                                <button
                                                    onClick={() => handleDownloadQuiz(item.quiz_uuid, item.title)}
                                                    style={{
                                                        padding: "5px 10px",
                                                        borderRadius: "6px",
                                                        background: "var(--card)",
                                                        color: "var(--muted-foreground)",
                                                        border: "1px solid var(--border)",
                                                        cursor: "pointer",
                                                        fontSize: "12px",
                                                        fontWeight: 600,
                                                    }}
                                                >
                                                    <Download size={12} style={{ display: "inline", marginRight: "3px" }} />
                                                    下载
                                                </button>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )
                        )}
                    </div>
                </div>
            ) : (
                /* ────── Quiz Questions ────── */
                <div>
                    <div
                        style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            marginBottom: "16px",
                        }}
                    >
                        <div>
                            <h4 style={{ margin: 0, fontSize: "16px" }}>
                                {isReviewMode && (
                                    <span style={{ fontSize: "11px", padding: "2px 8px", borderRadius: "6px", background: "rgba(6,182,212,0.12)", color: "var(--accent)", marginRight: "8px", fontWeight: 600 }}>
                                        回看
                                    </span>
                                )}
                                {currentQuiz.title}
                            </h4>
                            <span style={{ fontSize: "12px", color: "var(--muted-foreground)" }}>
                                {currentQuiz.question_count} 题 · {currentQuiz.difficulty}
                                {currentQuiz.source_type === "pages" && " · 按分P"}
                            </span>
                        </div>
                        <div style={{ display: "flex", gap: "8px" }}>
                            {!submitResult && !isReviewMode && (
                                <button
                                    onClick={handleSubmit}
                                    disabled={!isAllAnswered || submitting}
                                    style={{
                                        padding: "8px 20px",
                                        borderRadius: "8px",
                                        fontWeight: 700,
                                        cursor: isAllAnswered && !submitting ? "pointer" : "not-allowed",
                                        background: "var(--accent)",
                                        color: "#0d1117",
                                        border: "none",
                                        opacity: isAllAnswered && !submitting ? 1 : 0.5,
                                    }}
                                >
                                    {submitting ? (
                                        <span
                                            style={{
                                                display: "flex",
                                                alignItems: "center",
                                                gap: "6px",
                                            }}
                                        >
                                            <Loader2 size={14} className="animate-spin" />
                                            批改中
                                        </span>
                                    ) : (
                                        `交卷 (${userAnswers.size}/${currentQuiz.questions.length})`
                                    )}
                                </button>
                            )}
                            {(submitResult || isReviewMode) && (
                                <button
                                    onClick={handleBackToGenerate}
                                    style={{
                                        padding: "8px 16px",
                                        borderRadius: "8px",
                                        cursor: "pointer",
                                        background: "var(--card)",
                                        color: "var(--muted-foreground)",
                                        border: "1px solid var(--border)",
                                        fontWeight: 600,
                                        fontSize: "13px",
                                    }}
                                >
                                    <ArrowLeft size={14} style={{ display: "inline", marginRight: "4px" }} />
                                    返回
                                </button>
                            )}
                            <button
                                onClick={() =>
                                    handleDownloadQuiz(currentQuiz.quiz_uuid, currentQuiz.title)
                                }
                                style={{
                                    padding: "8px 16px",
                                    borderRadius: "8px",
                                    cursor: "pointer",
                                    background: "var(--card)",
                                    color: "var(--muted-foreground)",
                                    border: "1px solid var(--border)",
                                    fontWeight: 600,
                                    fontSize: "13px",
                                }}
                            >
                                <Download size={14} style={{ display: "inline", marginRight: "4px" }} />
                                下载
                            </button>
                        </div>
                    </div>

                    {currentQuiz.questions.map((q, i) => {
                        // In review mode, create a pseudo-result to show correct answers
                        const reviewResult: QuizAnswerResult | undefined = isReviewMode
                            ? {
                                  question_uuid: q.question_uuid,
                                  is_correct: null,
                                  auto_score: null,
                                  correct_answer: reviewCorrectAnswers.get(q.question_uuid) ?? "",
                              }
                            : undefined;
                        return (
                            <QuizQuestionCard
                                key={q.question_uuid}
                                index={i}
                                question={q}
                                userAnswer={userAnswers.get(q.question_uuid)}
                                result={
                                    submitResult?.results.find(
                                        (r) => r.question_uuid === q.question_uuid
                                    ) ?? reviewResult
                                }
                                disabled={!!submitResult || isReviewMode}
                                onAnswer={(uuid, ans) =>
                                    setUserAnswers((prev) => {
                                        const next = new Map(prev);
                                        next.set(uuid, ans);
                                        return next;
                                    })
                                }
                            />
                        );
                    })}

                    {/* Result summary */}
                    {submitResult && (
                        <div
                            style={{
                                padding: "16px",
                                borderRadius: "12px",
                                textAlign: "center",
                                background: submitResult.passed
                                    ? "var(--success-bg)"
                                    : "var(--danger-bg)",
                                border: `1px solid ${
                                    submitResult.passed ? "var(--success)" : "var(--danger)"
                                }`,
                            }}
                        >
                            <p
                                style={{
                                    fontSize: "20px",
                                    fontWeight: 700,
                                    color: submitResult.passed
                                        ? "var(--success)"
                                        : "var(--danger)",
                                    margin: 0,
                                }}
                            >
                                {submitResult.score} 分 -{" "}
                                {submitResult.passed ? "通过" : "未通过"}
                            </p>
                            <p style={{ color: "var(--muted-foreground)", margin: "8px 0 0" }}>
                                {submitResult.correct_count}/{submitResult.total_count} 正确
                            </p>
                            <div style={{ display: "flex", gap: "8px", justifyContent: "center", marginTop: "12px" }}>
                                <button
                                    onClick={handleBackToGenerate}
                                    style={{
                                        padding: "8px 20px",
                                        borderRadius: "8px",
                                        background:
                                            "linear-gradient(180deg, rgba(6,182,212,0.18) 0%, rgba(6,182,212,0.1) 100%)",
                                        color: "var(--accent)",
                                        border: "1px solid rgba(6,182,212,0.25)",
                                        cursor: "pointer",
                                        fontWeight: 600,
                                    }}
                                >
                                    再做一套
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

/* ────── Generate Button (reusable) ────── */

function GenerateButton({
    generating,
    disabled,
    onClick,
    label,
}: {
    generating: boolean;
    disabled: boolean;
    onClick: () => void;
    label: string;
}) {
    return (
        <button
            disabled={generating || disabled}
            onClick={onClick}
            style={{
                width: "100%",
                padding: "12px",
                borderRadius: "10px",
                fontWeight: 700,
                cursor: generating || disabled ? "not-allowed" : "pointer",
                background: "linear-gradient(180deg, rgba(6,182,212,0.18) 0%, rgba(6,182,212,0.1) 100%)",
                color: "var(--accent)",
                border: "1px solid rgba(6,182,212,0.25)",
                opacity: generating || disabled ? 0.5 : 1,
                marginBottom: "8px",
            }}
        >
            {generating ? (
                <span
                    style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        gap: "8px",
                    }}
                >
                    <Loader2 size={16} className="animate-spin" />
                    AI 正在出题...
                </span>
            ) : (
                label
            )}
        </button>
    );
}

/* ────── Question Card ────── */

function QuizQuestionCard({
    index,
    question,
    userAnswer,
    result,
    disabled,
    onAnswer,
}: {
    index: number;
    question: QuizQuestion;
    userAnswer?: string | string[];
    result?: QuizAnswerResult;
    disabled: boolean;
    onAnswer: (uuid: string, answer: string | string[]) => void;
}) {
    const isMulti = question.question_type === "multi_choice";
    const showResult = !!result;
    const isCorrect = result?.is_correct;
    const hasGradingNote = !!result?.grading_note;

    return (
        <div
            style={{
                background: "var(--card)",
                border: `1px solid ${
                    showResult && isCorrect === false ? "var(--danger)" : "var(--border)"
                }`,
                borderRadius: "12px",
                padding: "16px",
                marginBottom: "12px",
            }}
        >
            {/* Header */}
            <div
                style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    marginBottom: "12px",
                }}
            >
                <span style={{ fontWeight: 700, color: "var(--foreground)" }}>
                    Q{index + 1}.
                </span>
                <span
                    style={{
                        fontSize: "11px",
                        padding: "2px 8px",
                        borderRadius: "6px",
                        background: "rgba(6, 182, 212, 0.1)",
                        color: "var(--accent)",
                        fontWeight: 600,
                    }}
                >
                    {TYPE_LABELS[question.question_type] || question.question_type}
                </span>
                {showResult && (
                    <span style={{ marginLeft: "auto" }}>
                        {isCorrect ? (
                            <CheckCircle size={18} style={{ color: "var(--success)" }} />
                        ) : (
                            <XCircle size={18} style={{ color: "var(--danger)" }} />
                        )}
                    </span>
                )}
            </div>

            {/* Question text */}
            <p
                style={{
                    color: "var(--foreground)",
                    marginBottom: "12px",
                    lineHeight: 1.6,
                }}
            >
                {question.question_text}
            </p>

            {/* Options (choice questions) */}
            {question.options?.map((opt, i) => {
                const optKey = opt[0];
                const isSelected = Array.isArray(userAnswer)
                    ? userAnswer.includes(optKey)
                    : userAnswer === optKey;

                let bgColor = "var(--card)";
                let borderColor = "var(--border)";
                if (showResult) {
                    const correctAnswer = result!.correct_answer;
                    const correctKeys = Array.isArray(correctAnswer)
                        ? correctAnswer.map((s: string) =>
                              String(s).trim().toUpperCase()[0]
                          )
                        : [String(correctAnswer).trim().toUpperCase()[0]];
                    if (correctKeys.includes(optKey)) {
                        bgColor = "var(--success-bg)";
                        borderColor = "var(--success)";
                    } else if (isSelected && !correctKeys.includes(optKey)) {
                        bgColor = "var(--danger-bg)";
                        borderColor = "var(--danger)";
                    }
                } else if (isSelected) {
                    borderColor = "var(--accent)";
                }

                return (
                    <label
                        key={i}
                        style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "10px",
                            padding: "10px 12px",
                            borderRadius: "8px",
                            background: bgColor,
                            border: `1px solid ${borderColor}`,
                            cursor: disabled ? "default" : "pointer",
                            marginBottom: "6px",
                        }}
                    >
                        <input
                            type={isMulti ? "checkbox" : "radio"}
                            name={`q-${question.question_uuid}`}
                            checked={isSelected}
                            disabled={disabled}
                            onChange={() => {
                                if (isMulti) {
                                    const arr = Array.isArray(userAnswer)
                                        ? [...userAnswer]
                                        : [];
                                    arr.includes(optKey)
                                        ? arr.splice(arr.indexOf(optKey), 1)
                                        : arr.push(optKey);
                                    onAnswer(question.question_uuid, arr);
                                } else {
                                    onAnswer(question.question_uuid, optKey);
                                }
                            }}
                            style={{ accentColor: "var(--accent)" }}
                        />
                        <span style={{ color: "var(--foreground)", fontSize: "14px" }}>
                            {opt}
                        </span>
                    </label>
                );
            })}

            {/* Text input for short_answer / essay */}
            {!question.options && (
                <textarea
                    style={{
                        width: "100%",
                        minHeight: "100px",
                        padding: "10px 12px",
                        borderRadius: "8px",
                        background: "var(--background)",
                        color: "var(--foreground)",
                        border: "1px solid var(--border)",
                        resize: "vertical",
                        fontFamily: "inherit",
                    }}
                    placeholder="请输入答案..."
                    value={(userAnswer as string) ?? ""}
                    onChange={(e) => onAnswer(question.question_uuid, e.target.value)}
                    disabled={disabled}
                />
            )}

            {/* Result feedback */}
            {showResult && (
                <div
                    style={{
                        marginTop: "12px",
                        padding: "10px 12px",
                        borderRadius: "8px",
                        background: isCorrect === false
                            ? "var(--danger-bg)"
                            : isCorrect === true
                            ? "var(--success-bg)"
                            : "rgba(6,182,212,0.08)",
                        border: `1px solid ${
                            isCorrect === false ? "var(--danger)"
                            : isCorrect === true ? "var(--success)"
                            : "rgba(6,182,212,0.25)"
                        }`,
                    }}
                >
                    {isCorrect === true ? (
                        <span style={{ color: "var(--success)", fontWeight: 600 }}>
                            ✓ 正确
                        </span>
                    ) : isCorrect === false ? (
                        <>
                            <span style={{ color: "var(--danger)", fontWeight: 600 }}>
                                ✗
                            </span>
                            <span
                                style={{
                                    color: "var(--muted-foreground)",
                                    marginLeft: "8px",
                                }}
                            >
                                正确答案：
                                {Array.isArray(result!.correct_answer)
                                    ? result!.correct_answer.join(", ")
                                    : String(result!.correct_answer)}
                            </span>
                        </>
                    ) : (
                        <span style={{ color: "var(--accent)", fontWeight: 600 }}>
                            正确答案：
                            {Array.isArray(result!.correct_answer)
                                ? result!.correct_answer.join(", ")
                                : String(result!.correct_answer)}
                        </span>
                    )}
                    {hasGradingNote && (
                        <span
                            style={{
                                marginLeft: "8px",
                                fontSize: "11px",
                                color: "var(--warning)",
                                fontWeight: 600,
                            }}
                        >
                            {result!.grading_note}
                        </span>
                    )}
                    {question.explanation && (
                        <p style={{
                            margin: "8px 0 0",
                            fontSize: "12px",
                            color: "var(--muted-foreground)",
                            lineHeight: 1.6,
                            borderTop: "1px solid var(--border)",
                            paddingTop: "8px",
                        }}>
                            <span style={{ fontWeight: 600 }}>解析：</span>
                            {question.explanation}
                        </p>
                    )}
                </div>
            )}
        </div>
    );
}

/* ────── Poll helper ────── */

async function pollUntilReady(
    quizUuid: string,
    maxRetries = 30,
    intervalMs = 2000
): Promise<QuizSetData> {
    for (let i = 0; i < maxRetries; i++) {
        const quiz = await quizApi.getQuiz(quizUuid);
        if (quiz.status === "done") return quiz;
        if (quiz.status === "failed") throw new Error("题目生成失败");
        await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
    throw new Error("题目生成超时");
}
