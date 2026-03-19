/**
 * 内容修正弹窗 - 使用 Mantine UI
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
    Textarea,
    Box,
    ThemeIcon,
    RingProgress,
    Collapse,
    ActionIcon,
} from "@mantine/core";
import { IconFileText, IconRefresh, IconDeviceFloppy, IconHistory, IconChevronDown, IconChevronUp, IconArrowLeft } from "@tabler/icons-react";
import {
    correctionApi,
    CorrectionListResponse,
    CorrectionDetail,
    CorrectionHistoryResponse,
} from "@/lib/api";

interface CorrectionModalProps {
    isOpen: boolean;
    onClose: () => void;
    userSessionId: string;
    initialBvid?: string;
}

export default function CorrectionModal({
    isOpen,
    onClose,
    userSessionId,
    initialBvid,
}: CorrectionModalProps) {
    const [view, setView] = useState<"list" | "detail">("list");
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [listData, setListData] = useState<CorrectionListResponse | null>(null);
    const [detail, setDetail] = useState<CorrectionDetail | null>(null);
    const [history, setHistory] = useState<CorrectionHistoryResponse | null>(null);
    const [editedContent, setEditedContent] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [currentBvid, setCurrentBvid] = useState<string | null>(null);
    const [showHistory, setShowHistory] = useState(false);

    // 加载修正列表
    useEffect(() => {
        if (!isOpen || !userSessionId) return;

        if (initialBvid) {
            setCurrentBvid(initialBvid);
            setView("detail");
            loadDetail(initialBvid);
        } else {
            setView("list");
            loadList();
        }
    }, [isOpen, userSessionId, initialBvid]);

    const loadList = async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await correctionApi.listCorrections(userSessionId);
            setListData(data);
        } catch (e) {
            setError(e instanceof Error ? e.message : "加载失败");
        } finally {
            setLoading(false);
        }
    };

    const loadDetail = async (bvid: string) => {
        setLoading(true);
        setError(null);
        try {
            const data = await correctionApi.getCorrection(bvid, userSessionId);
            setDetail(data);
            setEditedContent(data.content);
            setCurrentBvid(bvid);
            loadHistory(bvid);
        } catch (e) {
            setError(e instanceof Error ? e.message : "加载失败");
        } finally {
            setLoading(false);
        }
    };

    const loadHistory = async (bvid: string) => {
        try {
            const data = await correctionApi.getCorrectionHistory(bvid, userSessionId);
            setHistory(data);
        } catch {
            setHistory(null);
        }
    };

    // 保存修正
    const handleSave = async () => {
        if (!currentBvid) return;

        setSaving(true);
        try {
            await correctionApi.submitCorrection(currentBvid, userSessionId, editedContent);
            toast.success("修正已保存");
            await loadDetail(currentBvid);
        } catch (e) {
            toast.error(e instanceof Error ? e.message : "保存失败");
        } finally {
            setSaving(false);
        }
    };

    // 返回列表
    const handleBack = () => {
        setView("list");
        setCurrentBvid(null);
        setDetail(null);
        setHistory(null);
        setEditedContent("");
        loadList();
    };

    // 获取质量颜色
    const getQualityColor = (score: number) => {
        if (score >= 0.8) return "green";
        if (score >= 0.6) return "yellow";
        return "red";
    };

    // 获取质量等级颜色
    const getGradeColor = (grade: string) => {
        switch (grade) {
            case "A": return "green";
            case "B": return "yellow";
            case "C": return "orange";
            default: return "red";
        }
    };

    const handleClose = () => {
        setView("list");
        setCurrentBvid(null);
        setDetail(null);
        setHistory(null);
        setEditedContent("");
        onClose();
    };

    // 列表视图
    if (view === "list") {
        return (
            <Modal
                opened={isOpen}
                onClose={handleClose}
                title={
                    <Group gap="sm">
                        <ThemeIcon variant="light" color="orange" size="lg" radius="xl">
                            <IconFileText size={18} />
                        </ThemeIcon>
                        <div>
                            <Title order={4}>内容修正</Title>
                            <Text size="xs" c="dimmed">修正视频转写内容</Text>
                        </div>
                    </Group>
                }
                size="lg"
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
                                <Button variant="light" onClick={loadList}>重试</Button>
                            </Stack>
                        </Card>
                    ) : listData && listData.videos.length > 0 ? (
                        <ScrollArea h={400}>
                            <Stack gap="sm">
                                {listData.videos.map((video) => (
                                    <Card
                                        key={video.bvid}
                                        withBorder
                                        p="md"
                                        radius="md"
                                        style={{
                                            cursor: 'pointer',
                                            borderColor: 'var(--mantine-color-orange-6)',
                                        }}
                                        onClick={() => {
                                            setCurrentBvid(video.bvid);
                                            setView("detail");
                                            loadDetail(video.bvid);
                                        }}
                                    >
                                        <Group justify="space-between" wrap="nowrap">
                                            <div style={{ flex: 1, minWidth: 0 }}>
                                                <Text size="sm" fw={500} lineClamp={1}>{video.title || video.bvid}</Text>
                                                {video.content_preview && (
                                                    <Text size="xs" c="dimmed" lineClamp={2} mt={4}>{video.content_preview}</Text>
                                                )}
                                                <Group gap="xs" mt="xs">
                                                    {video.asr_quality_score !== undefined && (
                                                        <Badge
                                                            size="sm"
                                                            color={getQualityColor(video.asr_quality_score)}
                                                        >
                                                            质量: {(video.asr_quality_score * 100).toFixed(0)}%
                                                        </Badge>
                                                    )}
                                                    {video.is_corrected && (
                                                        <Badge size="sm" color="blue">已修正</Badge>
                                                    )}
                                                </Group>
                                            </div>
                                        </Group>
                                    </Card>
                                ))}
                            </Stack>
                        </ScrollArea>
                    ) : (
                        <Card withBorder p="xl" ta="center">
                            <Stack align="center" gap="md">
                                <ThemeIcon size={60} radius="xl" variant="light" color="gray">
                                    <IconFileText size={30} />
                                </ThemeIcon>
                                <div>
                                    <Text fw={500}>暂无需修正的内容</Text>
                                    <Text size="sm" c="dimmed">暂无低质量转写内容</Text>
                                </div>
                            </Stack>
                        </Card>
                    )}

                    <Group justify="space-between">
                        <Text size="sm" c="dimmed">共 {listData?.total || 0} 个视频</Text>
                        <Button
                            variant="subtle"
                            leftSection={<IconRefresh size={16} />}
                            onClick={loadList}
                            loading={loading}
                        >
                            刷新
                        </Button>
                    </Group>
                </Stack>
            </Modal>
        );
    }

    // 详情视图
    return (
        <Modal
            opened={isOpen}
            onClose={handleClose}
            title={
                <Group gap="sm">
                    <ActionIcon variant="subtle" onClick={handleBack}>
                        <IconArrowLeft size={18} />
                    </ActionIcon>
                    <div>
                        <Title order={4}>内容修正</Title>
                        <Text size="xs" c="dimmed">{detail?.title || currentBvid}</Text>
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
                            <Button variant="light" onClick={() => loadDetail(currentBvid!)}>重试</Button>
                        </Stack>
                    </Card>
                ) : (
                    <>
                        {/* 质量报告 */}
                        {detail?.quality_report && (
                            <Card withBorder p="md" radius="md">
                                <Group justify="space-between" wrap="wrap">
                                    <div>
                                        <Text size="sm" c="dimmed">质量分数</Text>
                                        <Group gap="xs">
                                            <Title order={3}>{((detail.quality_report.quality_score) * 100).toFixed(0)}%</Title>
                                            <Badge color={getGradeColor(detail.quality_report.quality_grade)} size="lg">
                                                {detail.quality_report.quality_grade} 级
                                            </Badge>
                                        </Group>
                                    </div>
                                    <RingProgress
                                        size={80}
                                        thickness={8}
                                        roundCaps
                                        sections={[{
                                            value: detail.quality_report.quality_score * 100,
                                            color: getQualityColor(detail.quality_report.quality_score)
                                        }]}
                                        label={
                                            <Text size="xs" ta="center" fw={700}>
                                                {detail.quality_report.quality_grade}
                                            </Text>
                                        }
                                    />
                                </Group>
                                <Divider my="sm" />
                                <Group gap="xl">
                                    <div>
                                        <Text size="xs" c="dimmed">音频质量</Text>
                                        <Text size="sm" fw={500}>{detail.quality_report.audio_quality}</Text>
                                    </div>
                                    <div>
                                        <Text size="xs" c="dimmed">置信度平均</Text>
                                        <Text size="sm" fw={500}>{(detail.quality_report.confidence_avg * 100).toFixed(0)}%</Text>
                                    </div>
                                    <div>
                                        <Text size="xs" c="dimmed">语音比例</Text>
                                        <Text size="sm" fw={500}>{(detail.quality_report.speech_ratio * 100).toFixed(0)}%</Text>
                                    </div>
                                </Group>
                                {detail.quality_report.suggestions.length > 0 && (
                                    <>
                                        <Divider my="sm" />
                                        <div>
                                            <Text size="xs" c="dimmed" mb="xs">改进建议</Text>
                                            <Stack gap={4}>
                                                {detail.quality_report.suggestions.map((s, i) => (
                                                    <Text key={i} size="xs">- {s}</Text>
                                                ))}
                                            </Stack>
                                        </div>
                                    </>
                                )}
                            </Card>
                        )}

                        {/* 内容编辑 */}
                        <div>
                            <Text size="sm" fw={500} mb="xs">转写内容编辑</Text>
                            <Textarea
                                value={editedContent}
                                onChange={(e) => setEditedContent(e.target.value)}
                                minRows={10}
                                maxRows={20}
                                autosize
                                placeholder="加载中..."
                            />
                        </div>

                        {/* 句子标记 */}
                        {detail?.sentences && detail.sentences.length > 0 && (
                            <div>
                                <Text size="sm" fw={500} mb="xs">
                                    句子标记 ({detail.sentences.length})
                                </Text>
                                <ScrollArea h={150}>
                                    <Stack gap={4}>
                                        {detail.sentences.slice(0, 20).map((s) => (
                                            <Card
                                                key={s.id}
                                                withBorder
                                                p="xs"
                                                radius="sm"
                                                bg={s.is_flagged ? "red.0" : "gray.0"}
                                            >
                                                <Group justify="space-between" wrap="nowrap">
                                                    <Text size="xs" lineClamp={1} style={{ flex: 1 }}>
                                                        {s.text}
                                                    </Text>
                                                    {s.is_flagged && (
                                                        <Badge size="xs" color="red" variant="light">待修正</Badge>
                                                    )}
                                                </Group>
                                            </Card>
                                        ))}
                                        {detail.sentences.length > 20 && (
                                            <Text size="xs" c="dimmed" ta="center">
                                                ... 还有 {detail.sentences.length - 20} 个句子
                                            </Text>
                                        )}
                                    </Stack>
                                </ScrollArea>
                            </div>
                        )}

                        {/* 历史记录 */}
                        {history && history.history.length > 0 && (
                            <Card withBorder p="md" radius="md">
                                <Button
                                    variant="subtle"
                                    onClick={() => setShowHistory(!showHistory)}
                                    leftSection={<IconHistory size={16} />}
                                    rightSection={showHistory ? <IconChevronUp size={16} /> : <IconChevronDown size={16} />}
                                    fullWidth
                                >
                                    历史记录 ({history.total})
                                </Button>
                                <Collapse in={showHistory}>
                                    <ScrollArea h={200} mt="sm">
                                        <Stack gap="xs">
                                            {history.history.map((item) => (
                                                <Card key={item.id} withBorder p="sm" radius="sm" bg="gray.0">
                                                    <Group justify="space-between" wrap="nowrap">
                                                        <div>
                                                            <Text size="xs" c="dimmed">
                                                                {new Date(item.created_at).toLocaleString()}
                                                            </Text>
                                                            <Text size="xs">
                                                                {item.correction_type} - {item.char_diff > 0 ? `+${item.char_diff}` : item.char_diff} 字符
                                                            </Text>
                                                        </div>
                                                    </Group>
                                                </Card>
                                            ))}
                                        </Stack>
                                    </ScrollArea>
                                </Collapse>
                            </Card>
                        )}

                        {/* 操作按钮 */}
                        <Group justify="space-between">
                            <Button
                                variant="subtle"
                                leftSection={<IconRefresh size={16} />}
                                onClick={() => loadDetail(currentBvid!)}
                                disabled={loading}
                            >
                                重置
                            </Button>
                            <Button
                                leftSection={<IconDeviceFloppy size={16} />}
                                onClick={handleSave}
                                loading={saving}
                                disabled={editedContent === detail?.content}
                                color="orange"
                            >
                                保存修正
                            </Button>
                        </Group>
                    </>
                )}
            </Stack>
        </Modal>
    );
}
