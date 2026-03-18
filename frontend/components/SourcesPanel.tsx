"use client";

import { useState, useEffect, useRef } from "react";
import {
  FavoriteFolder,
  Video,
  favoritesApi,
  knowledgeApi,
  BuildStatus,
  FolderStatus,
  FolderDetailStatus,
  VideoDetailStatus,
  OrganizePreviewResponse,
  ASRStatus,
} from "@/lib/api";
import {
  Card,
  Image,
  Badge,
  Group,
  Text,
  Button,
  ActionIcon,
  ScrollArea,
  Progress,
  Collapse,
  Stack,
  Box,
  Avatar,
  Drawer,
  Checkbox,
} from "@mantine/core";
import {
  IconPlayerPlay,
  IconCheck,
  IconClock,
  IconX,
  IconCircle,
  IconRefresh,
  IconNote,
  IconPencil,
  IconAlertTriangle,
  IconChevronDown,
  IconChevronRight,
  IconFolder,
  IconFolderOpen,
  IconVideo,
  IconCloudDownload,
  IconExternalLink,
} from "@tabler/icons-react";
import OrganizePreviewModal from "@/components/OrganizePreviewModal";
import ExportModal from "@/components/ExportModal";
import VideoSummaryModal from "@/components/VideoSummaryModal";
import ClusteringModal from "@/components/ClusteringModal";
import LearningPathModal from "@/components/LearningPathModal";
import CorrectionModal from "@/components/CorrectionModal";
import { toast } from "sonner";

interface Props {
  sessionId: string;
  onBuildDone?: () => void;
  onSelectionChange?: (folderIds: number[]) => void;
}

