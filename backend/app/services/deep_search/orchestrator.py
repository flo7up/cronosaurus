"""
Deep search orchestrator — the core iterative research loop.

This module is called by the tool handler (deep_search_tools.py).
It coordinates: plan → search → collect → analyse → refine → synthesise.
"""

import logging
import time
from typing import Any

from app.services.deep_search.research_workspace import (
    ResearchWorkspace,
    SubQuestion,
    Finding,
    Contradiction,
)
from app.services.deep_search import research_collector

logger = logging.getLogger(__name__)

# ── Depth presets ───────────────────────────────────────────────

_DEPTH_PRESETS: dict[str, dict[str, int]] = {
    "light":  {"max_iterations": 1, "max_sources": 6,  "max_pages_per_query": 2},
    "medium": {"max_iterations": 3, "max_sources": 12, "max_pages_per_query": 3},
    "deep":   {"max_iterations": 5, "max_sources": 20, "max_pages_per_query": 4},
}


def run(
    query: str,
    api_key: str,
    engine_id: str,
    *,
    depth: str = "medium",
    max_iterations: int | None = None,
    max_sources: int | None = None,
    time_budget_seconds: int | None = None,
) -> dict[str, Any]:
    """Execute a full deep-search session and return the final result dict."""

    preset = _DEPTH_PRESETS.get(depth, _DEPTH_PRESETS["medium"])
    max_iter = max_iterations or preset["max_iterations"]
    max_src = max_sources or preset["max_sources"]
    pages_per_q = preset["max_pages_per_query"]
    budget = time_budget_seconds or 90
    start = time.monotonic()

    # 1 — Create workspace + initial plan
    ws = ResearchWorkspace(main_query=query)
    _generate_plan(ws)
    logger.info("Deep search plan for '%s': %d sub-questions", query, len(ws.sub_questions))

    # 2 — Iterative loop
    for i in range(max_iter):
        ws.iteration_count += 1
        elapsed = time.monotonic() - start
        if elapsed > budget:
            logger.info("Deep search time budget exhausted (%.1fs)", elapsed)
            break

        unresolved = ws.get_unresolved()
        if not unresolved:
            logger.info("All sub-questions resolved after %d iterations", i + 1)
            break

        # Generate queries for this iteration
        queries = _generate_queries(ws, unresolved, iteration=i)

        # Collect evidence
        stats = research_collector.collect(
            ws, queries, api_key, engine_id,
            max_results_per_query=5,
            max_pages_to_fetch=pages_per_q,
        )
        logger.info(
            "Deep search iter %d: %d queries, %d new sources, %d pages",
            i + 1, stats["queries_run"], stats["new_sources"], stats["pages_fetched"],
        )

        # Cap total sources
        if len(ws.sources) >= max_src:
            logger.info("Source cap reached (%d)", max_src)

        # Analyse current state
        _analyse_workspace(ws)

        # Check diminishing returns
        if stats["new_sources"] == 0:
            logger.info("No new sources — stopping early")
            break

    # 3 — Synthesise
    return _synthesise(ws)


# ── Plan generation ─────────────────────────────────────────────


def _generate_plan(ws: ResearchWorkspace) -> None:
    """Decompose the main query into sub-questions.

    Uses simple heuristics rather than an LLM call so that the tool
    works without spending an extra LLM round-trip.  The decomposition
    covers common research axes: definition, perspectives, evidence,
    tradeoffs, recency.
    """
    q = ws.main_query
    ws.sub_questions = [
        SubQuestion(id="sq1", question=f"What is {q}? Core definition and context.", priority="high"),
        SubQuestion(id="sq2", question=f"What are the main approaches or perspectives on {q}?", priority="high"),
        SubQuestion(id="sq3", question=f"What evidence or data supports each perspective on {q}?", priority="medium"),
        SubQuestion(id="sq4", question=f"What are the tradeoffs, risks, or criticisms related to {q}?", priority="medium"),
        SubQuestion(id="sq5", question=f"What are the most recent developments or updates on {q}?", priority="low"),
    ]


# ── Query generation ────────────────────────────────────────────


