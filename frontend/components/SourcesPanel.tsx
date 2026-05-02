"use client";

import SourcesPanelContent from "./SourcesPanelContent";
import {
  VectorPageStatusResponse,
  WorkspacePage,
} from "@/lib/api";

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

export default function SourcesPanel(props: Props) {
  return (
    <div className="panel-inner">
      <SourcesPanelContent {...props} />
    </div>
  );
}