export default function SourcesPanel({ sessionId, onBuildDone, onSelectionChange }: Props) {
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
  const [asrStatusMap, setAsrStatusMap] = useState<Record<string, ASRStatus>>({});
  const [exportOpen, setExportOpen] = useState(false);
  const [exportFolderId, setExportFolderId] = useState<number | null>(null);

  // 新功能弹窗状态
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [summaryBvid, setSummaryBvid] = useState<string | null>(null);
  const [clusteringOpen, setClusteringOpen] = useState(false);
  const [clusteringFolderId, setClusteringFolderId] = useState<number | null>(null);
  const [learningPathOpen, setLearningPathOpen] = useState(false);
  const [learningPathFolderId, setLearningPathFolderId] = useState<number | null>(null);
  const [correctionOpen, setCorrectionOpen] = useState(false);

  // 视频列表详情状态
  const [folderDetailStatus, setFolderDetailStatus] = useState<Record<number, FolderDetailStatus>>({});
  const [videoFilter, setVideoFilter] = useState<Record<number, string | null>>({}); // folderId -> filter
  const [retryingFolders, setRetryingFolders] = useState<Set<number>>(new Set());
  
  // 视频多P分组展开状态
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [partsDrawerOpen, setPartsDrawerOpen] = useState(false);
  const [selectedPartsGroup, setSelectedPartsGroup] = useState<{
    title: string;
    origBvid: string;
    parts: any[];
    main: any;
  } | null>(null);

  // 选择性同步状态
  const [videoSelectMode, setVideoSelectMode] = useState(false);
  const [selectedVideos, setSelectedVideos] = useState<Set<string>>(new Set());

  // 点击视频卡片展开视频列表的状态（用于显示系列/分P视频）
  const [expandedFolderVideos, setExpandedFolderVideos] = useState<string | null>(null);
  const [folderVideosCache, setFolderVideosCache] = useState<Record<string, { videos: any[]; mediaId: number }>>({});

  const toggleFolderVideosExpand = async (bvid: string, mediaId: number) => {
    const isExpanded = expandedFolderVideos === bvid;
    // 缓存键用 bvid，因为是根据视频来获取系列/分P列表
    const originalBvid = bvid.split('_p')[0];
    const cacheKey = originalBvid;
    console.log('toggleFolderVideosExpand:', bvid, mediaId, 'isExpanded:', isExpanded, 'cacheKey:', cacheKey);

    if (!isExpanded && !folderVideosCache[cacheKey]) {
      console.log('Requesting series videos for bvid:', originalBvid);
      // 展开时根据bvid请求该视频所属系列的所有视频
      try {
        const res = await favoritesApi.getSeriesVideos(originalBvid, sessionId);
        console.log('Got series videos:', res.videos?.length);
        setFolderVideosCache(prev => ({
          ...prev,
          [cacheKey]: { videos: res.videos, mediaId }
        }));
      } catch (e) {
        console.error("Failed to load series videos:", e);
      }
    }

    setExpandedFolderVideos(prev => prev === bvid ? null : bvid);
  };

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

  // 加载视频 ASR 状态
  const loadASRStatuses = async (bvids: string[]) => {
    if (bvids.length === 0) return;
    try {
      const newStatuses: Record<string, ASRStatus> = {};
      await Promise.all(
        bvids.map(async (bvid) => {
          try {
            const status = await knowledgeApi.getASRStatus(bvid);
            newStatuses[bvid] = status;
          } catch {
            // 忽略单个视频加载失败
          }
        })
      );
      setAsrStatusMap((prev) => ({ ...prev, ...newStatuses }));
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadFolders().then(loadStatuses);
  }, [sessionId]);

  // 刷新
  const refresh = async () => {
    setMessage(null);
    await loadFolders();
    await loadStatuses();
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
    const folder = folders.find((f) => f.media_id === id);
    const isExpanding = !folder?.expanded;
    console.log('toggleExpand:', id, 'isExpanding:', isExpanding, 'hasVideos:', !!folder?.videos);

    setFolders((prev) =>
      prev.map((f) => {
        if (f.media_id !== id) return f;
        if (f.expanded) return { ...f, expanded: false };
        return { ...f, expanded: true, loading: true };
      })
    );

    // 展开时加载视频列表（从 B 站）
    if (isExpanding) {
      console.log('Requesting videos from Bilibili for folder:', id);
      // 如果没有视频数据，则请求
      if (!folder?.videos) {
        try {
          console.log('Calling favoritesApi.getAllVideos...');
          const res = await favoritesApi.getAllVideos(id, sessionId);
          console.log('Got videos:', res.videos?.length);
          setFolders((prev) =>
            prev.map((f) =>
              f.media_id === id ? { ...f, videos: res.videos, loading: false, media_count: res.total, count_source: "filtered" } : f
            )
          );
          // 加载 ASR 状态
          const bvids = res.videos.map((v: Video) => v.bvid);
          loadASRStatuses(bvids);
        } catch (e) {
          console.error('Failed to load videos:', e);
          setFolders((prev) =>
            prev.map((f) => (f.media_id === id ? { ...f, loading: false } : f))
          );
        }
      } else {
        // 已有视频数据，只需要关闭 loading
        console.log('Videos already loaded, just closing loading');
        setFolders((prev) =>
          prev.map((f) => (f.media_id === id ? { ...f, loading: false } : f))
        );
      }
    }

    // 同时加载向量化进度状态
    if (isExpanding) {
      try {
        const detailStatus = await knowledgeApi.getFolderDetailStatus(id, sessionId, { page_size: 50 });
        setFolderDetailStatus((prev) => ({ ...prev, [id]: detailStatus }));
      } catch (e) {
        console.error("Failed to load folder detail status:", e);
      }
    }
  };

  // 选择收藏夹（状态变化通过 useEffect 传递给父组件，避免在渲染期间更新）
  const toggleSelect = (id: number) => {
    setSelected(prev => {
      const s = new Set(prev);
      if (s.has(id)) {
        s.delete(id);
      } else {
        s.add(id);
      }
      // 不在这里调用 onSelectionChange，避免在渲染期间更新父组件
      // 状态变化会通过 useEffect 传递给父组件
      return s;
    });
  };

  // 同步 selected 到父组件（使用 ref 避免循环）
  const prevSelectedRef = useRef<number[]>([]);
  useEffect(() => {
    const current = Array.from(selected);
    if (JSON.stringify(current) !== JSON.stringify(prevSelectedRef.current)) {
      prevSelectedRef.current = current;
      onSelectionChange?.(current);
    }
  }, [selected, onSelectionChange]);

  // 构建/更新知识库（统一操作）
  const buildKnowledge = async () => {
    if (selected.size === 0) return;
    setBuilding(true);
    setMessage(null);
    setProgress(null);

    try {
      // 如果有选中的视频，使用 include_bvids；否则同步全部
      const buildData: any = { folder_ids: Array.from(selected) };
      if (selectedVideos.size > 0) {
        buildData.include_bvids = Array.from(selectedVideos);
      }

      const res = await knowledgeApi.build(buildData, sessionId);

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

  // 获取视频 ASR 状态显示
  const getASRStatusDisplay = (bvid: string) => {
    const status = asrStatusMap[bvid];
    if (!status) {
      return { icon: "○", label: "未入库", className: "text-[var(--muted)]" };
    }

    switch (status.asr_status) {
      case "not_indexed":
        return { icon: "○", label: "未入库", className: "text-[var(--muted)]" };
      case "pending":
        return { icon: "○", label: "待处理", className: "text-[var(--muted)]" };
      case "processing":
        return { icon: "◐", label: "处理中", className: "text-yellow-500" };
      case "completed":
        return { icon: "✓", label: "已完成", className: "text-green-500" };
      case "failed":
        return { icon: "✗", label: "失败", className: "text-red-500" };
      default:
        return { icon: "○", label: "未入库", className: "text-[var(--muted)]" };
    }
  };

  // 获取质量评分标签
  const getQualityLabel = (score?: number) => {
    if (score === undefined || score === null) return null;
    if (score >= 0.8) return { label: "优", className: "bg-green-500/20 text-green-400" };
    if (score >= 0.6) return { label: "良", className: "bg-blue-500/20 text-blue-400" };
    if (score >= 0.4) return { label: "中", className: "bg-yellow-500/20 text-yellow-400" };
    return { label: "差", className: "bg-red-500/20 text-red-400" };
  };

  // 获取向量化状态显示
  const getProcessingStatusDisplay = (status?: string) => {
    switch (status) {
      case "completed":
        return { icon: "✓", label: "已完成", className: "text-green-500" };
      case "processing":
        return { icon: "◐", label: "处理中", className: "text-blue-400" };
      case "failed":
        return { icon: "✗", label: "失败", className: "text-red-500" };
      case "pending":
      default:
        return { icon: "○", label: "待处理", className: "text-[var(--muted)]" };
    }
  };

  // 批量重试失败视频
  const handleRetryFailed = async (mediaId: number) => {
    setRetryingFolders((prev) => new Set(prev).add(mediaId));
    try {
      const res = await knowledgeApi.retryFailedVideos({ folder_ids: [mediaId] }, sessionId);
      toast.success(res.message);
      // 刷新详细状态
      const detailStatus = await knowledgeApi.getFolderDetailStatus(mediaId, sessionId, { page_size: 50 });
      setFolderDetailStatus((prev) => ({ ...prev, [mediaId]: detailStatus }));
    } catch (e) {
      console.error(e);
      toast.error("重试失败");
    } finally {
      setRetryingFolders((prev) => {
        const next = new Set(prev);
        next.delete(mediaId);
        return next;
      });
    }
  };

  // 加载更多视频
  const loadMoreVideos = async (mediaId: number, page: number) => {
    const currentFilter = videoFilter[mediaId] || undefined;
    const detail = folderDetailStatus[mediaId];
    if (!detail || !detail.has_more) return;

    try {
      const newDetail = await knowledgeApi.getFolderDetailStatus(mediaId, sessionId, {
        status_filter: currentFilter,
        page: page + 1,
        page_size: 20,
      });
      setFolderDetailStatus((prev) => ({
        ...prev,
        [mediaId]: {
          ...newDetail,
          videos: [...(prev[mediaId]?.videos || []), ...newDetail.videos],
        },
      }));
    } catch (e) {
      console.error(e);
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

  // 计算按钮文字
  const getButtonText = () => {
    if (building) return progress?.current_step || "处理中...";
    if (selected.size === 0) return "选择收藏夹";

    // 如果有选中的视频，显示选中数量
    const videoCountText = selectedVideos.size > 0 ? ` (${selectedVideos.size}个视频)` : "";

    // 检查选中的是否有未入库的
    const hasUnindexed = Array.from(selected).some((id) => {
      const folder = folders.find((f) => f.media_id === id);
      if (!folder) return false;
      return !statusMap[id]?.last_sync_at;
    });

    if (hasUnindexed) {
      return `入库${videoCountText} (${selected.size})`;
    }
    return `更新${videoCountText} (${selected.size})`;
  };

  return (
    <div className="panel-inner">
      <div className="panel-header">
        <div>
          <div className="panel-title">收藏夹</div>
          <div className="panel-subtitle">{folders.length} 个</div>
        </div>
        <div className="panel-actions">
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
          {/* 导出按钮 - 常驻显示，只有勾选了才能导出 */}
          <button
            onClick={() => {
              const folderId = Array.from(selected)[0];
              setExportFolderId(folderId);
              setExportOpen(true);
            }}
            className="btn btn-ghost"
            disabled={selected.size === 0 || loading}
            title={selected.size === 0 ? "请先选择一个收藏夹" : "导出选中收藏夹"}
          >
            导出
          </button>
          {/* 主题聚类按钮 */}
          <button
            onClick={() => {
              const folderId = Array.from(selected)[0];
              setClusteringFolderId(folderId);
              setClusteringOpen(true);
            }}
            className="btn btn-ghost"
            disabled={selected.size !== 1 || loading}
            title={selected.size !== 1 ? "请先选择一个收藏夹" : "主题聚类"}
          >
            聚类
          </button>
          {/* 学习路径按钮 */}
          <button
            onClick={() => {
              const folderId = Array.from(selected)[0];
              setLearningPathFolderId(folderId);
              setLearningPathOpen(true);
            }}
            className="btn btn-ghost"
            disabled={selected.size !== 1 || loading}
            title={selected.size !== 1 ? "请先选择一个收藏夹" : "学习路径"}
          >
            路径
          </button>
          {/* 内容修正按钮 */}
          <button
            onClick={() => {
              setCorrectionOpen(true);
            }}
            className="btn btn-ghost"
            disabled={loading}
            title="内容修正"
          >
            修正
          </button>
          <button onClick={refresh} className="btn btn-ghost" disabled={loading}>
            {loading ? "加载中..." : "刷新"}
          </button>
        </div>
      </div>

      <div className="panel-body">
        <div className="sources-scroll">
          {loading ? (
            <div className="text-center text-sm py-6" style={{ color: 'var(--text-tertiary)' }}>加载中...</div>
          ) : folders.length === 0 ? (
            <div className="text-center text-sm py-6" style={{ color: 'var(--text-tertiary)' }}>暂无收藏夹</div>
          ) : (
            <div className="space-y-2">
              {folders.map((f) => {
                const status = getFolderStatus(f.media_id, f.media_count);
                const lastSync = formatTime(statusMap[f.media_id]?.last_sync_at);

                return (
                  <div key={f.media_id} className={`folder-card ${selected.has(f.media_id) ? "selected" : ""}`}>
                    <input
                      type="checkbox"
                      checked={selected.has(f.media_id)}
                      onChange={(e) => {
                        e.stopPropagation();
                        toggleSelect(f.media_id);
                      }}
                      onClick={(e) => e.stopPropagation()}
                      className="folder-checkbox-btn"
                    />
                    <div className="folder-head" onClick={() => { console.log('toggleExpand clicked:', f.media_id); toggleExpand(f.media_id); }}>
                      <div className="folder-meta">
                        <div className="folder-title" title={f.title}>{f.title}</div>
                        <div className="folder-count">
                          {status.indexedCount}/{status.totalCount ?? f.media_count} 个视频
                          {lastSync && ` · ${lastSync}`}
                        </div>
                        {/* 向量化进度条 */}
                        {(() => {
                          const folderStatus = statusMap[f.media_id];
                          return folderStatus?.progress !== undefined && folderStatus.progress < 100 && (
                            <div className="folder-progress">
                              <div className="progress-bar">
                                <div
                                  className="progress-fill"
                                  style={{ width: `${folderStatus.progress || 0}%` }}
                                />
                              </div>
                              <span className="progress-text">
                                {folderStatus.stats?.completed || 0}/{status.totalCount ?? f.media_count}
                              </span>
                            </div>
                          );
                        })()}
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
                          <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>加载中...</div>
                        ) : f.videos?.length === 0 ? (
                          <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>暂无视频</div>
                        ) : (
                          <>
                            {/* 向量化状态统计和筛选 */}
                            {(() => {
                              const detail = folderDetailStatus[f.media_id];
                              const stats = detail?.stats;
                              const currentFilter = videoFilter[f.media_id];
                              const failedCount = stats?.failed || 0;

                              return (
                                <>
                                  {/* 列表头部：统计 + 筛选 */}
                                  {stats && (
                                    <Card padding="sm" radius="md" withBorder mb="sm">
                                      <Group justify="space-between" wrap="wrap" gap="xs">
                                        <Group gap="md">
                                          <Badge color="green" variant="light" leftSection={<IconCheck size={12} />}>
                                            已完成 {stats.completed || 0}
                                          </Badge>
                                          <Badge color="blue" variant="light" leftSection={<IconClock size={12} />}>
                                            处理中 {stats.processing || 0}
                                          </Badge>
                                          <Badge color="red" variant="light" leftSection={<IconX size={12} />}>
                                            失败 {stats.failed || 0}
                                          </Badge>
                                          <Badge color="gray" variant="light" leftSection={<IconCircle size={12} />}>
                                            待处理 {stats.pending || 0}
                                          </Badge>
                                        </Group>
                                        {failedCount > 0 && (
                                          <Button
                                            size="xs"
                                            variant="light"
                                            color="red"
                                            leftSection={<IconRefresh size={14} />}
                                            loading={retryingFolders.has(f.media_id)}
                                            onClick={() => handleRetryFailed(f.media_id)}
                                          >
                                            重新处理 ({failedCount})
                                          </Button>
                                        )}
                                      </Group>
                                    </Card>
                                  )}

                                  {/* 筛选按钮 */}
                                  {stats && (
                                    <Group gap="xs" mb="sm">
                                      {[
                                        { key: null, label: "全部", count: detail?.total || 0, color: "gray" },
                                        { key: "completed", label: "已完成", count: stats.completed || 0, color: "green" },
                                        { key: "processing", label: "处理中", count: stats.processing || 0, color: "blue" },
                                        { key: "failed", label: "失败", count: stats.failed || 0, color: "red" },
                                        { key: "pending", label: "待处理", count: stats.pending || 0, color: "gray" },
                                      ].map((item) => (
                                        <Button
                                          key={item.key || "all"}
                                          size="xs"
                                          variant={currentFilter === item.key ? "filled" : "light"}
                                          color={item.color}
                                          onClick={async () => {
                                            setVideoFilter((prev) => ({ ...prev, [f.media_id]: item.key }));
                                            try {
                                              const newDetail = await knowledgeApi.getFolderDetailStatus(
                                                f.media_id,
                                                sessionId,
                                                { status_filter: item.key || undefined, page_size: 20 }
                                              );
                                              setFolderDetailStatus((prev) => ({ ...prev, [f.media_id]: newDetail }));
                                            } catch (e) {
                                              console.error(e);
                                            }
                                          }}
                                        >
                                          {item.label} ({item.count})
                                        </Button>
                                      ))}
                                    </Group>
                                  )}

                                  {/* 视频列表 - 使用 Mantine Card */}
                                  <ScrollArea h={400} offsetScrollbars>
                                    <Stack gap="sm">
                                      {(() => {
                                        // 优先使用 B 站视频列表（f.videos），其次使用知识库数据（detail?.videos）
                                        const flatVideos = (f.videos || detail?.videos) || [];
                                        
                                        // 辅助渲染方法
                                        const currentMediaId = f.media_id;
                                        const renderVideoCard = (v: any, videoDetail: any, isChild = false, parentGroup?: any, mediaId?: number) => {
                                          const processingStatus = videoDetail?.processing_status;
                                          const asrData = asrStatusMap[v.bvid];
                                          const coverUrl = v.cover || videoDetail?.cover || `https://pic1.bimg.qq.top/kv?url=https://i0.hdslb.com/bfs/archive/${v.original_bvid || v.bvid.split('_p')[0]}.jpg`;
                                          const author = v.owner || videoDetail?.owner || '';
                                          const duration = v.duration || videoDetail?.duration;
                                          const durationStr = duration ? `${Math.floor(duration / 60)}:${String(duration % 60).padStart(2, '0')}` : '';

                                          const statusColor = processingStatus === 'completed' ? 'green' :
                                            processingStatus === 'processing' ? 'blue' :
                                            processingStatus === 'failed' ? 'red' : 'gray';
                                          const statusIcon = processingStatus === 'completed' ? <IconCheck size={12} /> :
                                            processingStatus === 'processing' ? <IconClock size={12} /> :
                                            processingStatus === 'failed' ? <IconX size={12} /> : <IconCircle size={12} />;
                                          const statusLabel = processingStatus === 'completed' ? '已完成' :
                                            processingStatus === 'processing' ? '处理中' :
                                            processingStatus === 'failed' ? '失败' : '待处理';

                                          return (
                                            <Card
                                              key={v.bvid}
                                              padding="sm"
                                              radius="md"
                                              withBorder
                                              style={{ 
                                                cursor: parentGroup ? "pointer" : "default", 
                                                transition: "transform 0.2s ease",
                                                marginLeft: isChild ? "1.5rem" : "0",
                                                borderLeft: isChild ? "2px solid var(--mantine-color-blue-filled)" : undefined
                                              }}
                                              onMouseEnter={(e) => {
                                                if (!parentGroup) e.currentTarget.style.transform = "translateX(4px)";
                                              }}
                                              onMouseLeave={(e) => Object.assign(e.currentTarget.style, { transform: "translateX(0)" })}
                                              onClick={() => {
                                                if (parentGroup) {
                                                  // 打开 Drawer 展示所有分P
                                                  setSelectedPartsGroup({
                                                    title: parentGroup.main?.title || parentGroup.parts[0]?.title || '',
                                                    origBvid: parentGroup.origBvid,
                                                    parts: parentGroup.parts,
                                                    main: parentGroup.main,
                                                  });
                                                  setPartsDrawerOpen(true);
                                                }
                                              }}
                                            >
                                              <Group align="flex-start" wrap="nowrap" gap="sm">
                                                {videoSelectMode && (
                                                  <Checkbox
                                                    checked={selectedVideos.has(v.bvid)}
                                                    onChange={(e) => {
                                                      e.stopPropagation();
                                                      setSelectedVideos(prev => {
                                                        const next = new Set(prev);
                                                        if (next.has(v.bvid)) {
                                                          next.delete(v.bvid);
                                                        } else {
                                                          next.add(v.bvid);
                                                        }
                                                        return next;
                                                      });
                                                    }}
                                                    onClick={(e) => e.stopPropagation()}
                                                  />
                                                )}
                                                <Box w={120} h={68} style={{ flexShrink: 0 }}>
                                                  <Image
                                                    src={coverUrl}
                                                    alt={v.title}
                                                    h={68}
                                                    fit="cover"
                                                    radius="sm"
                                                    fallbackSrc="https://placehold.co/120x68?text=Video"
                                                  />
                                                </Box>

                                                <Stack gap={4} style={{ flex: 1, minWidth: 0 }}>
                                                  <Text size="sm" fw={500} lineClamp={1} title={v.title}>
                                                    {v.title}
                                                  </Text>
                                                  <Group gap="xs">
                                                    {author && (
                                                      <Text size="xs" c="dimmed" lineClamp={1}>
                                                        {author}
                                                      </Text>
                                                    )}
                                                    {durationStr && (
                                                      <Text size="xs" c="dimmed">
                                                        {durationStr}
                                                      </Text>
                                                    )}
                                                  </Group>
                                                </Stack>

                                                {!parentGroup && (
                                                  <Badge
                                                    color={statusColor}
                                                    variant="light"
                                                    leftSection={statusIcon}
                                                    style={{ flexShrink: 0 }}
                                                    title={processingStatus === "failed" ? videoDetail?.processing_error || "处理失败" : undefined}
                                                  >
                                                    {statusLabel}
                                                  </Badge>
                                                )}

                                                <Group gap={4} style={{ flexShrink: 0 }} onClick={(e) => e.stopPropagation()}>
                                                    {!parentGroup && (
                                                        <>
                                                            {asrData?.asr_quality_flags && asrData.asr_quality_flags.length > 0 && (
                                                              <ActionIcon
                                                                variant="subtle"
                                                                color="yellow"
                                                                size="sm"
                                                                title={`问题: ${asrData.asr_quality_flags.join(", ")}`}
                                                              >
                                                                <IconAlertTriangle size={14} />
                                                              </ActionIcon>
                                                            )}
                                                            <ActionIcon
                                                              variant="subtle"
                                                              color="blue"
                                                              size="sm"
                                                              title="查看摘要"
                                                              onClick={() => {
                                                                setSummaryBvid(v.bvid);
                                                                setSummaryOpen(true);
                                                              }}
                                                            >
                                                              <IconNote size={14} />
                                                            </ActionIcon>
                                                            <ActionIcon
                                                              variant="subtle"
                                                              color="grape"
                                                              size="sm"
                                                              title="修正内容"
                                                              onClick={() => {
                                                                setSummaryBvid(v.bvid);
                                                                setCorrectionOpen(true);
                                                              }}
                                                            >
                                                              <IconPencil size={14} />
                                                            </ActionIcon>
                                                            <ActionIcon
                                                              variant="subtle"
                                                              color="teal"
                                                              size="sm"
                                                              title="展开视频列表"
                                                              onClick={() => toggleFolderVideosExpand(v.bvid, currentMediaId)}
                                                            >
                                                              {expandedFolderVideos === v.bvid ? <IconChevronDown size={14} /> : <IconChevronRight size={14} />}
                                                            </ActionIcon>
                                                            <ActionIcon
                                                              variant="subtle"
                                                              color="orange"
                                                              size="sm"
                                                              title="在B站观看"
                                                              component="a"
                                                              href={`https://www.bilibili.com/video/${v.original_bvid || v.bvid.split('_p')[0]}${v.bvid.includes('_p') ? '?p=' + v.bvid.split('_p')[1] : ''}`}
                                                              target="_blank"
                                                            >
                                                              <IconExternalLink size={14} />
                                                            </ActionIcon>
                                                        </>
                                                    )}
                                                </Group>
                                              </Group>
                                            </Card>
                                          );
                                        };

                                        // 对带有 _p 的视频进行聚合
                                        const groupedVideos: Record<string, { main: any; parts: any[] }> = {};

                                        flatVideos.forEach(v => {
                                            const videoDetail = detail?.videos?.find((vd: any) => vd.bvid === v.bvid);
                                            const isPart = v.bvid.includes("_p");
                                            const orig = isPart ? v.bvid.split("_p")[0] : v.bvid;
                                            
                                            if (!groupedVideos[orig]) {
                                                groupedVideos[orig] = { main: null, parts: [] };
                                            }
                                            
                                            if (isPart) {
                                                groupedVideos[orig].parts.push({ ...v, detail: videoDetail });
                                            } else {
                                                groupedVideos[orig].main = { ...v, detail: videoDetail };
                                            }
                                        });

                                        const displayList = Object.keys(groupedVideos).map(origBvid => {
                                            const group = groupedVideos[origBvid];
                                            if (group.main && group.parts.length === 0) {
                                                return { type: 'single', origBvid, data: group.main };
                                            } else if (!group.main && group.parts.length > 0) {
                                                // 如果只有部分，没有 main，构造一个虚拟的 main
                                                const first = group.parts[0];
                                                // 优先使用 detail.videos[0].title（系列标题），其次使用第一个部分的标题
                                                const seriesTitle = detail?.videos?.[0]?.title;
                                                const virtualMain = {
                                                    ...first,
                                                    bvid: origBvid,
                                                    title: seriesTitle || first.title.replace(/\[\d+\/\d+\]\s*/, '').split(' - ')[0] || first.title,
                                                    isVirtual: true,
                                                };
                                                return { type: 'group', origBvid, main: virtualMain, parts: group.parts };
                                            } else {
                                                return { type: 'group', origBvid, main: group.main, parts: group.parts };
                                            }
                                        });

                                        return displayList.map((item, idx) => {
                                          if (item.type === 'single') {
                                              const bvid = item.data.bvid;
                                              const isExpanded = expandedFolderVideos === bvid;
                                              // 缓存键与 toggleFolderVideosExpand 保持一致，使用 originalBvid
                                              const originalBvid = bvid.split('_p')[0];
                                              const cacheKey = originalBvid;
                                              const allVideos = folderVideosCache[cacheKey]?.videos || [];

                                              return (
                                                <Stack gap="xs" key={bvid}>
                                                  {renderVideoCard(item.data, item.data.detail)}
                                                  <Collapse in={isExpanded}>
                                                    <Stack gap="xs" pl="md" style={{ borderLeft: '2px solid var(--mantine-color-teal-light)' }}>
                                                      {(() => {
                                                        // 显示该视频的分P列表
                                                        console.log('Rendering video parts for:', bvid, 'total parts:', allVideos.length);
                                                        if (allVideos.length === 0) {
                                                          return (
                                                            <Text size="xs" c="dimmed" ta="center" py="xs">
                                                              暂无分P信息
                                                            </Text>
                                                          );
                                                        }
                                                        return allVideos.map((v: any) => (
                                                          <Card key={v.bvid} padding="xs" radius="sm" withBorder>
                                                            <Group gap="xs" wrap="nowrap">
                                                              <Text size="xs" lineClamp={1} style={{ flex: 1 }} title={v.title}>{v.title}</Text>
                                                              <Text size="xs" c="dimmed">{v.owner || ''}</Text>
                                                              <ActionIcon
                                                                variant="subtle"
                                                                color="orange"
                                                                size="xs"
                                                                title="在B站观看"
                                                                component="a"
                                                                href={`https://www.bilibili.com/video/${v.original_bvid || originalBvid}${v.page ? '?p=' + v.page : ''}`}
                                                                target="_blank"
                                                              >
                                                                <IconExternalLink size={12} />
                                                              </ActionIcon>
                                                            </Group>
                                                          </Card>
                                                        ));
                                                      })()}
                                                    </Stack>
                                                  </Collapse>
                                                </Stack>
                                              );
                                          } else {
                                              const mainObj = item.main;
                                              const parts = item.parts;
                                              // mainObj 的渲染，传入 parentGroup 作为交互挂载点
                                              return (
                                                <Stack gap="xs" key={item.origBvid}>
                                                    {renderVideoCard(mainObj, mainObj.detail, false, item)}
                                                    <Collapse in={expandedGroups.has(item.origBvid!)}>
                                                        <Stack gap="xs">
                                                            {(parts || []).map(p => renderVideoCard(p, p.detail, true))}
                                                        </Stack>
                                                    </Collapse>
                                                </Stack>
                                              );
                                          }
                                        });
                                      })()}
                                    </Stack>
                                  </ScrollArea>

                                  {/* 加载更多 */}
                                  {detail?.has_more && (
                                    <Button
                                      fullWidth
                                      variant="light"
                                      mt="sm"
                                      onClick={() => loadMoreVideos(f.media_id, detail.page)}
                                    >
                                      加载更多...
                                    </Button>
                                  )}
                                </>
                              );
                            })()}
                          </>
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
              <span className="truncate" style={{ color: 'var(--text-tertiary)' }}>{progress.current_step}</span>
              <span style={{ color: 'var(--accent)' }}>{progress.progress}%</span>
            </div>
            <div className="progress">
              <div className="progress-bar" style={{ width: `${progress.progress}%` }} />
            </div>
          </div>
        )}

        {/* 消息 */}
        {message && <div className="text-xs mb-3" style={{ color: 'var(--text-tertiary)' }}>{message}</div>}
        {organizeMessage && <div className="text-xs mb-3" style={{ color: 'var(--text-tertiary)' }}>{organizeMessage}</div>}

        {/* 选择视频模式按钮 */}
        <div className="flex gap-2 mb-3">
          <Button
            variant={videoSelectMode ? "filled" : "light"}
            color={videoSelectMode ? "blue" : "gray"}
            size="xs"
            fullWidth
            onClick={() => {
              setVideoSelectMode(!videoSelectMode);
              if (videoSelectMode) {
                setSelectedVideos(new Set());
              }
            }}
          >
            {videoSelectMode ? "取消选择" : "选择视频"}
          </Button>
          {videoSelectMode && selectedVideos.size > 0 && (
            <Button
              variant="light"
              color="red"
              size="xs"
              onClick={() => setSelectedVideos(new Set())}
            >
              清空 ({selectedVideos.size})
            </Button>
          )}
        </div>

        {/* 主按钮 */}
        <button
          onClick={buildKnowledge}
          disabled={selected.size === 0 || building}
          className="btn btn-primary w-full"
        >
          {getButtonText()}
        </button>

        <p className="text-xs text-center mt-2" style={{ color: 'var(--text-tertiary)' }}>
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

      {/* 导出弹窗 */}
      <ExportModal
        isOpen={exportOpen}
        onClose={() => setExportOpen(false)}
        type="folder"
        folderIds={Array.from(selected)}
      />

      {/* 视频摘要弹窗 */}
      <VideoSummaryModal
        isOpen={summaryOpen}
        onClose={() => {
          setSummaryOpen(false);
          setSummaryBvid(null);
        }}
        bvid={summaryBvid || ""}
      />

      {/* 主题聚类弹窗 */}
      <ClusteringModal
        isOpen={clusteringOpen}
        onClose={() => {
          setClusteringOpen(false);
          setClusteringFolderId(null);
        }}
        folderId={clusteringFolderId || 0}
        sessionId={sessionId}
      />

      {/* 学习路径弹窗 */}
      <LearningPathModal
        isOpen={learningPathOpen}
        onClose={() => {
          setLearningPathOpen(false);
          setLearningPathFolderId(null);
        }}
        folderId={learningPathFolderId || 0}
        sessionId={sessionId}
      />

      {/* 内容修正弹窗 */}
      <CorrectionModal
        isOpen={correctionOpen}
        onClose={() => setCorrectionOpen(false)}
        userSessionId={sessionId}
      />

      {/* 分P视频目录 Drawer */}
      <Drawer
        opened={partsDrawerOpen}
        onClose={() => setPartsDrawerOpen(false)}
        title={selectedPartsGroup?.title || "分P视频列表"}
        position="right"
        size="md"
      >
        {selectedPartsGroup && (
          <Stack gap="sm">
            <Text size="sm" c="dimmed">
              共 {selectedPartsGroup.parts.length} 个视频
            </Text>
            <ScrollArea h={window.innerHeight - 150}>
              <Stack gap="xs">
                {selectedPartsGroup.parts.map((part: any, index: number) => {
                  const videoDetail = part.detail;
                  const coverUrl = part.cover || videoDetail?.cover || `https://pic1.bimg.qq.top/kv?url=https://i0.hdslb.com/bfs/archive/${part.original_bvid || part.bvid.split('_p')[0]}.jpg`;
                  const duration = part.duration || videoDetail?.duration;
                  const durationStr = duration ? `${Math.floor(duration / 60)}:${String(duration % 60).padStart(2, '0')}` : '';
                  const processingStatus = videoDetail?.processing_status;

                  return (
                    <Card
                      key={part.bvid}
                      padding="sm"
                      radius="md"
                      withBorder
                      style={{ cursor: "pointer", transition: "transform 0.2s ease" }}
                      onMouseEnter={(e) => e.currentTarget.style.transform = "translateX(4px)"}
                      onMouseLeave={(e) => Object.assign(e.currentTarget.style, { transform: "translateX(0)" })}
                      onClick={() => {
                        setSummaryBvid(part.bvid);
                        setSummaryOpen(true);
                        setPartsDrawerOpen(false);
                      }}
                    >
                      <Group align="flex-start" wrap="nowrap" gap="sm">
                        <Box w={80} h={45} style={{ flexShrink: 0, position: "relative" }}>
                          <Image
                            src={coverUrl}
                            alt={part.title}
                            h={45}
                            fit="cover"
                            radius="sm"
                            fallbackSrc="https://placehold.co/80x45?text=P"
                          />
                          <Badge
                            size="xs"
                            style={{ position: "absolute", bottom: 4, right: 4, background: "rgba(0,0,0,0.7)", color: "white" }}
                          >
                            P{index + 1}
                          </Badge>
                        </Box>

                        <Stack gap={2} style={{ flex: 1, minWidth: 0 }}>
                          <Text size="xs" fw={500} lineClamp={2} title={part.title}>
                            {part.title}
                          </Text>
                          <Group gap="xs">
                            {durationStr && (
                              <Text size="xs" c="dimmed">
                                {durationStr}
                              </Text>
                            )}
                            {processingStatus && (
                              <Badge
                                size="xs"
                                color={processingStatus === 'completed' ? 'green' : processingStatus === 'processing' ? 'blue' : processingStatus === 'failed' ? 'red' : 'gray'}
                                variant="light"
                              >
                                {processingStatus === 'completed' ? '已完成' : processingStatus === 'processing' ? '处理中' : processingStatus === 'failed' ? '失败' : '待处理'}
                              </Badge>
                            )}
                          </Group>
                        </Stack>

                        <ActionIcon variant="subtle" color="blue" size="sm" title="查看摘要">
                          <IconNote size={14} />
                        </ActionIcon>
                      </Group>
                    </Card>
                  );
                })}
              </Stack>
            </ScrollArea>
          </Stack>
        )}
      </Drawer>
    </div>
  );
}
