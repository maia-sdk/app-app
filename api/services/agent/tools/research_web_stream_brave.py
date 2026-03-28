from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import base64
from urllib.parse import parse_qs, urlparse
from typing import Any, Callable

from api.services.agent.connectors.computer_use_browser_helpers import write_snapshot
from api.services.agent.tools.base import ToolExecutionContext, ToolTraceEvent
from api.services.agent.tools.research_helpers import (
    classify_provider_failure as _classify_provider_failure,
    fuse_search_results as _fuse_search_results,
    safe_snippet as _safe_snippet,
    score_results_relevance_llm as _score_results_relevance_llm,
)
from api.services.agent.tools.research_web_helpers import (
    _apply_domain_scope,
    _hostname_label,
    _search_results_url,
    _website_scene_payload,
)
from api.services.computer_use.session_registry import get_session_registry


def _unwrap_search_result_url(url: str, *, provider_host: str) -> str:
    cleaned = str(url or "").strip()
    if not cleaned.startswith(("http://", "https://")):
        return ""
    host = str(urlparse(cleaned).hostname or "").strip().lower()
    if host.startswith("www."):
        host = host[4:]
    if provider_host == "bing.com" and host == "bing.com":
        parsed = urlparse(cleaned)
        encoded = parse_qs(parsed.query or "", keep_blank_values=False).get("u", [""])[0]
        encoded = str(encoded or "").strip()
        if encoded.startswith("a1"):
            payload = encoded[2:]
            payload += "=" * (-len(payload) % 4)
            try:
                decoded = base64.b64decode(payload).decode("utf-8", errors="ignore").strip()
            except Exception:
                decoded = ""
            if decoded.startswith(("http://", "https://")):
                cleaned = decoded
    return cleaned


def _is_result_like_url(url: str, *, provider_host: str) -> bool:
    cleaned = _unwrap_search_result_url(url, provider_host=provider_host)
    if not cleaned.startswith(("http://", "https://")):
        return False
    host = str(urlparse(cleaned).hostname or "").strip().lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return False
    if provider_host and (host == provider_host or host.endswith(f".{provider_host}")):
        return False
    lowered = cleaned.lower()
    if lowered.startswith(("javascript:", "mailto:", "tel:")):
        return False
    return True


