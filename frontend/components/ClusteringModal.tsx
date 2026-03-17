/**
 * 主题聚类弹窗 - 使用 Mantine UI
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
    ThemeIcon,
    RingProgress,
    Box,
} from "@mantine/core";
import { IconApps, IconSparkles, IconRefresh, IconPlayerPlay, IconTag } from "@tabler/icons-react";
import { clusteringApi, ClustersResponse, TopicClusterResponse } from "@/lib/api";

interface ClusteringModalProps {
    isOpen: boolean;
    onClose: () => void;
    folderId: number;
    folderTitle?: string;
    sessionId: string;
}

export default function ClusteringModal({
    isOpen,
    onClose,
    folderId,
    folderTitle,
    sessionId,
}: ClusteringModalProps) {
    const [loading, setLoading] = useState(false);
    const [generating, setGenerating] = useState(false);
    const [clusters, setClusters] = useState<ClustersResponse | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [selectedCluster, setSelectedCluster] = useState<number | null>(null);

    // 加载聚类结果
    useEffect(() => {
        if (!isOpen || !folderId) return;

        const loadClusters = async () => {
            setLoading(true);
            setError(null);
            try {
                const data = await clusteringApi.getClusters(folderId);
                setClusters(data);
                if (data.clusters.length > 0) {
                    setSelectedCluster(0);
                }
            } catch (e) {
                if (e instanceof Error && e.message.includes("暂无聚类结果")) {
                    setClusters(null);
                } else {
                    setError(e instanceof Error ? e.message : "加载失败");
                }
            } finally {
                setLoading(false);
            }
        };

        loadClusters();
    }, [isOpen, folderId]);

    // 触发生成聚类
    const handleGenerate = async () => {
        setGenerating(true);
        try {
            await clusteringApi.generateClusters(folderId);
            toast.success("聚类生成任务已提交，请稍后刷新");
            setTimeout(async () => {
                try {
                    const data = await clusteringApi.getClusters(folderId);
                    setClusters(data);
                    if (data.clusters.length > 0) {
                        setSelectedCluster(0);
                    }
                } catch { /* ignore */ }
            }, 5000);
        } catch (e) {
            toast.error(e instanceof Error ? e.message : "生成失败");
        } finally {
            setGenerating(false);
        }
    };

    // 刷新
    const handleRefresh = async () => {
        setLoading(true);
        try {
            const data = await clusteringApi.getClusters(folderId);
            setClusters(data);
            if (data.clusters.length > 0 && selectedCluster === null) {
                setSelectedCluster(0);
            }
        } catch (e) {
            setError(e instanceof Error ? e.message : "刷新失败");
        } finally {
            setLoading(false);
        }
    };

    const currentCluster = clusters?.clusters.find((_, idx) => idx === selectedCluster);

    // 获取难度颜色
    const getDifficultyColor = (level?: string) => {
        switch (level) {
            case "beginner": return "green";
            case "intermediate": return "yellow";
            case "advanced": return "red";
            default: return "gray";
        }
    };

    return (
        <Modal
            opened={isOpen}
            onClose={onClose}
            title={
                <Group gap="sm">
                    <ThemeIcon variant="light" color="violet" size="lg" radius="xl">
                        <IconApps size={18} />
                    </ThemeIcon>
                    <div>
                        <Title order={4}>主题聚类</Title>
                        <Text size="xs" c="dimmed">{folderTitle || `收藏夹 #${folderId}`}</Text>
                    </div>
                </Group>
            }
            size="xl"
            radius="lg"
            centered
            scrollAreaComponent={ScrollArea.Autosize}
        >
            <Stack gap="md">
                {loading ? (
                    <Box py="xl" style={{ display: 'flex', justifyContent: 'center' }}>
                        <Loader size="lg" />
                    </Box>
                ) : error ? (
                    <Card withBorder p="xl" bg="red.0">
                        <Stack align="center" gap="sm">
                            <Text c="red">{error}</Text>
                            <Button variant="light" onClick={handleRefresh}>重试</Button>
                        </Stack>
                    </Card>
                ) : clusters && clusters.clusters.length > 0 ? (
                    <>
                        {/* 概览 */}
                        <Card withBorder p="md" radius="md">
                            <Group justify="space-between">
                                <div>
                                    <Text size="sm" c="dimmed">聚类数量</Text>
                                    <Title order={3}>{clusters.clusters.length} 个主题</Title>
                                </div>
                                <RingProgress
                                    size={80}
                                    thickness={8}
                                    roundCaps
                                    sections={[{
                                        value: (clusters.clusters.length / 10) * 100,
                                        color: 'violet'
                                    }]}
                                    label={
                                        <Text size="xs" ta="center" fw={700}>
                                            {clusters.clusters.length}
                                        </Text>
                                    }
                                />
                            </Group>
                        </Card>

                        {/* 主题列表 */}
                        <Box>
                            <Text size="sm" fw={500} mb="xs">主题分类</Text>
                            <ScrollArea h={180}>
                                <Stack gap="xs">
                                    {clusters.clusters.map((cluster, idx) => (
                                        <Card
                                            key={idx}
                                            withBorder
                                            p="sm"
                                            radius="md"
                                            style={{
                                                cursor: 'pointer',
                                                borderColor: selectedCluster === idx ? 'var(--mantine-color-violet-6)' : undefined,
                                                background: selectedCluster === idx ? 'var(--mantine-color-violet-0)' : undefined,
                                            }}
                                            onClick={() => setSelectedCluster(idx)}
                                        >
                                            <Group justify="space-between" wrap="nowrap">
                                                <Group gap="sm" wrap="nowrap">
                                                    <ThemeIcon size="lg" radius="xl" variant={selectedCluster === idx ? "filled" : "light"} color="violet">
                                                        <IconTag size={16} />
                                                    </ThemeIcon>
                                                    <div>
                                                        <Text size="sm" fw={500} lineClamp={1}>{cluster.topic_name}</Text>
                                                        <Group gap="xs">
                                                            <Badge size="xs" variant="light">{cluster.video_count} 个视频</Badge>
                                                            {cluster.keywords?.slice(0, 2).map((kw, i) => (
                                                                <Badge key={i} size="xs" variant="outline">{kw}</Badge>
                                                            ))}
                                                        </Group>
                                                    </div>
                                                </Group>
                                            </Group>
                                        </Card>
                                    ))}
                                </Stack>
                            </ScrollArea>
                        </Box>

                        {/* 主题详情 */}
                        {currentCluster && (
                            <Box>
                                <Divider my="sm" label={`${currentCluster.topic_name} - 视频列表`} labelPosition="left" />
                                {currentCluster.keywords && currentCluster.keywords.length > 0 && (
                                    <Group gap="xs" mb="md">
                                        {currentCluster.keywords.map((kw, idx) => (
                                            <Badge key={idx} variant="light" color="violet">{kw}</Badge>
                                        ))}
                                    </Group>
                                )}
                                <Stack gap="sm">
                                    {currentCluster.videos?.map((video, idx) => (
                                        <Card
                                            key={idx}
                                            withBorder
                                            p="sm"
                                            radius="md"
                                            component="a"
                                            href={`https://www.bilibili.com/video/${video.bvid}`}
                                            target="_blank"
                                            style={{ textDecoration: 'none' }}
                                        >
                                            <Group justify="space-between" wrap="nowrap">
                                                <div>
                                                    <Text size="sm" fw={500} lineClamp={1}>{video.title || video.bvid}</Text>
                                                    {video.short_intro && (
                                                        <Text size="xs" c="dimmed" lineClamp={1}>{video.short_intro}</Text>
                                                    )}
                                                </div>
                                                {video.difficulty_level && (
                                                    <Badge size="sm" color={getDifficultyColor(video.difficulty_level)}>
                                                        {video.difficulty_level}
                                                    </Badge>
                                                )}
                                            </Group>
                                        </Card>
                                    ))}
                                </Stack>
                            </Box>
                        )}
                    </>
                ) : (
                    <Card withBorder p="xl" ta="center">
                        <Stack align="center" gap="md">
                            <ThemeIcon size={60} radius="xl" variant="light" color="gray">
                                <IconApps size={30} />
                            </ThemeIcon>
                            <div>
                                <Text fw={500}>暂无聚类结果</Text>
                                <Text size="sm" c="dimmed">点击下方按钮生主题聚类</Text>
                            </div>
                        </Stack>
                    </Card>
                )}

                {/* 操作 */}
                <Group justify="space-between">
                    <Button
                        variant="subtle"
                        leftSection={<IconRefresh size={16} />}
                        onClick={handleRefresh}
                        loading={loading}
                    >
                        刷新
                    </Button>
                    <Button
                        leftSection={<IconSparkles size={16} />}
                        onClick={handleGenerate}
                        loading={generating}
                    >
                        生成聚类
                    </Button>
                </Group>
            </Stack>
        </Modal>
    );
}
