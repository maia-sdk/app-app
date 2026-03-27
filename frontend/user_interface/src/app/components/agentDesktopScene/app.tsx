import {
  AgentDesktopScene as SdkAgentDesktopScene,
  parseApiSceneState,
} from "@maia/theatre";
import { renderRichText } from "../../utils/richText";
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
    />
  );
}

export { AgentDesktopScene };
