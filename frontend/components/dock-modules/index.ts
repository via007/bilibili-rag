import { BarChart3, BookOpen, FolderHeart, MessageCircle, MessageSquareText, Settings } from "lucide-react";
import { DockModule } from "@/lib/dock-registry";
import ChatPanel from "@/components/ChatPanel";
import FavoritesPanel from "./favorites";
import ChatHistoryPanel from "./chat-history";
import SettingsPanel from "./settings";
import BillingPanel from "./billing";
import QuizPanel from "./quiz";

export const dockModules: DockModule[] = [
  {
    id: "chat",
    icon: MessageCircle,
    title: "对话",
    panel: ChatPanel,
    defaultSize: { width: 1156, height: 640 },
  },
  {
    id: "chat-history",
    icon: MessageSquareText,
    title: "历史会话",
    panel: ChatHistoryPanel,
    defaultSize: { width: 640, height: 520 },
  },
  {
    id: "quiz",
    icon: BookOpen,
    title: "题目练习",
    panel: QuizPanel,
    defaultSize: { width: 720, height: 700 },
  },
  {
    id: "favorites",
    icon: FolderHeart,
    title: "收藏夹",
    panel: FavoritesPanel,
    defaultSize: { width: 570, height: 600 },
  },
  {
    id: "settings",
    icon: Settings,
    title: "API 设置",
    panel: SettingsPanel,
    defaultSize: { width: 1296, height: 806 },
  },
  {
    id: "billing",
    icon: BarChart3,
    title: "用量计费",
    panel: BillingPanel,
    defaultSize: { width: 1156, height: 672 },
  },
];