def _generate_queries(
    ws: ResearchWorkspace,
    unresolved: list[SubQuestion],
    *,
    iteration: int,
) -> list[str]:
    """Generate search queries for the next iteration.

    First iteration: broad queries based on sub-questions.
    Later iterations: narrow refinement queries targeting gaps.
    """
    queries: list[str] = []

    if iteration == 0:
        # Broad discovery
        queries.append(ws.main_query)
        for sq in unresolved[:3]:
            queries.append(sq.question)
    else:
        # Targeted refinement
        for sq in unresolved:
            if sq.priority == "high":
                queries.append(sq.question)
        # Add gap-targeted queries
        for gap in ws.gaps[:2]:
            queries.append(gap)
        # Add contradiction-resolution queries
        for c in ws.contradictions[:1]:
            queries.append(f"{c.claim_a} vs {c.claim_b}")

    # Deduplicate against already-executed queries
    seen = set(ws.queries_executed)
    return [q for q in queries if q not in seen]


# ── Workspace analysis ──────────────────────────────────────────


def _analyse_workspace(ws: ResearchWorkspace) -> None:
    """Inspect collected sources and update findings / gaps / resolutions.

    This is a heuristic pass — it maps sources back to sub-questions
    based on simple keyword overlap.
    """
    for sq in ws.sub_questions:
        if sq.status == "resolved":
            continue

        sq_words = set(sq.question.lower().split())
        matching_sources: list[Source] = []

        for src in ws.sources:
            text = (src.snippet + " " + src.extracted_text).lower()
            overlap = sq_words & set(text.split())
            if len(overlap) >= min(3, len(sq_words) // 2 + 1):
                matching_sources.append(src)

        if matching_sources:
            # Record a finding
            claim = f"Evidence found for: {sq.question}"
            finding = Finding(
                sub_question_id=sq.id,
                claim=claim,
                supporting_sources=[s.url for s in matching_sources[:5]],
                confidence=min(0.5 + 0.1 * len(matching_sources), 0.95),
            )
            ws.add_finding(finding)

            # Resolve if enough evidence
            if len(matching_sources) >= 2:
                ws.mark_resolved(sq.id)
        else:
            ws.record_gap(f"No evidence found for: {sq.question}")


# ── Synthesis ───────────────────────────────────────────────────

from app.services.deep_search.research_workspace import Source  # noqa: E402 (already imported above, here for clarity)


def _synthesise(ws: ResearchWorkspace) -> dict[str, Any]:
    """Build the final result dict from workspace state."""

    # Build per-sub-question summaries
    sections: list[str] = []
    for sq in ws.sub_questions:
        relevant = [
            f for f in ws.findings if f.sub_question_id == sq.id
        ]
        # Collect supporting snippets
        snippets: list[str] = []
        for finding in relevant:
            for url in finding.supporting_sources:
                src = next((s for s in ws.sources if s.url == url), None)
                if src:
                    text = src.extracted_text or src.snippet
                    if text:
                        snippets.append(text[:600])
        status = "✅ resolved" if sq.status == "resolved" else "❓ unresolved"
        section = f"### {sq.question} [{status}]\n"
        if snippets:
            # Deduplicate and join
            seen_snippets: set[str] = set()
            for s in snippets:
                trimmed = s.strip()[:200]
                if trimmed not in seen_snippets:
                    seen_snippets.add(trimmed)
                    section += f"- {trimmed}\n"
        else:
            section += "- No relevant evidence collected.\n"
        sections.append(section)

    answer_body = "\n".join(sections)

    # Gaps / contradictions note
    notes: list[str] = []
    if ws.gaps:
        notes.append("**Gaps remaining:** " + "; ".join(ws.gaps[:5]))
    if ws.contradictions:
        notes.append(
            "**Contradictions found:** "
            + "; ".join(f'"{c.claim_a}" vs "{c.claim_b}"' for c in ws.contradictions[:3])
        )
    if notes:
        answer_body += "\n\n---\n" + "\n".join(notes)

    # Source list (sorted by score desc)
    sorted_sources = sorted(ws.sources, key=lambda s: s.score, reverse=True)
    source_list = [
        {
            "title": s.title,
            "url": s.url,
            "relevanceScore": round(s.score, 2),
        }
        for s in sorted_sources
        if s.url
    ]

    return {
        "success": True,
        "answer": answer_body,
        "sources": source_list,
        "researchSummary": {
            "resolvedQuestions": [sq.question for sq in ws.get_resolved()],
            "unresolvedQuestions": [sq.question for sq in ws.get_unresolved()],
            "iterations": ws.iteration_count,
            "confidence": round(ws.overall_confidence(), 2),
        },
    }
