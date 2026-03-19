/**
 * 导出预览弹窗 - 使用 Mantine UI
 */

"use client";

import { useState, useEffect } from "react";
import { toast } from "sonner";
import {
    Modal,
    Button,
    Group,
    Text,
    Title,
    Badge,
    Card,
    Stack,
    Loader,
    ScrollArea,
    Divider,
    Box,
    ThemeIcon,
    SegmentedControl,
} from "@mantine/core";
import { IconDownload, IconCopy, IconRefresh, IconFileText, IconAlertCircle } from "@tabler/icons-react";
import {
    exportVideo,
    exportFolder,
    exportSession,
    getSessionSummary,
    refreshSessionSummary,
    downloadMarkdown,
    copyToClipboard,
    ExportResponse,
    SessionSummaryResponse,
} from "@/lib/export";

interface ExportModalProps {
    isOpen: boolean;
    onClose: () => void;
    type: "video" | "folder" | "session" | "session-summary";
    bvid?: string;
    folderId?: number;
    folderIds?: number[];
    chatSessionId?: string;
}

export default function ExportModal({
    isOpen,
    onClose,
    type,
    bvid,
    folderId,
    folderIds,
    chatSessionId,
}: ExportModalProps) {
    const [loading, setLoading] = useState(false);
    const [refreshing, setRefreshing] = useState(false);
    const [exportData, setExportData] = useState<ExportResponse | null>(null);
    const [summaryData, setSummaryData] = useState<SessionSummaryResponse["data"] | null>(null);
    const [hasCache, setHasCache] = useState(false);
    const [format, setFormat] = useState<"full" | "simple">("full");
    const [error, setError] = useState<string | null>(null);

    // 加载导出数据
    useEffect(() => {
        if (!isOpen) return;

        const loadData = async () => {
            setLoading(true);
            setError(null);
            setExportData(null);
            setSummaryData(null);

            try {
                if (type === "video" && bvid) {
                    const data = await exportVideo(bvid, format);
                    setExportData(data);
                } else if (type === "folder" && (folderId || folderIds)) {
                    const ids = folderIds || (folderId ? [folderId] : []);
                    const data = await exportFolder(ids, format);
                    setExportData(data);
                } else if (type === "session" && chatSessionId) {
                    const data = await exportSession(chatSessionId);
                    setExportData(data);
                } else if (type === "session-summary" && chatSessionId) {
                    const data = await getSessionSummary(chatSessionId);
                    setHasCache(!!data.has_cache);
                    setSummaryData(data.data);
                } else {
                    throw new Error("参数不完整");
                }
            } catch (e) {
                setError(e instanceof Error ? e.message : "加载失败");
            } finally {
                setLoading(false);
            }
        };

        loadData();
    }, [isOpen, type, bvid, folderId, folderIds, chatSessionId, format]);

    // 关闭时重置状态
    useEffect(() => {
        if (!isOpen) {
            setExportData(null);
            setError(null);
        }
    }, [isOpen]);

    const handleDownload = () => {
        if (type === "session-summary" && summaryData) {
            const filename = `总结_${chatSessionId?.slice(0, 8) || 'unknown'}_${new Date().toISOString().split('T')[0]}.md`;
            downloadMarkdown(summaryData.content, filename);
            return;
        }
        if (!exportData) return;
        downloadMarkdown(exportData.content, exportData.filename);
    };

    const handleRefresh = async () => {
        if (!chatSessionId) return;
        if (!confirm("重新生成会消耗 Token，是否继续？")) return;

        setRefreshing(true);
        try {
            await refreshSessionSummary(chatSessionId, format);
            const data = await getSessionSummary(chatSessionId);
            setHasCache(!!data.has_cache);
            setSummaryData(data.data);
            toast.success("总结已刷新");
        } catch (e) {
            toast.error(e instanceof Error ? e.message : "刷新失败");
        } finally {
            setRefreshing(false);
        }
    };

    const handleCopy = async () => {
        const content = type === "session-summary" ? summaryData?.content : exportData?.content;
        if (!content) return;
        const success = await copyToClipboard(content);
        if (success) {
            toast.success("已复制到剪贴板");
        } else {
            toast.error("复制失败，请手动复制");
        }
    };

    const getTitle = () => {
        switch (type) {
            case "video": return "导出视频";
            case "folder": return "导出收藏夹";
            case "session": return "导出会话";
            case "session-summary": return "会话总结";
        }
    };

    return (
        <Modal
            opened={isOpen}
            onClose={onClose}
            title={
                <Group gap="sm">
                    <ThemeIcon variant="light" color="teal" size="lg" radius="xl">
                        <IconFileText size={18} />
                    </ThemeIcon>
                    <div>
                        <Title order={4}>{getTitle()}</Title>
                        <Text size="xs" c="dimmed">Markdown 导出预览</Text>
                    </div>
                </Group>
            }
            size="xl"
            radius="lg"
            centered
        >
            <Stack gap="md">
                {loading ? (
                    <Box py="xl" style={{ display: 'flex', justifyContent: 'center' }}>
                        <Loader size="lg" />
                    </Box>
                ) : error ? (
                    <Card withBorder p="xl" bg="red.0">
                        <Stack align="center" gap="sm">
                            <Group gap="xs">
                                <IconAlertCircle size={20} color="var(--mantine-color-red-6)" />
                                <Text c="red">{error}</Text>
                            </Group>
                            <Button variant="light" onClick={() => window.location.reload()}>重试</Button>
                        </Stack>
                    </Card>
                ) : (
                    <>
                        {/* 格式选择 - 仅视频和收藏夹 */}
                        {(type === "video" || type === "folder") && (
                            <Box>
                                <Text size="sm" fw={500} mb="xs">导出格式</Text>
                                <SegmentedControl
                                    value={format}
                                    onChange={(value) => setFormat(value as "full" | "simple")}
                                    fullWidth
                                    data={[
                                        { label: "完整", value: "full" },
                                        { label: "精简", value: "simple" },
                                    ]}
                                />
                                <Text size="xs" c="dimmed" mt="xs">
                                    {format === "full" ? "包含完整标题、摘要、提纲、原文" : "只包含标题、摘要、核心要点"}
                                </Text>
                            </Box>
                        )}

                        {/* 文件信息 */}
                        {type === "session-summary" && summaryData ? (
                            <Group gap="xs">
                                <Badge variant="light">{summaryData.source_video_count} 个视频</Badge>
                                <Badge variant="light">{summaryData.message_count} 轮对话</Badge>
                                <Badge variant="outline" color={hasCache ? "green" : "gray"}>
                                    v{summaryData.version} · {hasCache ? "已缓存" : "新生成"}
                                </Badge>
                            </Group>
                        ) : exportData ? (
                            <Group gap="xs">
                                <Text size="xs" c="dimmed">文件名: {exportData.filename}</Text>
                                <Text size="xs" c="dimmed">大小: {(exportData.size / 1024).toFixed(1)} KB</Text>
                            </Group>
                        ) : null}

                        <Divider />

                        {/* 预览区 */}
                        <ScrollArea h={400}>
                            <Box
                                p="md"
                                style={{
                                    background: 'var(--mantine-color-gray-0)',
                                    borderRadius: 'var(--mantine-radius-md)',
                                }}
                            >
                                <Text
                                    component="pre"
                                    style={{
                                        whiteSpace: 'pre-wrap',
                                        fontFamily: 'inherit',
                                        fontSize: '14px',
                                        margin: 0,
                                    }}
                                >
                                    {type === "session-summary" ? summaryData?.content : exportData?.content}
                                </Text>
                            </Box>
                        </ScrollArea>

                        <Divider />

                        {/* 操作按钮 */}
                        <Group justify="space-between">
                            <Button
                                variant="subtle"
                                leftSection={<IconRefresh size={16} />}
                                onClick={handleRefresh}
                                loading={refreshing}
                                hidden={type !== "session-summary"}
                            >
                                重新生成
                            </Button>
                            <Group>
                                <Button
                                    variant="light"
                                    leftSection={<IconCopy size={16} />}
                                    onClick={handleCopy}
                                    disabled={(!exportData && !summaryData) || loading}
                                >
                                    复制内容
                                </Button>
                                <Button
                                    leftSection={<IconDownload size={16} />}
                                    onClick={handleDownload}
                                    disabled={(!exportData && !summaryData) || loading}
                                    color="teal"
                                >
                                    下载 .md
                                </Button>
                            </Group>
                        </Group>
                    </>
                )}
            </Stack>
        </Modal>
    );
}
