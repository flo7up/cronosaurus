"""
Research collector — internal-only retrieval pipeline.

Orchestrates: Google search → page fetch → content extraction → dedup.
Not exposed to the user; called only by the deep_search orchestrator.
"""

import logging
from typing import Any

from app.services.deep_search import google_search_client, page_fetcher, content_extractor
from app.services.deep_search.research_workspace import ResearchWorkspace, Source

logger = logging.getLogger(__name__)

_DEFAULT_RESULTS_PER_QUERY = 5
_DEFAULT_PAGES_TO_FETCH = 3


def collect(
    workspace: ResearchWorkspace,
    search_queries: list[str],
    api_key: str,
    engine_id: str,
    *,
    max_results_per_query: int = _DEFAULT_RESULTS_PER_QUERY,
    max_pages_to_fetch: int = _DEFAULT_PAGES_TO_FETCH,
) -> dict[str, Any]:
    """Execute searches, fetch pages, extract text, and update *workspace*.

    Returns a summary dict of what was collected in this pass.
    """
    new_sources = 0
    queries_run = 0
    pages_fetched = 0

    for query in search_queries:
        if query in workspace.queries_executed:
            continue

        results = google_search_client.search(
            query, api_key, engine_id, max_results=max_results_per_query,
        )
        workspace.queries_executed.append(query)
        queries_run += 1

        # Fetch top pages that we haven't already visited
        fetched_this_query = 0
        for result in results:
            url = result.get("url", "")
            if not url or url in workspace._source_urls:
                continue
            if fetched_this_query >= max_pages_to_fetch:
                # Still record unfetched results as snippet-only sources
                src = Source(
                    url=url,
                    title=result.get("title", ""),
                    snippet=result.get("snippet", ""),
                    score=_score_result(result),
                )
                workspace.add_source(src)
                new_sources += 1
                continue

            html = page_fetcher.fetch(url)
            if html:
                title, text = content_extractor.extract(html)
                pages_fetched += 1
            else:
                title = result.get("title", "")
                text = ""

            src = Source(
                url=url,
                title=title or result.get("title", ""),
                snippet=result.get("snippet", ""),
                extracted_text=text,
                score=_score_result(result, has_content=bool(text)),
            )
            if workspace.add_source(src):
                new_sources += 1
            fetched_this_query += 1

    return {
        "queries_run": queries_run,
        "new_sources": new_sources,
        "pages_fetched": pages_fetched,
        "total_sources": len(workspace.sources),
    }


def _score_result(result: dict, *, has_content: bool = False) -> float:
    """Simple heuristic relevance score (0-1)."""
    score = 0.3  # baseline
    snippet = result.get("snippet", "")
    if len(snippet) > 80:
        score += 0.2
    if has_content:
        score += 0.3
    # Prefer known-authority domains
    domain = result.get("displayLink", result.get("url", ""))
    authority_domains = (
        "wikipedia.org", "github.com", "stackoverflow.com",
        "arxiv.org", "docs.microsoft.com", "learn.microsoft.com",
        "developer.mozilla.org", "gov", "edu",
    )
    if any(ad in domain for ad in authority_domains):
        score += 0.2
    return min(score, 1.0)
