import { describe, expect, it } from "vitest";
import { toActivityEventFromWorkflowEvent } from "./workflow";

describe("toActivityEventFromWorkflowEvent", () => {
  it("preserves snapshot and scene references from streamed workflow browser events", () => {
    const normalized = toActivityEventFromWorkflowEvent(
      {
        event_type: "browser_open",
        run_id: "run_browser",
        event_id: "evt_browser",
        title: "Open live source",
        detail: "Opening page",
        timestamp: "2026-03-28T10:00:00Z",
        snapshot_ref: ".maia_agent/browser_captures/source.png",
        scene_ref: "scene_browser_1",
        graph_node_id: "graph_browser_1",
        data: {
          scene_surface: "website",
          url: "https://www.zhihu.com/question/423929401",
        },
      },
      { fallbackRunId: "fallback", index: 1 },
    );

    expect(normalized).toMatchObject({
      event_id: "evt_browser",
      run_id: "run_browser",
      event_type: "browser_open",
      title: "Open live source",
      detail: "Opening page",
      timestamp: "2026-03-28T10:00:00Z",
      snapshot_ref: ".maia_agent/browser_captures/source.png",
      scene_ref: "scene_browser_1",
      graph_node_id: "graph_browser_1",
    });
  });
});
