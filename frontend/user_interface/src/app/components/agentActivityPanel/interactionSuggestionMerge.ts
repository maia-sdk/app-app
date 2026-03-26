export {
  extractSuggestionLayer,
  INTERACTION_SUGGESTION_MIN_CONFIDENCE,
  isInteractionSuggestionEvent,
  mergeSuggestion,
  suggestionLookupKeyForEvent,
} from "@maia/theatre";
export type {
  AgentActivityInteractionSuggestion as InteractionSuggestion,
  AgentActivityInteractionSuggestionRejectReason as InteractionSuggestionRejectReason,
  AgentActivityMergedInteractionSource as MergedInteractionSource,
  AgentActivityMergedInteractionState as MergedInteractionState,
} from "@maia/theatre";
