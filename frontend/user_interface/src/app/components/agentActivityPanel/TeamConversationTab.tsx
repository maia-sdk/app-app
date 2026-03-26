import { useCallback, useEffect, useMemo, useState } from "react";

import { ConversationPanel } from "@maia/teamchat";
import { listRunCollaboration, type CollaborationEntry } from "../../../api/client";
import type { AgentActivityEvent } from "../../types";
import { deriveFromEvents, filterConversationRows, mergeRows, toTimestamp } from "./teamConversationModel";

type TeamConversationTabProps = {
  runId?: string;
  events: AgentActivityEvent[];
};

export function TeamConversationTab({ runId, events }: TeamConversationTabProps) {
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [remoteRows, setRemoteRows] = useState<CollaborationEntry[]>([]);

  const fallbackRows = useMemo(() => deriveFromEvents(events), [events]);
  const rows = useMemo(
    () => filterConversationRows(mergeRows(remoteRows, fallbackRows)),
    [fallbackRows, remoteRows],
  );
  const latestEventKey = useMemo(() => {
    const lastEvent = events[events.length - 1];
    if (!lastEvent) {
      return "";
    }
    return [
      String(lastEvent.run_id || "").trim(),
      String(lastEvent.event_id || "").trim(),
      String(lastEvent.event_type || "").trim(),
    ].join("|");
  }, [events]);

  const load = useCallback(async () => {
    const normalizedRunId = String(runId || "").trim();
    if (!normalizedRunId) {
      setRemoteRows([]);
      setLoading(false);
      setLoadError("");
      return;
    }
    setLoading(true);
    setLoadError("");
    try {
      const nextRows = await listRunCollaboration(normalizedRunId);
      setRemoteRows(Array.isArray(nextRows) ? nextRows : []);
    } catch (error) {
      const message = String(error || "Failed to load collaboration logs.");
      setLoadError(fallbackRows.length ? "" : message);
      setRemoteRows([]);
    } finally {
      setLoading(false);
    }
  }, [fallbackRows.length, runId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const normalizedRunId = String(runId || "").trim();
    if (!normalizedRunId || rows.length > 0 || !latestEventKey) {
      return;
    }
    const timer = window.setTimeout(() => {
      void load();
    }, 1500);
    return () => window.clearTimeout(timer);
  }, [latestEventKey, load, rows.length, runId]);

  useEffect(() => {
    const normalizedRunId = String(runId || "").trim();
    if (!normalizedRunId) {
      return;
    }
    const lastEvent = events[events.length - 1];
    const lastEventAt = toTimestamp(lastEvent?.ts || lastEvent?.timestamp || Date.now());
    const stillActive = Date.now() - lastEventAt < 30 * 60_000;
    if (!stillActive) {
      return;
    }
    const interval = window.setInterval(() => {
      void load();
    }, 12_000);
    return () => window.clearInterval(interval);
  }, [events, load, runId]);

  return (
    <ConversationPanel
      rows={rows}
      loading={loading}
      loadError={loadError}
      onRefresh={load}
      autoRefreshEnabled
    />
  );
}

