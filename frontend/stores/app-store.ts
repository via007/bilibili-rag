import { create } from "zustand";
import { ChatMessage, ReasoningStep } from "@/lib/api";

/** 前端内部扩展消息类型（与 ChatPanel 中 LocalChatMessage 对齐） */
export interface LocalChatMessage extends ChatMessage {
  clientId?: string;
  reasoningSteps?: ReasoningStep[];
  hopsUsed?: number;
  avgRecallScore?: number;
}

interface AppState {
  /** 知识库统计刷新信号（替代原 page.tsx 的 statsKey） */
  statsKey: number;
  incrementStatsKey: () => void;

  /** 聊天消息缓存（面板关闭不丢失，重开无需请求后端） */
  chatMessages: LocalChatMessage[];
  setChatMessages: (messages: LocalChatMessage[] | ((prev: LocalChatMessage[]) => LocalChatMessage[])) => void;
  appendChatMessage: (message: LocalChatMessage) => void;
  clearChatMessages: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  statsKey: 0,
  incrementStatsKey: () => set((s) => ({ statsKey: s.statsKey + 1 })),

  chatMessages: [],
  setChatMessages: (messagesOrUpdater) =>
    set((s) => ({
      chatMessages:
        typeof messagesOrUpdater === "function"
          ? (messagesOrUpdater as (prev: LocalChatMessage[]) => LocalChatMessage[])(s.chatMessages)
          : messagesOrUpdater,
    })),
  appendChatMessage: (message) =>
    set((s) => ({ chatMessages: [...s.chatMessages, message] })),
  clearChatMessages: () => set({ chatMessages: [] }),
}));
