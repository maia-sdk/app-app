import { getAgentEventSnapshotUrl } from "../../../api/client";
import {
  resolveBrowserUrl,
  resolveDocBodyHint,
  resolveEmailBodyHint,
  resolveEmailRecipient,
  resolveEmailSubject,
  resolveSheetBodyHint,
  readStringField,
} from "@maia/theatre";
import type { AgentActivityEvent } from "../../types";

function resolveSceneSnapshotUrl(
  sceneEvent: AgentActivityEvent | null,
  visibleEvents: AgentActivityEvent[],
): string {
  const resolveSnapshot = (event: AgentActivityEvent | null): string => {
    if (!event) return "";
    const raw = readStringField(event.snapshot_ref);
    if (!raw) return "";
    if (raw.startsWith("http://") || raw.startsWith("https://") || raw.startsWith("data:image/")) {
      return raw;
    }
    if (!event.run_id || !event.event_id) {
      return "";
    }
    return getAgentEventSnapshotUrl(event.run_id, event.event_id);
  };

  const preferred = resolveSnapshot(sceneEvent);
  if (preferred) {
    return preferred;
  }
  for (let idx = visibleEvents.length - 1; idx >= 0; idx -= 1) {
    const fallback = resolveSnapshot(visibleEvents[idx]);
    if (fallback) {
      return fallback;
    }
  }
  return "";
}

export {
  resolveBrowserUrl,
  resolveDocBodyHint,
  resolveEmailBodyHint,
  resolveEmailRecipient,
  resolveEmailSubject,
  resolveSceneSnapshotUrl,
  resolveSheetBodyHint,
};
