/**
 * 会话列表组件 - Mantine UI 重构版本
 */

"use client";

import { useState, useEffect, useRef } from "react";
import { ChatSession, conversationApi } from "@/lib/conversation";
import { toast } from "sonner";
import {
    ActionIcon,
    Menu,
    TextInput,
    Modal,
    Skeleton,
    ScrollArea,
    Group,
    Text,
    Button,
    Stack,
    Divider,
    Box,
} from "@mantine/core";
import {
    IconMessage,
    IconPlus,
    IconDotsVertical,
    IconPencil,
    IconTrash,
    IconMessageOff,
    IconChevronRight,
} from "@tabler/icons-react";

interface Props {
    userSessionId: string;
    currentSessionId?: string;
    onSelectSession: (sessionId: string | null) => void;
    onCreateSession: () => void;
    onSessionChange?: () => void;
    isExpanded?: boolean;
    externalSessions?: ChatSession[];
    externalLoading?: boolean;
}

// ============ 加载骨架屏 ============
function SessionSkeleton() {
    return (
        <Stack gap="xs" p="md">
            <Skeleton height={40} radius="md" />
            <Skeleton height={40} radius="md" />
            <Skeleton height={40} radius="md" />
            <Skeleton height={40} radius="md" />
        </Stack>
    );
}

// ============ 空状态 ============
function EmptyState({ onCreateSession }: { onCreateSession: () => void }) {
    return (
        <Stack align="center" justify="center" h={300} gap="md">
            <Box
                style={{
                    width: 64,
                    height: 64,
                    borderRadius: 16,
                    background: "var(--bg-tertiary)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                }}
            >
                <IconMessageOff size={28} color="#98989f" />
            </Box>
            <Text c="#98989f" size="sm">暂无会话记录</Text>
            <Button
                leftSection={<IconPlus size={16} />}
                variant="light"
                color="blue"
                size="xs"
                onClick={onCreateSession}
            >
                新建会话
            </Button>
        </Stack>
    );
}

// ============ 会话项 ============
function SessionItem({
    session,
    isActive,
    isEditing,
    editTitle,
    onSelect,
    onStartEdit,
    onEditTitleChange,
    onEditSave,
    onEditCancel,
    onDelete,
}: {
    session: ChatSession;
    isActive: boolean;
    isEditing: boolean;
    editTitle: string;
    onSelect: () => void;
    onStartEdit: () => void;
    onEditTitleChange: (v: string) => void;
    onEditSave: () => void;
    onEditCancel: () => void;
    onDelete: () => void;
}) {
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        if (isEditing && inputRef.current) {
            inputRef.current.focus();
        }
    }, [isEditing]);

    const formatTime = (dateStr: string | null) => {
        if (!dateStr) return "";
        const date = new Date(dateStr);
        const now = new Date();
        const diff = now.getTime() - date.getTime();
        const days = Math.floor(diff / (1000 * 60 * 60 * 24));
        if (days === 0) return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
        if (days === 1) return "昨天";
        if (days < 7) return `${days}天前`;
        return date.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
    };

    return (
        <Box
            onClick={onSelect}
            style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: "10px 12px",
                borderRadius: 8,
                cursor: "pointer",
                background: isActive ? "var(--bg-hover)" : "transparent",
                transition: "background 0.2s",
            }}
            className={!isActive ? "hover:bg-[var(--bg-hover)]" : ""}
        >
            {/* 左侧图标 */}
            <Box
                style={{
                    width: 32,
                    height: 32,
                    borderRadius: 8,
                    background: isActive ? "var(--accent)" : "var(--bg-tertiary)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                }}
            >
                <IconMessage
                    size={16}
                    color={isActive ? "white" : "#98989f"}
                />
            </Box>

            {/* 标题区域 */}
            <Box style={{ flex: 1, minWidth: 0 }}>
                {isEditing ? (
                    <TextInput
                        ref={inputRef as any}
                        value={editTitle}
                        onChange={(e) => onEditTitleChange(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === "Enter") onEditSave();
                            if (e.key === "Escape") onEditCancel();
                            e.stopPropagation();
                        }}
                        onBlur={onEditSave}
                        size="xs"
                        styles={{
                            input: {
                                background: "var(--bg-tertiary)",
                                border: "1px solid var(--accent)",
                                color: "white",
                            },
                        }}
                        onClick={(e) => e.stopPropagation()}
                    />
                ) : (
                    <>
                        <Text
                            size="sm"
                            fw={500}
                            c={isActive ? "white" : "#aeaeb2"}
                            lineClamp={1}
                        >
                            {session.title || "新会话"}
                        </Text>
                        {session.message_count > 0 && (
                            <Text size="xs" c="#636366" mt={2}>
                                {formatTime(session.last_message_at)} · {session.message_count} 条消息
                            </Text>
                        )}
                    </>
                )}
            </Box>

            {/* 操作菜单 */}
            {!isEditing && (
                <Menu shadow="md" width={160} position="bottom-end">
                    <Menu.Target>
                        <ActionIcon
                            variant="subtle"
                            color="gray"
                            size="sm"
                            onClick={(e) => e.stopPropagation()}
                        >
                            <IconDotsVertical size={14} />
                        </ActionIcon>
                    </Menu.Target>

                    <Menu.Dropdown>
                        <Menu.Item
                            leftSection={<IconPencil size={14} />}
                            onClick={(e) => {
                                e.stopPropagation();
                                onStartEdit();
                            }}
                            c="#aeaeb2"
                        >
                            重命名
                        </Menu.Item>
                        <Menu.Divider />
                        <Menu.Item
                            color="red"
                            leftSection={<IconTrash size={14} />}
                            onClick={(e) => {
                                e.stopPropagation();
                                onDelete();
                            }}
                        >
                            删除会话
                        </Menu.Item>
                    </Menu.Dropdown>
                </Menu>
            )}
        </Box>
    );
}

