/**
 * 学习路径弹窗 - 使用 Mantine UI 组件库
 */

"use client";

import { useState, useEffect } from "react";
import { toast } from "sonner";
import {
    Modal,
    SegmentedControl,
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
    ActionIcon,
    Box,
    ThemeIcon,
    RingProgress,
    Progress,
} from "@mantine/core";
import { IconBook, IconRocket, IconRefresh, IconSparkles, IconPlayerPlay, IconClock, IconVideo, IconArrowRight } from "@tabler/icons-react";
import { learningPathApi, LearningPathResponse, LearningStageResponse } from "@/lib/api";

interface LearningPathModalProps {
    isOpen: boolean;
    onClose: () => void;
    folderId: number;
    folderTitle?: string;
    sessionId: string;
}

const USER_LEVELS = [
    { value: "beginner", label: "入门", icon: IconBook, color: "green" },
    { value: "intermediate", label: "进阶", icon: IconRocket, color: "yellow" },
    { value: "advanced", label: "高级", icon: IconSparkles, color: "red" },
];

export default function LearningPathModal({
    isOpen,
    onClose,
    folderId,
    folderTitle,
    sessionId,
}: LearningPathModalProps) {
    const [loading, setLoading] = useState(false);
    const [generating, setGenerating] = useState(false);
    const [path, setPath] = useState<LearningPathResponse | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [userLevel, setUserLevel] = useState<string>("beginner");
    const [selectedStage, setSelectedStage] = useState<number | null>(null);

    // 加载学习路径
    useEffect(() => {
        if (!isOpen || !folderId) return;

        const loadPath = async () => {
            setLoading(true);
            setError(null);
            try {
                const data = await learningPathApi.getLearningPath(folderId, userLevel, sessionId);
                setPath(data);
                if (data.stages.length > 0) {
                    setSelectedStage(data.stages[0].stage_id);
                }
            } catch (e) {
                if (e instanceof Error && (e.message.includes("暂无") || e.message.includes("不存在"))) {
                    setPath(null);
                } else {
                    setError(e instanceof Error ? e.message : "加载失败");
                }
            } finally {
                setLoading(false);
            }
        };

        loadPath();
    }, [isOpen, folderId, userLevel, sessionId]);

    // 触发生成学习路径
    const handleGenerate = async () => {
        setGenerating(true);
        try {
            await learningPathApi.triggerPathGeneration(folderId, userLevel, sessionId);
            toast.success("学习路径生成任务已提交，请稍后刷新");
            // 延迟刷新尝试获取结果
            setTimeout(async () => {
                try {
                    const data = await learningPathApi.getLearningPath(folderId, userLevel, sessionId);
                    setPath(data);
                    if (data.stages.length > 0) {
                        setSelectedStage(data.stages[0].stage_id);
                    }
                } catch {
                    // 忽略，等待用户手动刷新
                }
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
            const data = await learningPathApi.getLearningPath(folderId, userLevel, sessionId);
            setPath(data);
            if (data.stages.length > 0 && selectedStage === null) {
                setSelectedStage(data.stages[0].stage_id);
            }
        } catch (e) {
            setError(e instanceof Error ? e.message : "刷新失败");
        } finally {
            setLoading(false);
        }
    };

    const currentStage = path?.stages.find(s => s.stage_id === selectedStage);

    // 获取难度颜色
    const getDifficultyColor = (level?: string) => {
        switch (level) {
            case "beginner": return "green";
            case "intermediate": return "yellow";
            case "advanced": return "red";
            default: return "gray";
        }
    };

    // 获取难度标签
    const getDifficultyLabel = (level?: string) => {
        switch (level) {
            case "beginner": return "入门";
            case "intermediate": return "进阶";
            case "advanced": return "高级";
            default: return "未知";
        }
    };

    // 格式化时长
    const formatDuration = (seconds?: number) => {
        if (!seconds) return "--:--";
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}:${String(secs).padStart(2, '0')}`;
    };

    return (
        <Modal
            opened={isOpen}
            onClose={onClose}
            title={
                <Group gap="sm">
                    <ThemeIcon variant="light" color="blue" size="lg" radius="xl">
                        <IconBook size={18} />
                    </ThemeIcon>
                    <div>
                        <Title order={4}>学习路径</Title>
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
                {/* 用户水平选择 */}
                <Box>
                    <Text size="sm" fw={500} mb="xs">选择你的水平</Text>
                    <SegmentedControl
                        value={userLevel}
                        onChange={setUserLevel}
                        fullWidth
                        data={USER_LEVELS.map(level => ({
                            value: level.value,
                            label: (
                                <Group gap="xs" justify="center">
                                    <level.icon size={16} />
                                    <span>{level.label}</span>
                                </Group>
                            ),
                        }))}
                        color="blue"
                    />
                </Box>

                <Divider />

                {/* 内容区域 */}
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
                ) : path && path.stages.length > 0 ? (
                    <>
                        {/* 概览卡片 */}
                        <Card withBorder p="md" radius="md">
                            <Group justify="space-between">
                                <div>
                                    <Text size="sm" c="dimmed">推荐视频</Text>
                                    <Title order={3}>{path.total_videos} 个</Title>
                                </div>
                                <RingProgress
                                    size={80}
                                    thickness={8}
                                    roundCaps
                                    sections={[{
                                        value: (path.estimated_hours / 10) * 100,
                                        color: 'blue'
                                    }]}
                                    label={
                                        <Text size="xs" ta="center" fw={700}>
                                            {path.estimated_hours.toFixed(1)}h
                                        </Text>
                                    }
                                />
                                <div style={{ textAlign: 'right' }}>
                                    <Text size="sm" c="dimmed">预计学习</Text>
                                    <Title order={3}>{path.estimated_hours.toFixed(1)} 小时</Title>
                                </div>
                            </Group>
                        </Card>

                        {/* 学习阶段 */}
                        <Box>
                            <Text size="sm" fw={500} mb="xs">学习阶段</Text>
                            <ScrollArea h={200}>
                                <Stack gap="xs">
                                    {path.stages.map((stage, idx) => (
                                        <Card
                                            key={stage.stage_id}
                                            withBorder
                                            p="sm"
                                            radius="md"
                                            style={{
                                                cursor: 'pointer',
                                                borderColor: selectedStage === stage.stage_id ? 'var(--mantine-color-blue-6)' : undefined,
                                                background: selectedStage === stage.stage_id ? 'var(--mantine-color-blue-0)' : undefined,
                                            }}
                                            onClick={() => setSelectedStage(stage.stage_id)}
                                        >
                                            <Group justify="space-between" wrap="nowrap">
                                                <Group gap="sm" wrap="nowrap">
                                                    <ThemeIcon
                                                        size="lg"
                                                        radius="xl"
                                                        variant={selectedStage === stage.stage_id ? "filled" : "light"}
                                                        color="blue"
                                                    >
                                                        {idx + 1}
                                                    </ThemeIcon>
                                                    <div>
                                                        <Text size="sm" fw={500} lineClamp={1}>{stage.name}</Text>
                                                        <Group gap="xs">
                                                            <Badge size="xs" variant="light">{stage.videos.length} 个视频</Badge>
                                                            <Text size="xs" c="dimmed">约 {stage.estimated_time.toFixed(0)} 分钟</Text>
                                                        </Group>
                                                    </div>
                                                </Group>
                                                <IconArrowRight size={16} style={{ opacity: 0.5 }} />
                                            </Group>
                                        </Card>
                                    ))}
                                </Stack>
                            </ScrollArea>
                        </Box>

                        {/* 阶段详情 */}
                        {currentStage && (
                            <Box>
                                <Divider my="sm" label={`${currentStage.name} - 详情`} labelPosition="left" />
                                <Text size="sm" c="dimmed" mb="md">{currentStage.description}</Text>

                                {/* 前置知识 */}
                                {currentStage.prerequisites.length > 0 && (
                                    <Box mb="md">
                                        <Text size="sm" fw={500} mb="xs">前置知识</Text>
                                        <Group gap="xs">
                                            {currentStage.prerequisites.map((prereq, idx) => (
                                                <Badge key={idx} variant="light" color="gray">{prereq}</Badge>
                                            ))}
                                        </Group>
                                    </Box>
                                )}

                                {/* 视频列表 */}
                                <Stack gap="sm">
                                    {currentStage.videos.map((video, idx) => (
                                        <Card
                                            key={video.bvid}
                                            withBorder
                                            p="sm"
                                            radius="md"
                                            component="a"
                                            href={`https://www.bilibili.com/video/${video.bvid}`}
                                            target="_blank"
                                            style={{ textDecoration: 'none' }}
                                        >
                                            <Group justify="space-between" wrap="nowrap">
                                                <Group gap="sm" wrap="nowrap">
                                                    <ThemeIcon size="lg" radius="xl" variant="light" color="blue">
                                                        <IconVideo size={16} />
                                                    </ThemeIcon>
                                                    <div>
                                                        <Text size="sm" fw={500} lineClamp={1}>{video.title || video.bvid}</Text>
                                                        {video.short_intro && (
                                                            <Text size="xs" c="dimmed" lineClamp={1}>{video.short_intro}</Text>
                                                        )}
                                                    </div>
                                                </Group>
                                                <Group gap="xs" wrap="nowrap">
                                                    {video.difficulty_level && (
                                                        <Badge size="sm" color={getDifficultyColor(video.difficulty_level)}>
                                                            {getDifficultyLabel(video.difficulty_level)}
                                                        </Badge>
                                                    )}
                                                    {video.duration && (
                                                        <Badge size="sm" variant="outline" color="gray">
                                                            <Group gap={4} wrap="nowrap">
                                                                <IconClock size={12} />
                                                                {formatDuration(video.duration)}
                                                            </Group>
                                                        </Badge>
                                                    )}
                                                </Group>
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
                                <IconBook size={30} />
                            </ThemeIcon>
                            <div>
                                <Text fw={500}>暂无学习路径</Text>
                                <Text size="sm" c="dimmed">点击下方按钮生成学习路径</Text>
                            </div>
                        </Stack>
                    </Card>
                )}

                {/* 操作按钮 */}
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
                        生成学习路径
                    </Button>
                </Group>
            </Stack>
        </Modal>
    );
}
