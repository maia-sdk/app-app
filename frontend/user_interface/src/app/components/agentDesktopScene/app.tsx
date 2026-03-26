import {
  AgentDesktopScene as SdkAgentDesktopScene,
  TeamChatSkin,
  parseApiSceneState,
  shouldRenderTeamChatScene,
} from "@maia/theatre";
import { renderRichText } from "../../utils/richText";
import { buildTeamChatMessages } from "./teamChatMessages";
import type { AgentDesktopSceneProps } from "./types";

function compactValue(value: unknown): string {
  if (typeof value === "string") {
    return value.trim();
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value).trim();
  }
  return "";
}

function AgentDesktopScene({
  visibleEvents = [],
  snapshotUrl,
  isBrowserScene,
  isEmailScene,
  isDocumentScene,
  isDocsScene,
  isSheetsScene,
  isSystemScene,
  activeTitle,
  activeDetail,
  activeEventType,
  runId = "",
  activeSceneData,
  ...sceneProps
}: AgentDesktopSceneProps) {
  const actionTarget =
    activeSceneData["action_target"] && typeof activeSceneData["action_target"] === "object"
      ? (activeSceneData["action_target"] as Record<string, unknown>)
      : {};
  const actionTargetLabel =
    compactValue(actionTarget["field_label"]) ||
    compactValue(actionTarget["field"]) ||
    compactValue(actionTarget["selector"]) ||
    compactValue(actionTarget["title"]) ||
    compactValue(actionTarget["url"]) ||
    compactValue(actionTarget["source_name"]);
  const actionStatus = compactValue(activeSceneData["action_status"]).toLowerCase();
  const shouldRenderTeamChatSkin = shouldRenderTeamChatScene({
    activeEventType,
    activeSceneData,
    apiSceneActive: parseApiSceneState({
      activeSceneData,
      activeEventType,
      actionTargetLabel,
      actionStatus,
      sceneText: sceneProps.sceneText,
      activeDetail,
    }).isApiScene,
    isBrowserScene,
    isDocsScene,
    isDocumentScene,
    isEmailScene,
    isSheetsScene,
    isSystemScene,
    snapshotUrl,
  });
  const teamChatScene = shouldRenderTeamChatSkin ? (
    <TeamChatSkin
      messages={buildTeamChatMessages(visibleEvents, activeSceneData, activeDetail)}
      topic={String(activeSceneData?.topic || activeTitle || "")}
      runId={runId || ""}
    />
  ) : null;

  return (
    <SdkAgentDesktopScene
      {...sceneProps}
      snapshotUrl={snapshotUrl}
      isBrowserScene={isBrowserScene}
      isEmailScene={isEmailScene}
      isDocumentScene={isDocumentScene}
      isDocsScene={isDocsScene}
      isSheetsScene={isSheetsScene}
      isSystemScene={isSystemScene}
      activeTitle={activeTitle}
      activeDetail={activeDetail}
      activeEventType={activeEventType}
      runId={runId}
      activeSceneData={activeSceneData}
      renderRichText={renderRichText}
      teamChatScene={teamChatScene}
    />
  );
}

export { AgentDesktopScene };