def _run_computer_use_search_variant(
    *,
    context: ToolExecutionContext,
    query_variant: str,
    variant_index: int,
    total_variants: int,
    result_limit: int,
    search_url: str,
    max_live_clicks_per_query: int,
    trace_events: list[ToolTraceEvent],
) -> list[dict[str, Any]]:
    registry = get_session_registry()
    user_id = str(context.settings.get("__agent_user_id") or context.settings.get("agent.tenant_id") or "default").strip() or "default"
    session = registry.create(user_id=user_id, start_url=search_url)
    provider_host = str(urlparse(search_url).hostname or "").strip().lower()
    if provider_host.startswith("www."):
        provider_host = provider_host[4:]
    try:
        session.navigate(search_url)
        open_snapshot = write_snapshot(screenshot_b64=session.screenshot_b64(), label=f"search-{variant_index}-open")
        open_event = ToolTraceEvent(
            event_type="browser_open",
            title=f"Open live search results {variant_index}/{total_variants}",
            detail=_safe_snippet(query_variant, 140),
            data=_website_scene_payload(
                lane="search-results-open-live",
                primary_index=variant_index,
                payload={
                    "provider": "computer_use_browser",
                    "query": query_variant,
                    "variant_index": variant_index,
                    "url": search_url,
                    "source_url": search_url,
                    "render_quality": "live",
                    "computer_use_session_id": session.session_id,
                },
            ),
            snapshot_ref=open_snapshot or None,
        )
        trace_events.append(open_event)
        yield open_event

        discovered: list[dict[str, Any]] = []
        for scroll_step, metrics in enumerate(session.scroll_through_page(max_steps=3), start=1):
            scroll_snapshot = write_snapshot(
                screenshot_b64=session.screenshot_b64(),
                label=f"search-{variant_index}-scroll-{scroll_step}",
            )
            scroll_event = ToolTraceEvent(
                event_type="browser_scroll",
                title=f"Scroll live search results {scroll_step}",
                detail=f"Scanning results ({int(round(float(metrics.get('scroll_percent') or 0.0)))}%)",
                data=_website_scene_payload(
                    lane="search-results-scroll-live",
                    primary_index=variant_index,
                    secondary_index=scroll_step,
                    payload={
                        "provider": "computer_use_browser",
                        "query": query_variant,
                        "variant_index": variant_index,
                        "url": search_url,
                        "source_url": search_url,
                        "scroll_percent": float(metrics.get("scroll_percent") or 0.0),
                        "scroll_direction": "down",
                        "computer_use_session_id": session.session_id,
                    },
                ),
                snapshot_ref=scroll_snapshot or None,
            )
            trace_events.append(scroll_event)
            yield scroll_event
            for row in session.extract_links(limit=max(12, result_limit * 2)):
                url = _unwrap_search_result_url(str(row.get("url") or "").strip(), provider_host=provider_host)
                if not _is_result_like_url(url, provider_host=provider_host):
                    continue
                if any(str(existing.get("url") or "") == url for existing in discovered):
                    continue
                discovered.append(
                    {
                        "url": url,
                        "title": str(row.get("title") or url).strip(),
                        "description": str(row.get("text") or "").strip(),
                        "source": "computer_use_browser",
                    }
                )
                if len(discovered) >= max(12, result_limit * 2):
                    break
            if len(discovered) >= max(6, result_limit):
                break

        ranked = _score_results_relevance_llm(
            query=query_variant,
            results=discovered,
            min_score=0.18,
            batch_size=12,
        )[: max(1, result_limit)]

        for rank, row in enumerate(ranked[: max(1, max_live_clicks_per_query)], start=1):
            clicked_url = str(row.get("url") or "").strip()
            if not clicked_url:
                continue
            host_label = _hostname_label(clicked_url)
            click_event = ToolTraceEvent(
                event_type="browser_click",
                title=f"Select live result {rank}",
                detail=(f"Open {host_label}" if host_label else f"Open result {rank}"),
                data=_website_scene_payload(
                    lane="search-result-click-live",
                    primary_index=variant_index,
                    secondary_index=rank,
                    payload={
                        "provider": "computer_use_browser",
                        "query": query_variant,
                        "variant_index": variant_index,
                        "result_rank": rank,
                        "url": search_url,
                        "source_url": search_url,
                        "target_url": clicked_url,
                        "computer_use_session_id": session.session_id,
                    },
                ),
                snapshot_ref=open_snapshot or None,
            )
            trace_events.append(click_event)
            yield click_event

            opened_snapshot = open_snapshot
            opened_title = ""
            try:
                opened_title = session.navigate(clicked_url)
                opened_snapshot = write_snapshot(
                    screenshot_b64=session.screenshot_b64(),
                    label=f"search-{variant_index}-source-{rank}",
                )
            except Exception as exc:
                failure_event = ToolTraceEvent(
                    event_type="tool_failed",
                    title=f"Open live source {rank} failed",
                    detail=_safe_snippet(str(exc) or clicked_url, 160),
                    data={
                        "provider": "computer_use_browser",
                        "query": query_variant,
                        "variant_index": variant_index,
                        "result_rank": rank,
                        "url": clicked_url,
                        "source_url": clicked_url,
                        "computer_use_session_id": session.session_id,
                    },
                )
                trace_events.append(failure_event)
                yield failure_event
                continue

            opened_event = ToolTraceEvent(
                event_type="web_result_opened",
                title=f"Open live source {rank}",
                detail=_safe_snippet(opened_title or clicked_url, 140),
                data=_website_scene_payload(
                    lane="source-opened-live",
                    primary_index=variant_index,
                    secondary_index=rank,
                    payload={
                        "provider": "computer_use_browser",
                        "query": query_variant,
                        "variant_index": variant_index,
                        "result_rank": rank,
                        "url": clicked_url,
                        "source_url": clicked_url,
                        "title": opened_title,
                        "computer_use_session_id": session.session_id,
                    },
                ),
                snapshot_ref=opened_snapshot or None,
            )
            trace_events.append(opened_event)
            yield opened_event

            source_open_event = ToolTraceEvent(
                event_type="browser_open",
                title=f"Load live source {rank}",
                detail=_safe_snippet(opened_title or clicked_url, 140),
                data=_website_scene_payload(
                    lane="source-open-live",
                    primary_index=variant_index,
                    secondary_index=rank,
                    payload={
                        "provider": "computer_use_browser",
                        "query": query_variant,
                        "variant_index": variant_index,
                        "result_rank": rank,
                        "url": clicked_url,
                        "source_url": clicked_url,
                        "title": opened_title,
                        "computer_use_session_id": session.session_id,
                    },
                ),
                snapshot_ref=opened_snapshot or None,
            )
            trace_events.append(source_open_event)
            yield source_open_event

            source_scroll_steps = session.scroll_through_page(max_steps=1)
            for source_scroll_index, metrics in enumerate(source_scroll_steps, start=1):
                source_scroll_snapshot = write_snapshot(
                    screenshot_b64=session.screenshot_b64(),
                    label=f"search-{variant_index}-source-{rank}-scroll-{source_scroll_index}",
                )
                source_scroll_event = ToolTraceEvent(
                    event_type="browser_scroll",
                    title=f"Scroll live source {rank}",
                    detail=f"Verifying page ({int(round(float(metrics.get('scroll_percent') or 0.0)))}%)",
                    data=_website_scene_payload(
                        lane="source-scroll-live",
                        primary_index=variant_index,
                        secondary_index=rank,
                        payload={
                            "provider": "computer_use_browser",
                            "query": query_variant,
                            "variant_index": variant_index,
                            "result_rank": rank,
                            "url": clicked_url,
                            "source_url": clicked_url,
                            "title": opened_title,
                            "scroll_percent": float(metrics.get("scroll_percent") or 0.0),
                            "scroll_direction": "down",
                            "computer_use_session_id": session.session_id,
                        },
                    ),
                    snapshot_ref=source_scroll_snapshot or opened_snapshot or None,
                )
                trace_events.append(source_scroll_event)
                yield source_scroll_event

        return ranked
    finally:
        registry.close(session.session_id)


