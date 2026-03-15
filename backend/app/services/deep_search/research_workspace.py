"""
Research workspace — in-memory state for a single deep search session.

Tracks the search plan, executed queries, collected sources, extracted
findings, gaps, contradictions, and per-sub-question confidence.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


# ── Data classes ────────────────────────────────────────────────


@dataclass
class SubQuestion:
    id: str
    question: str
    priority: str = "medium"  # high | medium | low
    status: str = "pending"  # pending | resolved | unresolved


@dataclass
class Source:
    url: str
    title: str = ""
    snippet: str = ""
    extracted_text: str = ""
    score: float = 0.0


@dataclass
class Finding:
    sub_question_id: str
    claim: str
    supporting_sources: list[str] = field(default_factory=list)  # URLs
    confidence: float = 0.0


@dataclass
class Contradiction:
    claim_a: str
    claim_b: str
    source_a: str
    source_b: str


@dataclass
class ResearchWorkspace:
    """Mutable workspace that accumulates research state."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    main_query: str = ""
    sub_questions: list[SubQuestion] = field(default_factory=list)
    queries_executed: list[str] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    contradictions: list[Contradiction] = field(default_factory=list)
    iteration_count: int = 0

    # ── helpers ──────────────────────────────────────────────

    @property
    def _source_urls(self) -> set[str]:
        return {s.url for s in self.sources}

    def add_source(self, source: Source) -> bool:
        """Add a source if its URL is new.  Returns True if added."""
        if source.url in self._source_urls:
            return False
        self.sources.append(source)
        return True

    def add_finding(self, finding: Finding) -> None:
        self.findings.append(finding)

    def record_gap(self, gap: str) -> None:
        if gap not in self.gaps:
            self.gaps.append(gap)

    def record_contradiction(self, c: Contradiction) -> None:
        self.contradictions.append(c)

    def mark_resolved(self, sub_question_id: str) -> None:
        for sq in self.sub_questions:
            if sq.id == sub_question_id:
                sq.status = "resolved"
                return

    def get_unresolved(self) -> list[SubQuestion]:
        return [sq for sq in self.sub_questions if sq.status != "resolved"]

    def get_resolved(self) -> list[SubQuestion]:
        return [sq for sq in self.sub_questions if sq.status == "resolved"]

    def overall_confidence(self) -> float:
        """Simple average confidence across findings, 0.0 if none."""
        if not self.findings:
            return 0.0
        return sum(f.confidence for f in self.findings) / len(self.findings)

    # ── serialisation helpers (for logging / debug) ─────────

    def summary_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.id,
            "main_query": self.main_query,
            "iterations": self.iteration_count,
            "sub_questions_total": len(self.sub_questions),
            "sub_questions_resolved": len(self.get_resolved()),
            "sources_count": len(self.sources),
            "findings_count": len(self.findings),
            "gaps": self.gaps,
            "contradictions_count": len(self.contradictions),
            "confidence": round(self.overall_confidence(), 2),
        }
