import { useMemo } from "react";
import { getRawFileUrl } from "../../../api/client";
import { deriveAgentActivityState } from "@maia/theatre";
import type { ChatAttachment } from "../../types";
import type { PreviewTab } from "../agentActivityMeta";
import { resolveSceneSnapshotUrl } from "./contentDerivation";
import type { AgentActivityEvent } from "../../types";

interface UseAgentActivityDerivedParams {
  events: AgentActivityEvent[];
  cursor: number;
  previewTab: PreviewTab;
  stageAttachment?: ChatAttachment;
  snapshotFailedEventId: string;
  streaming: boolean;
}

function useAgentActivityDerived({
  events,
  cursor,
  previewTab,
  stageAttachment,
  snapshotFailedEventId,
  streaming,
}: UseAgentActivityDerivedParams) {
  return useMemo(
    () =>
      deriveAgentActivityState({
        events,
        cursor,
        previewTab,
        stageAttachment,
        snapshotFailedEventId,
        streaming,
        resolveSceneSnapshotUrl,
        resolveStageFileUrl: (fileId) => getRawFileUrl(fileId),
      }),
    [cursor, events, previewTab, snapshotFailedEventId, stageAttachment, streaming],
  );
}

export { useAgentActivityDerived };
