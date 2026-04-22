"use client";

import { useState, useEffect } from "react";
import {
  FavoriteFolder,
  Video,
  VideoPageInfo,
  favoritesApi,
  knowledgeApi,
  vecPageApi,
  VectorPageStatusResponse,
  BuildStatus,
  FolderStatus,
  OrganizePreviewResponse,
  WorkspacePage,
} from "@/lib/api";
import OrganizePreviewModal from "@/components/OrganizePreviewModal";
import WorkspacePanel from "@/components/WorkspacePanel";

interface Props {
  sessionId: string;
  onBuildDone?: () => void;
  onSelectionChange?: (folderIds: number[]) => void;
  onOpenASR?: (bvid: string, cid: number, pageTitle: string, pageIndex?: number) => void;
  externalVectorUpdate?: {
    bvid: string;
    cid: number;
    status: VectorPageStatusResponse;
    version: number;
  } | null;
  workspacePages?: WorkspacePage[];
  onWorkspacePagesChange?: (pages: WorkspacePage[]) => void;
}

export default function SourcesPanel({
  sessionId,
  onBuildDone,
  onSelectionChange,
  onOpenASR,
  externalVectorUpdate,
  workspacePages = [],
  onWorkspacePagesChange,
}: Props) {
  const [folders, setFolders] = useState<(FavoriteFolder & { videos?: Video[]; expanded?: boolean; loading?: boolean; count_source?: "bili" | "filtered" | "db" })[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(true);
  const [building, setBuilding] = useState(false);
  const [progress, setProgress] = useState<BuildStatus | null>(null);
  const [statusMap, setStatusMap] = useState<Record<number, FolderStatus>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [organizeOpen, setOrganizeOpen] = useState(false);
  const [organizeLoading, setOrganizeLoading] = useState(false);
  const [organizePreview, setOrganizePreview] = useState<OrganizePreviewResponse | null>(null);
  const [organizeMessage, setOrganizeMessage] = useState<string | null>(null);

  // 分P展开状态（key: bvid）
  const [expandedVideos, setExpandedVideos] = useState<Set<string>>(new Set());

  // 分P数据缓存（key: bvid）
  const [pageCache, setPageCache] = useState<Record<string, VideoPageInfo[]>>({});

  // 分P向量化状态缓存（key: `${bvid}-${cid}`）
  const [pageVectorStatus, setPageVectorStatus] = useState<Record<string, VectorPageStatusResponse>>({});

  // 向量化操作提示
  const [vectorMessage, setVectorMessage] = useState<string | null>(null);

  // 加载收藏夹列表（从B站获取）
  const loadFolders = async () => {
    setLoading(true);
    try {
      const data = await favoritesApi.getList(sessionId);
      setFolders(data.map((f) => ({ ...f, count_source: "bili" })));
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  // 加载入库状态（从本地数据库）
  const loadStatuses = async () => {
    try {
      const data = await knowledgeApi.getFolderStatus(sessionId);
      const map: Record<number, FolderStatus> = {};
      data.forEach((item) => {
        map[item.media_id] = item;
      });
      setStatusMap(map);
      setFolders((prev) =>
        prev.map((f) => {
          const s = map[f.media_id];
          if (!s?.media_count) return f;
          if (f.count_source === "filtered") return f;
          return { ...f, count_source: "bili" };
        })
      );
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadFolders().then(loadStatuses);
  }, [sessionId]);

  useEffect(() => {
    if (!externalVectorUpdate) return;
    const { bvid, cid, status } = externalVectorUpdate;
    setPageVectorStatus((prev) => ({
      ...prev,
      [`${bvid}-${cid}`]: status,
    }));
  }, [externalVectorUpdate]);

  // 刷新
  const refresh = async () => {
    setMessage(null);
    await loadFolders();
    await loadStatuses();
  };

  // 打开 ASR 弹窗
  const handleASRClick = (bvid: string, cid: number, pageTitle: string, pageIndex: number = 0) => {
    onOpenASR?.(bvid, cid, pageTitle || `P${cid}`, pageIndex);
  };

  const updatePageStatusCache = (bvid: string, cid: number, status: VectorPageStatusResponse) => {
    setPageVectorStatus((prev) => ({
      ...prev,
      [`${bvid}-${cid}`]: status,
    }));
  };

  const refreshPageVectorStatus = async (bvid: string, cid: number) => {
    const refreshed = await vecPageApi.getStatus(bvid, cid);
    updatePageStatusCache(bvid, cid, refreshed);
    return refreshed;
  };

  // 处理视频项点击（展开分P列表 + 按需获取分P数据）
  const handleVideoClick = async (bvid: string) => {
    const isExpanded = expandedVideos.has(bvid);

    // 1. 切换展开状态
    setExpandedVideos((prev) => {
      const next = new Set(prev);
      isExpanded ? next.delete(bvid) : next.add(bvid);
      return next;
    });

    // 2. 未展开且未缓存时请求分P数据
    if (!isExpanded && !pageCache[bvid]) {
      try {
        const data = await knowledgeApi.getVideoPages(bvid);
        setPageCache((prev) => ({ ...prev, [bvid]: data.pages }));

        // 3. 同步批量查询每P向量状态
        const vecStatusMap: Record<string, VectorPageStatusResponse> = {};
        await Promise.all(
          data.pages.map(async (p) => {
            try {
              const status = await vecPageApi.getStatus(bvid, p.cid);
              vecStatusMap[`${bvid}-${p.cid}`] = status;
            } catch {
              // ignore
            }
          })
        );
        setPageVectorStatus((prev) => ({ ...prev, ...vecStatusMap }));
      } catch (e) {
        console.error("[SourcesPanel] 获取分P失败:", e);
      }
    }
  };

  const openOrganizePreview = async (folderId: number) => {
    setOrganizeMessage(null);
    setOrganizePreview(null);
    setOrganizeOpen(true);
    setOrganizeLoading(true);
    try {
      const res = await favoritesApi.organizePreview(folderId, sessionId);
      setOrganizePreview(res);
    } catch (e) {
      setOrganizeMessage("预览失败，请稍后重试");
    } finally {
      setOrganizeLoading(false);
    }
  };

  // 展开收藏夹查看视频
  const toggleExpand = async (id: number) => {
    setFolders((prev) =>
      prev.map((f) => {
        if (f.media_id !== id) return f;
        if (f.expanded) return { ...f, expanded: false };
        if (f.videos) return { ...f, expanded: true };
        return { ...f, expanded: true, loading: true };
      })
    );

    const folder = folders.find((f) => f.media_id === id);
    if (!folder?.videos) {
      try {
        const res = await favoritesApi.getAllVideos(id, sessionId);
        setFolders((prev) =>
          prev.map((f) =>
            f.media_id === id ? { ...f, videos: res.videos, loading: false, media_count: res.total, count_source: "filtered" } : f
          )
        );
      } catch {
        setFolders((prev) =>
          prev.map((f) => (f.media_id === id ? { ...f, loading: false } : f))
        );
      }
    }
  };

  // 选择收藏夹
  const toggleSelect = (id: number) => {
    const s = new Set(selected);
    s.has(id) ? s.delete(id) : s.add(id);
    setSelected(s);
    onSelectionChange?.(Array.from(s));
  };

  // 构建/更新知识库（统一操作）
  const buildKnowledge = async () => {
    if (selected.size === 0) return;
    setBuilding(true);
    setMessage(null);
    setProgress(null);

    try {
      const res = await knowledgeApi.build({ folder_ids: Array.from(selected) }, sessionId);

      const poll = async () => {
        const s = await knowledgeApi.getBuildStatus(res.task_id);
        setProgress(s);

        if (s.status === "running" || s.status === "pending") {
          setTimeout(poll, 1000);
        } else {
          setBuilding(false);
          if (s.status === "completed") {
            setMessage(s.message || "构建完成");
            await loadStatuses();
            onBuildDone?.();
          } else if (s.status === "failed") {
            setMessage(`构建失败: ${s.message}`);
          }
        }
      };
      poll();
    } catch (e) {
      setBuilding(false);
      setMessage("构建失败，请重试");
    }
  };

  // 格式化时间
  const formatTime = (value?: string) => {
    if (!value) return null;
    try {
      let dateStr = value;
      if (!value.includes('T') && !value.includes('Z')) {
        dateStr = value.replace(' ', 'T') + 'Z';
      }
      const date = new Date(dateStr);
      if (Number.isNaN(date.getTime())) return null;

      const month = String(date.getMonth() + 1).padStart(2, '0');
      const day = String(date.getDate()).padStart(2, '0');
      const hour = String(date.getHours()).padStart(2, '0');
      const minute = String(date.getMinutes()).padStart(2, '0');
      return `${month}/${day} ${hour}:${minute}`;
    } catch {
      return null;
    }
  };

  // 获取收藏夹状态
  const getFolderStatus = (mediaId: number, totalInBilibili: number) => {
    const status = statusMap[mediaId];
    const indexedCount = status?.indexed_count ?? 0;
    const lastSync = status?.last_sync_at;
    const folder = folders.find((f) => f.media_id === mediaId);
    const countSource = folder?.count_source ?? "bili";
    let totalCount = totalInBilibili;
    if (countSource === "filtered") {
      totalCount = folder?.media_count ?? totalInBilibili;
    } else if (status?.media_count != null) {
      totalCount = status.media_count;
    }

    // 未入库：从未同步过
    if (!lastSync) {
      return { label: "未入库", className: "empty", indexedCount };
    }

    // 已入库：有同步时间
    if (indexedCount >= totalCount) {
      return { label: "已入库", className: "ok", indexedCount, totalCount };
    }

    // 有更新：B站收藏夹比本地多
    if (indexedCount < totalCount && indexedCount > 0) {
      return { label: "有更新", className: "partial", indexedCount, totalCount };
    }

    // 已入库但视频数为0（可能视频都没有内容）
    return { label: "已入库", className: "ok", indexedCount, totalCount };
  };

  // 向量化状态 Icon
  function VecStatusIcon({ status }: { status: string }) {
    const config = {
      pending: { icon: "○", color: "text-gray-400", label: "未向量化" },
      processing: { icon: "◐", color: "text-yellow-500", label: "向量化中" },
      done: { icon: "●", color: "text-green-500", label: "已向量化" },
      failed: { icon: "✕", color: "text-red-500", label: "向量化失败" },
    };
    const c = config[status as keyof typeof config] || config.pending;
    return <span className={c.color} title={c.label}>{c.icon}</span>;
  }

  // 向量化按钮 handler
  const handleVectorClick = async (bvid: string, cid: number, pageTitle: string) => {
    const pages = pageCache[bvid];
    const pageInfo = pages?.find((p) => p.cid === cid);
    const pageIndex = pageInfo ? pageInfo.page - 1 : 0;

    setVectorMessage(null);
    try {
      const resp = await vecPageApi.create({ bvid, cid, page_index: pageIndex, page_title: pageTitle });
      if (!resp.task_id) {
        setVectorMessage("已是最新向量");
        return;
      }

      // 轮询直到完成
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        const taskStatus = await vecPageApi.getTaskStatus(resp.task_id);
        if (taskStatus.status === "done") {
          setVectorMessage("向量化完成");
          // 刷新状态
          const refreshed = await vecPageApi.getStatus(bvid, cid);
          setPageVectorStatus((prev) => ({
            ...prev,
            [`${bvid}-${cid}`]: refreshed,
          }));
          return;
        }
        if (taskStatus.status === "failed") {
          setVectorMessage(`向量化失败: ${taskStatus.message}`);
          return;
        }
      }
      setVectorMessage("向量化超时");
    } catch {
      setVectorMessage("向量化请求失败");
    }
  };

  // 计算按钮文字
  const handleVectorClickV2 = async (bvid: string, cid: number, pageTitle: string) => {
    const pages = pageCache[bvid];
    const pageInfo = pages?.find((p) => p.cid === cid);
    const pageIndex = pageInfo ? pageInfo.page - 1 : 0;
    const cacheKey = `${bvid}-${cid}`;
    const prevStatus = pageVectorStatus[cacheKey];

    setVectorMessage(null);
    try {
      const resp = await vecPageApi.create({ bvid, cid, page_index: pageIndex, page_title: pageTitle });
      if (!resp.task_id) {
        const refreshed = await refreshPageVectorStatus(bvid, cid);
        setVectorMessage(
          refreshed.is_vectorized === "done"
            ? `已是最新向量 (${refreshed.vector_chunk_count} 块)`
            : "无需重复向量化"
        );
        return;
      }

      updatePageStatusCache(bvid, cid, {
        exists: prevStatus?.exists ?? true,
        bvid,
        cid,
        page_index: prevStatus?.page_index ?? pageIndex,
        page_title: prevStatus?.page_title ?? pageTitle,
        is_processed: prevStatus?.is_processed ?? true,
        content_preview: prevStatus?.content_preview,
        is_vectorized: "processing",
        vectorized_at: prevStatus?.vectorized_at,
        vector_chunk_count: prevStatus?.vector_chunk_count ?? 0,
        vector_error: undefined,
        chroma_exists: prevStatus?.chroma_exists ?? false,
      });
      setVectorMessage("向量化任务已提交");

      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        const taskStatus = await vecPageApi.getTaskStatus(resp.task_id);
        if (taskStatus.status === "done") {
          const refreshed = await refreshPageVectorStatus(bvid, cid);
          setVectorMessage(`向量化完成 (${refreshed.vector_chunk_count} 块)`);
          return;
        }
        if (taskStatus.status === "failed") {
          try {
            await refreshPageVectorStatus(bvid, cid);
          } catch {
            // ignore secondary refresh errors
          }
          setVectorMessage(`向量化失败: ${taskStatus.message}`);
          return;
        }
      }

      try {
        const refreshed = await refreshPageVectorStatus(bvid, cid);
        if (refreshed.is_vectorized === "done") {
          setVectorMessage(`向量化已完成 (${refreshed.vector_chunk_count} 块)，状态已刷新`);
        } else if (refreshed.is_vectorized === "processing") {
          setVectorMessage("向量化仍在后台处理中，请稍后刷新查看");
        } else {
          setVectorMessage("向量化超时，已回刷当前状态");
        }
      } catch {
        setVectorMessage("向量化超时，状态刷新失败");
      }
    } catch {
      try {
        await refreshPageVectorStatus(bvid, cid);
      } catch {
        // ignore secondary refresh errors
      }
      setVectorMessage("向量化请求失败");
    }
  };

  // 工作区：切换分P选中状态
  const toggleWorkspacePage = (bvid: string, cid: number, pageTitle: string, pageIndex: number) => {
    const key = `${bvid}-${cid}`;
    const exists = workspacePages.some((p) => `${p.bvid}-${p.cid}` === key);
    if (exists) {
      onWorkspacePagesChange?.(workspacePages.filter((p) => `${p.bvid}-${p.cid}` !== key));
    } else {
      onWorkspacePagesChange?.([...workspacePages, { bvid, cid, page_index: pageIndex, page_title: pageTitle }]);
    }
  };

  const isInWorkspace = (bvid: string, cid: number) =>
    workspacePages.some((p) => p.bvid === bvid && p.cid === cid);

  const getButtonText = () => {
    if (building) return progress?.current_step || "处理中...";
    if (selected.size === 0) return "选择收藏夹";

    // 检查选中的是否有未入库的
    const hasUnindexed = Array.from(selected).some((id) => {
      const folder = folders.find((f) => f.media_id === id);
      if (!folder) return false;
      return !statusMap[id]?.last_sync_at;
    });

    if (hasUnindexed) {
      return `入库 (${selected.size})`;
    }
    return `更新 (${selected.size})`;
  };

  return (
    <div className="panel-inner">
      <div className="panel-header">
        <div>
          <div className="panel-title">收藏夹</div>
          <div className="panel-subtitle">{folders.length} 个</div>
        </div>
        <div className="panel-actions">
          {workspacePages.length > 0 && (
            <span className="workspace-badge">
              {workspacePages.length} 个分P已选中
              <button
                onClick={() => onWorkspacePagesChange?.([])}
                className="ml-1 text-xs hover:underline"
              >
                清空
              </button>
            </span>
          )}
          <button
            onClick={() => {
              const def = folders.find((f) => f.is_default || f.title === "默认收藏夹");
              if (def) {
                openOrganizePreview(def.media_id);
              } else {
                setOrganizeMessage("未找到默认收藏夹");
              }
            }}
            className="btn btn-ghost"
            disabled={loading || organizeLoading}
          >
            {organizeLoading ? "整理中..." : "快速整理默认收藏夹"}
          </button>
          <button onClick={refresh} className="btn btn-ghost" disabled={loading}>
            {loading ? "加载中..." : "刷新"}
          </button>
        </div>
      </div>

      <div className="panel-body">
        <div className="sources-scroll">
          {/* 工作区管理面板 */}
          {workspacePages.length > 0 && (
            <div className="mb-3 pb-3 border-b border-dashed border-[var(--border)]">
              <div className="text-xs font-semibold text-[var(--muted)] mb-2 uppercase tracking-wider">
                工作区 ({workspacePages.length})
              </div>
              <WorkspacePanel
                workspacePages={workspacePages}
                onRemove={(bvid, cid) => {
                  const key = `${bvid}-${cid}`;
                  onWorkspacePagesChange?.(
                    workspacePages.filter((p) => `${p.bvid}-${p.cid}` !== key)
                  );
                }}
                onClear={() => onWorkspacePagesChange?.([])}
                onOpenVideo={(bvid) => window.open(`https://www.bilibili.com/video/${bvid}`)}
              />
            </div>
          )}
          {loading ? (
            <div className="text-center text-sm text-[var(--muted)] py-6">加载中...</div>
          ) : folders.length === 0 ? (
            <div className="text-center text-sm text-[var(--muted)] py-6">暂无收藏夹</div>
          ) : (
            <div className="space-y-2">
              {folders.map((f) => {
                const status = getFolderStatus(f.media_id, f.media_count);
                const lastSync = formatTime(statusMap[f.media_id]?.last_sync_at);

                return (
                  <div key={f.media_id} className={`folder-card ${selected.has(f.media_id) ? "selected" : ""}`}>
                    <div className="folder-head" onClick={() => toggleExpand(f.media_id)}>
                      <input
                        type="checkbox"
                        checked={selected.has(f.media_id)}
                        onChange={() => toggleSelect(f.media_id)}
                        onClick={(e) => e.stopPropagation()}
                        className="w-4 h-4 accent-[var(--accent)]"
                      />
                      <div className="folder-meta">
                        <div className="folder-title" title={f.title}>{f.title}</div>
                      <div className="folder-count">
                        {status.indexedCount}/{status.totalCount ?? f.media_count} 个视频
                        {lastSync && ` · ${lastSync}`}
                      </div>
                      </div>
                      <span className={`status-pill ${status.className}`}>{status.label}</span>
                      <div className="folder-toggle">
                        <svg className={`w-4 h-4 transition-transform ${f.expanded ? "rotate-90" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                        </svg>
                      </div>
                    </div>

                    {f.expanded && (
                      <div className="folder-list">
                        {f.loading ? (
                          <div className="text-xs text-[var(--muted)]">加载中...</div>
                        ) : f.videos?.length === 0 ? (
                          <div className="text-xs text-[var(--muted)]">暂无视频</div>
                        ) : (
                          f.videos?.map((v) => {
                            const isVideoExpanded = expandedVideos.has(v.bvid);
                            const pages = pageCache[v.bvid];
                            return (
                              <div key={v.bvid}>
                                <div
                                  className="video-item cursor-pointer"
                                  onClick={() => handleVideoClick(v.bvid)}
                                >
                                  <span className="text-[var(--accent)]">
                                    {isVideoExpanded ? "▼" : "▶"}
                                  </span>
                                  <span className="truncate" title={v.title}>{v.title}</span>
                                  {v.page_count && v.page_count > 1 && (
                                    <span className="ml-1 text-xs text-[var(--muted)]">({v.page_count}P)</span>
                                  )}
                                </div>
                                {isVideoExpanded && pages && (
                                  <div className="pl-4 mt-1 space-y-1 overflow-hidden">
                                    {pages.map((p) => {
                                      const vecStatus = pageVectorStatus[`${v.bvid}-${p.cid}`];
                                      return (
                                        <div
                                          key={`${v.bvid}-${p.page}`}
                                          className="page-row"
                                          onClick={() => window.open(`https://www.bilibili.com/video/${v.bvid}?p=${p.page}`)}
                                        >
                                          <span className="text-[var(--accent)]">▶</span>
                                          <span>P{p.page}:</span>
                                          <span className="truncate flex-1">{p.title}</span>

                                          <div className="page-actions">
                                            {/* 工作区勾选 */}
                                            <input
                                              type="checkbox"
                                              checked={isInWorkspace(v.bvid, p.cid)}
                                              onChange={() => toggleWorkspacePage(v.bvid, p.cid, `P${p.page}: ${p.title}`, p.page - 1)}
                                              onClick={(e) => e.stopPropagation()}
                                              className="w-3 h-3 accent-[var(--accent)]"
                                              title="加入工作区"
                                            />

                                            {/* 向量化状态 icon */}
                                            <VecStatusIcon status={vecStatus?.is_vectorized || "pending"} />

                                            {/* ASR 按钮 */}
                                            <button
                                              onClick={(e) => {
                                                e.stopPropagation();
                                                handleASRClick(v.bvid, p.cid, `P${p.page}: ${p.title}`, p.page - 1);
                                              }}
                                              className="page-action-btn"
                                            >
                                              转文字
                                            </button>

                                            {/* 向量化按钮 */}
                                            <button
                                              onClick={(e) => {
                                                e.stopPropagation();
                                                handleVectorClickV2(v.bvid, p.cid, `P${p.page}: ${p.title}`);
                                              }}
                                              disabled={vecStatus?.is_vectorized === "processing"}
                                              title={!vecStatus?.is_processed ? "Auto ASR before vectorization" : ""}
                                              className="page-action-btn"
                                            >
                                              {vecStatus?.is_vectorized === "processing"
                                                ? "向量化中..."
                                                : !vecStatus?.is_processed
                                                ? "ASR+Vector"
                                                : vecStatus?.is_vectorized === "done"
                                                ? "重新向量化"
                                                : "向量化"}
                                            </button>
                                          </div>
                                        </div>
                                      );
                                    })}
                                  </div>
                                )}
                              </div>
                            );
                          })
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <div className="panel-footer">
        {/* 进度条 */}
        {progress && building && (
          <div className="mb-4">
            <div className="flex justify-between text-xs mb-2">
              <span className="text-[var(--muted)] truncate">{progress.current_step}</span>
              <span className="text-[var(--accent)]">{progress.progress}%</span>
            </div>
            <div className="progress">
              <div className="progress-bar" style={{ width: `${progress.progress}%` }} />
            </div>
          </div>
        )}

        {/* 消息 */}
        {message && <div className="text-xs text-[var(--muted)] mb-3">{message}</div>}
        {organizeMessage && <div className="text-xs text-[var(--muted)] mb-3">{organizeMessage}</div>}
        {vectorMessage && <div className="text-xs text-[var(--muted)] mb-3">{vectorMessage}</div>}

        {/* 主按钮 */}
        <button
          onClick={buildKnowledge}
          disabled={selected.size === 0 || building}
          className="btn btn-primary w-full"
        >
          {getButtonText()}
        </button>

        <p className="text-xs text-[var(--muted)] text-center mt-2">
          入库后可在右侧进行问答
        </p>
      </div>

      <OrganizePreviewModal
        open={organizeOpen}
        sessionId={sessionId}
        preview={organizePreview}
        loading={organizeLoading}
        errorMessage={organizeMessage}
        onClose={() => setOrganizeOpen(false)}
        onApplied={refresh}
      />
    </div>
  );
}