def run_brave_provider_stage(
    *,
    context: ToolExecutionContext,
    requested_provider: str,
    search_plan: list[tuple[str, int]],
    planned_result_budget: int,
    requested_search_budget: int,
    query_variants: list[str],
    max_live_queries: int,
    max_live_clicks_per_query: int,
    domain_scope_hosts: list[str],
    domain_scope_mode: str,
    min_unique_sources: int,
    fused_top_k: int,
    query: str,
    trace_events: list[ToolTraceEvent],
    state: dict[str, Any],
    get_connector_registry_fn: Callable[..., Any],
):
    get_connector_registry = get_connector_registry_fn
    payload: dict[str, Any] = state.get("payload") if isinstance(state.get("payload"), dict) else {}
    used_provider = str(state.get("used_provider") or requested_provider)
    ok = bool(state.get("ok"))
    search_runs = state.get("search_runs")
    if not isinstance(search_runs, list):
        search_runs = []
    provider_failures = state.get("provider_failures")
    if not isinstance(provider_failures, list):
        provider_failures = []
    provider_attempted = state.get("provider_attempted")
    if not isinstance(provider_attempted, list):
        provider_attempted = []
    domain_scope_filtered_out = int(state.get("domain_scope_filtered_out") or 0)
    if requested_provider == "brave_search":
        try:
            provider_attempted.append("brave_search")
            trace_events.append(
                ToolTraceEvent(
                    event_type="api_call_started",
                    title="Call Brave Search API",
                    detail=(
                        f"Running {len(search_plan)} query variant(s) "
                        f"with {planned_result_budget} total result slots"
                    ),
                    data={
                        "provider": "brave_search",
                        "search_budget_requested": requested_search_budget,
                        "search_budget_effective": planned_result_budget,
                    },
                )
            )
            yield trace_events[-1]
            brave_settings = context.settings
            scheduled_queries: list[tuple[int, str, int, str]] = []
            for idx, (query_variant, per_query_limit) in enumerate(search_plan, start=1):
                search_url = _search_results_url("brave_search", query_variant)
                scheduled_queries.append((idx, query_variant, per_query_limit, search_url))
                if idx <= max_live_queries and search_url:
                    live_navigate_event = ToolTraceEvent(
                        event_type="browser_navigate",
                        title=f"Open Brave results {idx}/{len(query_variants)}",
                        detail=_safe_snippet(query_variant, 140),
                        data=_website_scene_payload(
                            lane="search-results-open",
                            primary_index=idx,
                            payload={
                                "provider": "brave_search",
                                "query": query_variant,
                                "variant_index": idx,
                                "url": search_url,
                                "source_url": search_url,
                                "render_quality": "live",
                            },
                        ),
                    )
                    trace_events.append(live_navigate_event)
                    yield live_navigate_event
                query_event = ToolTraceEvent(
                    event_type="brave.search.query",
                    title=f"Run Brave query {idx}/{len(query_variants)}",
                    detail=_safe_snippet(query_variant, 140),
                    data={
                        "query": query_variant,
                        "variant_index": idx,
                        "provider": "brave_search",
                        "result_limit": per_query_limit,
                    },
                )
                trace_events.append(query_event)
                yield query_event
            def _run_search_variant(
                variant_query: str,
                variant_limit: int,
            ) -> dict[str, Any]:
                brave = get_connector_registry().build("brave_search", settings=brave_settings)
                return brave.web_search(query=variant_query, count=variant_limit)

            max_workers = max(1, min(len(scheduled_queries), 4))
            future_map = {}
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for idx, query_variant, per_query_limit, search_url in scheduled_queries:
                    future = executor.submit(_run_search_variant, query_variant, per_query_limit)
                    future_map[future] = (idx, query_variant, per_query_limit, search_url)

                for future in as_completed(future_map):
                    idx, query_variant, per_query_limit, search_url = future_map[future]
                    run_payload = future.result()
                    if not isinstance(run_payload, dict):
                        continue
                    run_payload["query_variant"] = query_variant
                    run_payload["result_limit"] = per_query_limit
                    run_rows = run_payload.get("results") if isinstance(run_payload.get("results"), list) else []
                    scoped_rows, dropped_count = _apply_domain_scope(
                        rows=[row for row in run_rows if isinstance(row, dict)],
                        domain_scope_hosts=domain_scope_hosts,
                        domain_scope_mode=domain_scope_mode,
                    )
                    domain_scope_filtered_out += int(dropped_count)
                    scoped_payload = dict(run_payload)
                    scoped_payload["results"] = scoped_rows
                    search_runs.append(scoped_payload)
                    run_urls = [
                        str(item.get("url") or "")
                        for item in scoped_rows
                        if isinstance(item, dict)
                    ][:5]
                    result_event = ToolTraceEvent(
                        event_type="brave.search.results",
                        title=f"Brave results for query {idx}",
                        detail=f"Captured {len(run_urls)} URL(s) from limit {per_query_limit}",
                        data={
                            "query": query_variant,
                            "top_urls": run_urls,
                            "provider": "brave_search",
                            "result_limit": per_query_limit,
                            "domain_scope_filtered_out": int(dropped_count),
                        },
                    )
                    trace_events.append(result_event)
                    yield result_event
                    if idx <= max_live_queries and search_url:
                        hover_event = ToolTraceEvent(
                            event_type="browser_hover",
                            title=f"Hover search results {idx}/{len(query_variants)}",
                            detail="Reviewing top-ranked result cards",
                            data=_website_scene_payload(
                                lane="search-results-hover",
                                primary_index=idx,
                                payload={
                                    "provider": "brave_search",
                                    "query": query_variant,
                                    "variant_index": idx,
                                    "url": search_url,
                                    "source_url": search_url,
                                },
                            ),
                        )
                        trace_events.append(hover_event)
                        yield hover_event
                        scroll_targets = [14.0, 36.0, 62.0]
                        if len(scoped_rows) >= 8:
                            scroll_count = 3
                        elif len(scoped_rows) >= 4:
                            scroll_count = 2
                        else:
                            scroll_count = 1
                        for scroll_step, scroll_percent in enumerate(scroll_targets[:scroll_count], start=1):
                            scroll_event = ToolTraceEvent(
                                event_type="browser_scroll",
                                title=f"Scroll Brave results {scroll_step}/{scroll_count}",
                                detail=f"Reviewing result cards ({int(round(scroll_percent))}%)",
                                data=_website_scene_payload(
                                    lane="search-results-scroll",
                                    primary_index=idx,
                                    secondary_index=scroll_step,
                                    payload={
                                        "provider": "brave_search",
                                        "query": query_variant,
                                        "variant_index": idx,
                                        "url": search_url,
                                        "source_url": search_url,
                                        "scroll_percent": float(scroll_percent),
                                        "scroll_direction": "down",
                                    },
                                ),
                            )
                            trace_events.append(scroll_event)
                            yield scroll_event
                        for rank, clicked_url in enumerate(run_urls[:max_live_clicks_per_query], start=1):
                            if not clicked_url:
                                continue
                            host_label = _hostname_label(clicked_url)
                            result_click_event = ToolTraceEvent(
                                event_type="browser_click",
                                title=f"Click result {rank}",
                                detail=(f"Open {host_label}" if host_label else f"Open result {rank}"),
                                data=_website_scene_payload(
                                    lane="search-result-click",
                                    primary_index=idx,
                                    secondary_index=rank,
                                    payload={
                                        "provider": "brave_search",
                                        "query": query_variant,
                                        "variant_index": idx,
                                        "result_rank": rank,
                                        "selector": f"result_rank_{rank}",
                                        "url": search_url,
                                        "source_url": search_url,
                                        "target_url": clicked_url,
                                    },
                                ),
                            )
                            trace_events.append(result_click_event)
                            yield result_click_event
                            click_event = ToolTraceEvent(
                                event_type="web_result_opened",
                                title=f"Open result {rank}",
                                detail=(f"Opening {host_label}" if host_label else f"Opening result {rank}"),
                                data=_website_scene_payload(
                                    lane="source-opened",
                                    primary_index=idx,
                                    secondary_index=rank,
                                    payload={
                                        "provider": "brave_search",
                                        "query": query_variant,
                                        "variant_index": idx,
                                        "result_rank": rank,
                                        "url": clicked_url,
                                        "source_url": clicked_url,
                                    },
                                ),
                            )
                            trace_events.append(click_event)
                            yield click_event
                            open_event = ToolTraceEvent(
                                event_type="browser_navigate",
                                title=f"Open source page {rank}",
                                detail=_safe_snippet(clicked_url, 140),
                                data=_website_scene_payload(
                                    lane="source-navigate",
                                    primary_index=idx,
                                    secondary_index=rank,
                                    payload={
                                        "provider": "brave_search",
                                        "query": query_variant,
                                        "variant_index": idx,
                                        "result_rank": rank,
                                        "url": clicked_url,
                                        "source_url": clicked_url,
                                        "render_quality": "live",
                                    },
                                ),
                            )
                            trace_events.append(open_event)
                            yield open_event
                            source_scroll_percent = min(92.0, 24.0 + (rank * 22.0))
                            source_scroll_event = ToolTraceEvent(
                                event_type="browser_scroll",
                                title=f"Scroll source page {rank}",
                                detail=f"Scanning source evidence ({int(round(source_scroll_percent))}%)",
                                data=_website_scene_payload(
                                    lane="source-scroll",
                                    primary_index=idx,
                                    secondary_index=rank,
                                    payload={
                                        "provider": "brave_search",
                                        "query": query_variant,
                                        "variant_index": idx,
                                        "result_rank": rank,
                                        "url": clicked_url,
                                        "source_url": clicked_url,
                                        "scroll_percent": float(source_scroll_percent),
                                        "scroll_direction": "down",
                                    },
                                ),
                            )
                            trace_events.append(source_scroll_event)
                            yield source_scroll_event
                            source_preview = ""
                            if rank - 1 < len(scoped_rows) and isinstance(scoped_rows[rank - 1], dict):
                                source_preview = str(
                                    scoped_rows[rank - 1].get("description")
                                    or scoped_rows[rank - 1].get("snippet")
                                    or ""
                                ).strip()
                            extract_event = ToolTraceEvent(
                                event_type="browser_extract",
                                title=f"Extract source evidence {rank}",
                                detail=_safe_snippet(source_preview or clicked_url, 140),
                                data=_website_scene_payload(
                                    lane="source-extract",
                                    primary_index=idx,
                                    secondary_index=rank,
                                    payload={
                                        "provider": "brave_search",
                                        "query": query_variant,
                                        "variant_index": idx,
                                        "result_rank": rank,
                                        "url": clicked_url,
                                        "source_url": clicked_url,
                                        "text_excerpt": _safe_snippet(source_preview, 260),
                                    },
                                ),
                            )
                            trace_events.append(extract_event)
                            yield extract_event

            fused_results = _fuse_search_results(search_runs, top_k=fused_top_k)
            payload = {"results": fused_results, "query": query, "provider": "brave_fused"}
            used_provider = "brave_search"
            ok = True
            fused_event = ToolTraceEvent(
                event_type="retrieval_fused",
                title="Fuse search runs",
                detail=f"Reduced {sum(len(run.get('results') or []) for run in search_runs)} raw rows to {len(fused_results)} fused results",
                data={
                    "query_variants": query_variants,
                    "result_count": len(fused_results),
                    "target_source_count": min_unique_sources,
                    "fused_top_k": fused_top_k,
                    "search_budget_requested": requested_search_budget,
                    "search_budget_effective": planned_result_budget,
                    "domain_scope_hosts": domain_scope_hosts[:6],
                    "domain_scope_mode": domain_scope_mode,
                    "domain_scope_filtered_out": int(domain_scope_filtered_out),
                },
            )
            trace_events.append(fused_event)
            yield fused_event
            trace_events.append(
                ToolTraceEvent(
                    event_type="api_call_completed",
                    title="Brave Search API completed",
                    detail=f"Collected {len(fused_results)} fused result(s)",
                    data={
                        "provider": "brave_search",
                        "result_count": len(fused_results),
                        "provider_requested": requested_provider,
                    },
                )
            )
            yield trace_events[-1]
        except Exception as exc:
            failure = _classify_provider_failure(exc)
            failure["provider"] = "brave_search"
            provider_failures.append(failure)
            trace_events.append(
                ToolTraceEvent(
                    event_type="tool_failed",
                    title="Brave provider failed",
                    detail=f"{failure['reason']}: {failure['message']}",
                    data=failure,
                )
            )
            yield trace_events[-1]
            ok = False
            search_runs = []
            scheduled_queries = [
                (idx, query_variant, per_query_limit, _search_results_url("bing_search", query_variant))
                for idx, (query_variant, per_query_limit) in enumerate(search_plan, start=1)
            ]
            try:
                trace_events.append(
                    ToolTraceEvent(
                        event_type="tool_progress",
                        title="Falling back to Maia computer live search",
                        detail="Search API unavailable; using Maia computer to search the web live.",
                        data={
                            "provider_requested": "brave_search",
                            "fallback_provider": "computer_use_browser",
                            "failure_reason": failure.get("reason"),
                        },
                    )
                )
                yield trace_events[-1]
                for idx, query_variant, per_query_limit, search_url in scheduled_queries:
                    if not search_url:
                        continue
                    ranked_rows = yield from _run_computer_use_search_variant(
                        context=context,
                        query_variant=query_variant,
                        variant_index=idx,
                        total_variants=len(query_variants),
                        result_limit=per_query_limit,
                        search_url=search_url,
                        max_live_clicks_per_query=max_live_clicks_per_query,
                        trace_events=trace_events,
                    )
                    scoped_rows, dropped_count = _apply_domain_scope(
                        rows=[row for row in ranked_rows if isinstance(row, dict)],
                        domain_scope_hosts=domain_scope_hosts,
                        domain_scope_mode=domain_scope_mode,
                    )
                    domain_scope_filtered_out += int(dropped_count)
                    search_runs.append(
                        {
                            "query_variant": query_variant,
                            "result_limit": per_query_limit,
                            "results": scoped_rows,
                        }
                    )
                    trace_events.append(
                        ToolTraceEvent(
                            event_type="tool_progress",
                            title=f"Collected live search results {idx}/{len(query_variants)}",
                            detail=f"Maia computer captured {len(scoped_rows)} source URL(s)",
                            data={
                                "provider": "computer_use_browser",
                                "query": query_variant,
                                "variant_index": idx,
                                "result_count": len(scoped_rows),
                                "domain_scope_filtered_out": int(dropped_count),
                            },
                        )
                    )
                    yield trace_events[-1]
                fused_results = _fuse_search_results(search_runs, top_k=fused_top_k)
                if fused_results:
                    payload = {"results": fused_results, "query": query, "provider": "computer_use_browser"}
                    used_provider = "computer_use_browser"
                    ok = True
                    trace_events.append(
                        ToolTraceEvent(
                            event_type="retrieval_fused",
                            title="Fuse live Maia computer search runs",
                            detail=f"Reduced {sum(len(run.get('results') or []) for run in search_runs)} raw rows to {len(fused_results)} fused results",
                            data={
                                "query_variants": query_variants,
                                "result_count": len(fused_results),
                                "target_source_count": min_unique_sources,
                                "fused_top_k": fused_top_k,
                                "provider": "computer_use_browser",
                            },
                        )
                    )
                    yield trace_events[-1]
            except Exception as fallback_exc:
                fallback_failure = _classify_provider_failure(fallback_exc)
                fallback_failure["provider"] = "computer_use_browser"
                provider_failures.append(fallback_failure)
                trace_events.append(
                    ToolTraceEvent(
                        event_type="tool_failed",
                        title="Maia computer live search failed",
                        detail=f"{fallback_failure['reason']}: {fallback_failure['message']}",
                        data=fallback_failure,
                    )
                )
                yield trace_events[-1]

    state["payload"] = payload
    state["used_provider"] = used_provider
    state["ok"] = ok
    state["search_runs"] = search_runs
    state["provider_failures"] = provider_failures
    state["provider_attempted"] = provider_attempted
    state["domain_scope_filtered_out"] = int(domain_scope_filtered_out)
