/**
 * 视频摘要弹窗 - 使用 Mantine UI
 */

"use client";

import { useState, useEffect } from "react";
import {
    Modal,
    Button,
    Group,
    Stack,
    Text,
    Badge,
    Card,
    Loader,
    RingProgress,
    ThemeIcon,
    Divider,
    Collapse,
} from "@mantine/core";
import {
    IconFileText,
    IconSparkles,
    IconRefresh,
    IconCheck,
    IconTarget,
    IconChartBar,
    IconTags,
    IconInfoCircle,
    IconAlertCircle,
    IconChevronDown,
} from "@tabler/icons-react";
import { toast } from "sonner";
import { summaryApi, VideoSummaryResponse } from "@/lib/api";

interface VideoSummaryModalProps {
    isOpen: boolean;
    onClose: () => void;
    bvid: string;
    title?: string;
}

export default function VideoSummaryModal({
    isOpen,
    onClose,
    bvid,
    title,
}: VideoSummaryModalProps) {
    const [loading, setLoading] = useState(false);
    const [generating, setGenerating] = useState(false);
    const [summary, setSummary] = useState<VideoSummaryResponse | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [introOpened, setIntroOpened] = useState(false);

    // 加载摘要
    useEffect(() => {
        if (!isOpen || !bvid) return;

        const loadSummary = async () => {
            setLoading(true);
            setError(null);
            try {
                const data = await summaryApi.getSummary(bvid);
                setSummary(data);
            } catch (e) {
                if (e instanceof Error && e.message.includes("暂无摘要")) {
                    setSummary(null);
                } else {
                    setError(e instanceof Error ? e.message : "加载失败");
                }
            } finally {
                setLoading(false);
            }
        };

        loadSummary();
    }, [isOpen, bvid]);

    // 生成摘要
    const handleGenerate = async () => {
        setGenerating(true);
        try {
            await summaryApi.generateSummary(bvid);
            toast.success("摘要生成任务已提交，请稍后刷新");
            setTimeout(async () => {
                try {
                    const data = await summaryApi.getSummary(bvid);
                    setSummary(data);
                } catch {
                    // 忽略
                }
            }, 3000);
        } catch (e) {
            toast.error(e instanceof Error ? e.message : "生成失败");
        } finally {
            setGenerating(false);
        }
    };

    // 刷新摘要
    const handleRefresh = async () => {
        setLoading(true);
        try {
            const data = await summaryApi.getSummary(bvid);
            setSummary(data);
            toast.success("已刷新");
        } catch (e) {
            setError(e instanceof Error ? e.message : "刷新失败");
        } finally {
            setLoading(false);
        }
    };

    // 难度等级配置
    const difficultyConfig = {
        beginner: { label: "入门", color: "green", icon: IconChartBar },
        intermediate: { label: "进阶", color: "yellow", icon: IconChartBar },
        advanced: { label: "高级", color: "red", icon: IconChartBar },
    };

    return (
        <Modal
            opened={isOpen}
            onClose={onClose}
            title={
                <Group gap="sm">
                    <ThemeIcon variant="light" color="blue" size="lg">
                        <IconFileText size={20} />
                    </ThemeIcon>
                    <div>
                        <Text fw={600} size="lg">视频摘要</Text>
                        <Text size="xs" c="dimmed">{title || bvid}</Text>
                    </div>
                </Group>
            }
            size="lg"
            radius="lg"
            centered
            overlayProps={{ backgroundOpacity: 0.55, blur: 3 }}
        >
            {loading ? (
                <Stack align="center" py="xl" gap="md">
                    <Loader size="lg" color="blue" />
                    <Text c="dimmed">加载中...</Text>
                </Stack>
            ) : error ? (
                <Stack align="center" py="xl" gap="md">
                    <ThemeIcon size={48} radius="xl" color="red" variant="light">
                        <IconAlertCircle size={24} />
                    </ThemeIcon>
                    <Text c="red">{error}</Text>
                </Stack>
            ) : summary ? (
                <Stack gap="lg">
                    {/* 详细简介 (可折叠) */}
                    {summary.short_intro && (
                        <Card padding="md" radius="md" withBorder>
                            <Group 
                                justify="space-between" 
                                onClick={() => setIntroOpened(!introOpened)} 
                                style={{ cursor: 'pointer' }}
                                mb={introOpened ? "xs" : 0}
                            >
                                <Group gap="xs">
                                    <ThemeIcon size="sm" variant="light" color="blue">
                                        <IconInfoCircle size={14} />
                                    </ThemeIcon>
                                    <Text size="sm" fw={500} c="dimmed">详细简介</Text>
                                </Group>
                                <IconChevronDown 
                                    size={14} 
                                    style={{ 
                                        transform: introOpened ? 'rotate(180deg)' : 'none', 
                                        transition: 'transform 200ms ease' 
                                    }} 
                                />
                            </Group>
                            <Collapse in={introOpened}>
                                <Text mt="md" size="sm" style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>
                                    {summary.short_intro}
                                </Text>
                            </Collapse>
                        </Card>
                    )}

                    {/* 关键要点 */}
                    {summary.key_points && summary.key_points.length > 0 && (
                        <Card padding="md" radius="md" withBorder>
                            <Group gap="xs" mb="md">
                                <ThemeIcon size="sm" variant="light" color="violet">
                                    <IconSparkles size={14} />
                                </ThemeIcon>
                                <Text size="sm" fw={500} c="dimmed">关键要点</Text>
                            </Group>
                            <Stack gap="sm">
                                {summary.key_points.map((point, idx) => (
                                    <Group key={idx} gap="sm" align="flex-start">
                                        <Badge
                                            size="lg"
                                            radius="xl"
                                            color="violet"
                                            variant="filled"
                                            style={{ minWidth: 28 }}
                                        >
                                            {idx + 1}
                                        </Badge>
                                        <Text size="sm" style={{ flex: 1 }}>{point}</Text>
                                    </Group>
                                ))}
                            </Stack>
                        </Card>
                    )}

                    {/* 标签 */}
                    {summary.tags && summary.tags.length > 0 && (
                        <Card padding="md" radius="md" withBorder>
                            <Group gap="xs" mb="sm">
                                <ThemeIcon size="sm" variant="light" color="orange">
                                    <IconTags size={14} />
                                </ThemeIcon>
                                <Text size="sm" fw={500} c="dimmed">标签</Text>
                            </Group>
                            <Group gap="xs">
                                {summary.tags.map((tag, idx) => (
                                    <Badge key={idx} variant="light" color="orange">
                                        {tag}
                                    </Badge>
                                ))}
                            </Group>
                        </Card>
                    )}

                    {/* 目标受众和难度等级 */}
                    <Group grow>
                        {summary.target_audience && (
                            <Card padding="md" radius="md" withBorder>
                                <Group gap="xs" mb="xs">
                                    <ThemeIcon size="sm" variant="light" color="teal">
                                        <IconTarget size={14} />
                                    </ThemeIcon>
                                    <Text size="sm" fw={500} c="dimmed">适合人群</Text>
                                </Group>
                                <Text size="sm">{summary.target_audience}</Text>
                            </Card>
                        )}

                        {summary.difficulty_level && (
                            <Card padding="md" radius="md" withBorder>
                                <Group gap="xs" mb="xs">
                                    <ThemeIcon size="sm" variant="light" color="grape">
                                        <IconChartBar size={14} />
                                    </ThemeIcon>
                                    <Text size="sm" fw={500} c="dimmed">难度等级</Text>
                                </Group>
                                <Badge
                                    color={
                                        summary.difficulty_level === "beginner" ? "green" :
                                        summary.difficulty_level === "intermediate" ? "yellow" : "red"
                                    }
                                    variant="light"
                                    size="lg"
                                >
                                    {difficultyConfig[summary.difficulty_level as keyof typeof difficultyConfig]?.label || summary.difficulty_level}
                                </Badge>
                            </Card>
                        )}
                    </Group>

                    <Divider />

                    {/* 生成信息 */}
                    <Group justify="space-between">
                        <Text size="xs" c="dimmed">
                            {summary.is_generated ? (
                                <>生成于: {new Date(summary.generated_at!).toLocaleString("zh-CN")}</>
                            ) : (
                                "尚未生成"
                            )}
                        </Text>
                    </Group>
                </Stack>
            ) : (
                <Stack align="center" py="xl" gap="md">
                    <ThemeIcon size={64} radius="xl" color="gray" variant="light">
                        <IconFileText size={32} />
                    </ThemeIcon>
                    <Text c="dimmed">暂无摘要</Text>
                    <Text size="sm" c="dimmed">点击下方按钮生成视频摘要</Text>
                </Stack>
            )}

            {/* 底部操作 */}
            <Group justify="space-between" mt="xl" pt="md" style={{ borderTop: "1px solid var(--mantine-color-gray-3)" }}>
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
                    color="blue"
                >
                    {generating ? "生成中..." : "生成摘要"}
                </Button>
            </Group>
        </Modal>
    );
}