// ============ 主组件 ============
export default function SessionList({
    userSessionId,
    currentSessionId,
    onSelectSession,
    onCreateSession,
    onSessionChange,
    isExpanded = true,
    externalSessions,
    externalLoading,
}: Props) {
    const [sessions, setSessions] = useState<ChatSession[]>(externalSessions || []);
    const [loading, setLoading] = useState(externalLoading ?? true);
    const [editingId, setEditingId] = useState<string | null>(null);
    const [editTitle, setEditTitle] = useState("");
    const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
    const [showEmptySessions, setShowEmptySessions] = useState(false);

    useEffect(() => {
        if (externalSessions) setSessions(externalSessions);
    }, [externalSessions]);

    useEffect(() => {
        if (externalLoading !== undefined) setLoading(externalLoading);
    }, [externalLoading]);

    useEffect(() => {
        if (!externalSessions && userSessionId) loadSessions();
    }, [userSessionId, externalSessions]);

    const loadSessions = async () => {
        try {
            setLoading(true);
            const data = await conversationApi.list(userSessionId);
            setSessions(data.sessions);
        } catch (error) {
            console.error("加载会话列表失败:", error);
        } finally {
            setLoading(false);
        }
    };

    const handleDelete = async (sessionId: string) => {
        try {
            await conversationApi.delete(sessionId, userSessionId);
            setSessions(sessions.filter((s) => s.chat_session_id !== sessionId));
            if (currentSessionId === sessionId) onSelectSession(null);
            setDeleteConfirmId(null);
            onSessionChange?.();
            toast.success("会话已删除");
        } catch (error) {
            toast.error("删除失败，请重试");
        }
    };

    const handleRename = (sessionId: string, save: boolean = true) => {
        const trimmedTitle = editTitle.trim();
        if (!save || !trimmedTitle) {
            setEditingId(null);
            setEditTitle("");
            return;
        }
        const finalTitle = trimmedTitle.slice(0, 30);
        conversationApi.update(sessionId, userSessionId, { title: finalTitle })
            .then(() => {
                setSessions(sessions.map((s) => s.chat_session_id === sessionId ? { ...s, title: finalTitle } : s));
                setEditingId(null);
                setEditTitle("");
                onSessionChange?.();
                toast.success("会话已重命名");
            })
            .catch(() => toast.error("重命名失败，请重试"));
    };

    const isEmptySession = (session: ChatSession) => !session.last_message_at || session.message_count === 0;

    const activeSessions = sessions.filter(s => !isEmptySession(s));
    const emptySessions = sessions.filter(s => isEmptySession(s));

    // 收起状态
    if (!isExpanded) {
        const currentSession = currentSessionId ? sessions.find((s) => s.chat_session_id === currentSessionId) : null;
        return (
            <Stack align="center" justify="center" h="100%" gap="md" p="md">
                <ActionIcon
                    size="xl"
                    variant="filled"
                    color="blue"
                    onClick={onCreateSession}
                >
                    <IconPlus size={20} />
                </ActionIcon>
                {currentSession ? (
                    <ActionIcon size="xl" variant="light" color="blue" onClick={() => onSelectSession(null)}>
                        <IconMessage size={20} />
                    </ActionIcon>
                ) : (
                    <ActionIcon size="xl" variant="subtle" color="gray">
                        <IconMessage size={20} />
                    </ActionIcon>
                )}
            </Stack>
        );
    }

    // 展开状态
    return (
        <Box style={{ display: "flex", flexDirection: "column", height: "100%" }}>
            {/* 新建会话按钮 */}
            <Box p="md" pb="xs">
                <Button
                    fullWidth
                    leftSection={<IconPlus size={16} />}
                    onClick={onCreateSession}
                    color="blue"
                >
                    新建会话
                </Button>
            </Box>

            {/* 标题栏 */}
            <Group justify="space-between" px="md" py="xs">
                <Text size="xs" fw={600} c="#98989f" tt="uppercase" style={{ letterSpacing: "0.05em" }}>
                    会话
                </Text>
                {sessions.length > 0 && (
                    <Text size="xs" c="#636366">{sessions.length}</Text>
                )}
            </Group>

            <Divider color="var(--glass-border)" />

            {/* 列表内容 */}
            <ScrollArea style={{ flex: 1 }} type="hover">
                {loading ? (
                    <SessionSkeleton />
                ) : sessions.length === 0 ? (
                    <EmptyState onCreateSession={onCreateSession} />
                ) : (
                    <Stack gap={4} p="xs">
                        {/* 活跃会话 */}
                        {activeSessions.map((session) => (
                            <SessionItem
                                key={session.chat_session_id}
                                session={session}
                                isActive={currentSessionId === session.chat_session_id}
                                isEditing={editingId === session.chat_session_id}
                                editTitle={editTitle}
                                onSelect={() => onSelectSession(session.chat_session_id)}
                                onStartEdit={() => {
                                    setEditingId(session.chat_session_id);
                                    setEditTitle(session.title || "");
                                }}
                                onEditTitleChange={setEditTitle}
                                onEditSave={() => handleRename(session.chat_session_id, true)}
                                onEditCancel={() => handleRename(session.chat_session_id, false)}
                                onDelete={() => setDeleteConfirmId(session.chat_session_id)}
                            />
                        ))}

                        {/* 空白会话 */}
                        {emptySessions.length > 0 && (
                            <Box mt="md">
                                <Box
                                    component="button"
                                    onClick={() => setShowEmptySessions(!showEmptySessions)}
                                    style={{
                                        display: "flex",
                                        alignItems: "center",
                                        justifyContent: "space-between",
                                        width: "100%",
                                        padding: "8px 12px",
                                        border: "none",
                                        background: "transparent",
                                        cursor: "pointer",
                                        borderRadius: 8,
                                    }}
                                >
                                    <Text size="xs" c="#636366">空白会话</Text>
                                    <Group gap={4}>
                                        <Text size="xs" c="#636366">{emptySessions.length}</Text>
                                        <IconChevronRight
                                            size={14}
                                            style={{
                                                transform: showEmptySessions ? "rotate(90deg)" : "none",
                                                transition: "transform 0.2s",
                                                color: "#636366",
                                            }}
                                        />
                                    </Group>
                                </Box>

                                {showEmptySessions && (
                                    <Stack gap={4} mt={4}>
                                        {emptySessions.map((session) => (
                                            <SessionItem
                                                key={session.chat_session_id}
                                                session={session}
                                                isActive={currentSessionId === session.chat_session_id}
                                                isEditing={editingId === session.chat_session_id}
                                                editTitle={editTitle}
                                                onSelect={() => onSelectSession(session.chat_session_id)}
                                                onStartEdit={() => {
                                                    setEditingId(session.chat_session_id);
                                                    setEditTitle(session.title || "");
                                                }}
                                                onEditTitleChange={setEditTitle}
                                                onEditSave={() => handleRename(session.chat_session_id, true)}
                                                onEditCancel={() => handleRename(session.chat_session_id, false)}
                                                onDelete={() => setDeleteConfirmId(session.chat_session_id)}
                                            />
                                        ))}
                                    </Stack>
                                )}
                            </Box>
                        )}
                    </Stack>
                )}
            </ScrollArea>

            {/* 删除确认弹窗 */}
            <Modal
                opened={deleteConfirmId !== null}
                onClose={() => setDeleteConfirmId(null)}
                title={<Text fw={600} c="white">删除会话</Text>}
                centered
                size="sm"
                styles={{
                    header: { background: "var(--bg-secondary)" },
                    body: { background: "var(--bg-secondary)" },
                    content: { background: "var(--bg-secondary)" },
                }}
            >
                <Text size="sm" c="#98989f" mb="lg">
                    确定要删除这个会话吗？此操作 <Text span c="red" fw={500}>无法撤销</Text>。
                </Text>
                <Group justify="flex-end" gap="sm">
                    <Button variant="subtle" color="gray" onClick={() => setDeleteConfirmId(null)}>
                        取消
                    </Button>
                    <Button color="red" onClick={() => deleteConfirmId && handleDelete(deleteConfirmId)}>
                        删除
                    </Button>
                </Group>
            </Modal>
        </Box>
    );
}
