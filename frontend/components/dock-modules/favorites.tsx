"use client";

import { useDockContext } from "@/lib/dock-context";
import SourcesPanelContent from "../SourcesPanelContent";

export default function FavoritesPanel() {
  const ctx = useDockContext();

  return (
    <SourcesPanelContent
      sessionId={ctx.sessionId ?? ""}
      onBuildDone={ctx.onBuildDone}
      onSelectionChange={ctx.onSelectionChange}
      onOpenASR={ctx.onOpenASR}
      externalVectorUpdate={ctx.externalVectorUpdate}
      workspacePages={ctx.workspacePages}
      onWorkspacePagesChange={ctx.onWorkspacePagesChange}
    />
  );
}
