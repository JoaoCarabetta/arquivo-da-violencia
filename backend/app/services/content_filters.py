"""Heuristic pre-filters for post-download article content (AQV-32).

Cheap regex checks on headline + body catch high-confidence outlier patterns
(aggregate statistics, foreign disasters) before an LLM content-gate call.
Patterns are intentionally conservative to avoid false positives on normal
single-incident reporting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

ContentClassHint = Literal[
    "incident",
    "aggregate_statistics",
    "foreign",
    "non_incident",
    "suicide",
    "accident_disaster",
]


@dataclass(frozen=True)
class HeuristicMatch:
    """Result when a heuristic rule rejects article content."""

    hint: ContentClassHint
    rule: str
    detail: str


# Year-end / national statistics and CVLI-style reports.
_AGGREGATE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "cvli_year_report",
        re.compile(
            r"\bcvli\b.*\b(20\d{2}|regist(?:ou|ra)|mortes?\s+violentas?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "annual_balance",
        re.compile(
            r"\bbalan[çc]o\s+(anual|de\s+mortes|crim(?:inal|inalidade))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "large_victim_total",
        re.compile(
            r"\b(\d{1,3}[.,]\d{3}|\d{4,})\s+(mortes?\s+violentas?|v[ií]timas?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "year_state_total",
        re.compile(
            r"\b(mortes?\s+violentas?|v[ií]timas?).{0,40}\b(20\d{2}|no\s+estado|em\s+todo\s+o\s+estado)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "national_study",
        re.compile(
            r"\b(estudo|pesquisa|mapa|painel).{0,60}\b(mortes?\s+violentas?|homic[ií]dios?)\b.{0,40}\b(brasil|pa[ií]s|nacional)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "monthly_roundup",
        re.compile(
            r"\bno\s+m[eê]s.{0,40}\b(regist(?:ou|ra)|foram)\s+\d+\s+(mortes?|homic[ií]dios?)\b",
            re.IGNORECASE,
        ),
    ),
)

# Foreign disasters / clearly out-of-scope geography in the body.
_FOREIGN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "foreign_earthquake",
        re.compile(
            r"\bterremoto.{0,80}\b(venezuela|chile|turquia|turkey|m[eé]xico|haiti|afeganist[aã]o)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "foreign_country_disaster",
        re.compile(
            r"\b(desastre|terremoto|tsunami|guerra).{0,40}\b(venezuela|ucr[aâ]nia|gaza|s[ií]ria|sud[aã]o)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "foreign_mass_shooting",
        re.compile(
            r"\b(atirador|tiroteio|mass\s+shooting).{0,40}\b(eua|estados\s+unidos|texas|california|paris|londres)\b",
            re.IGNORECASE,
        ),
    ),
)

# Suicides and animal cruelty — out of scope even when violent.
_NON_INCIDENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "suicide",
        re.compile(
            r"\b(suic[ií]dio|tirou\s+a\s+pr[oó]pria\s+vida|enforcou-se|se\s+matou)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "animal_cruelty",
        re.compile(
            r"\b(cachorro|gato|animal|cavalo).{0,40}\b(morto|mortos|envenenado|maltratado)\b",
            re.IGNORECASE,
        ),
    ),
)


def _search_patterns(
    text: str,
    patterns: tuple[tuple[str, re.Pattern[str]], ...],
    hint: ContentClassHint,
) -> HeuristicMatch | None:
    for rule, pattern in patterns:
        match = pattern.search(text)
        if match:
            snippet = text[max(0, match.start() - 20) : match.end() + 40].strip()
            return HeuristicMatch(hint=hint, rule=rule, detail=snippet[:200])
    return None


def apply_content_heuristics(headline: str | None, content: str) -> HeuristicMatch | None:
    """Return a match when content clearly should not reach extraction.

    Args:
        headline: Source headline (may be empty).
        content: Extracted article body.

    Returns:
        HeuristicMatch if the article should be discarded, else None.
    """
    combined = f"{headline or ''}\n{content}".strip()
    if not combined:
        return None

    for patterns, hint in (
        (_AGGREGATE_PATTERNS, "aggregate_statistics"),
        (_FOREIGN_PATTERNS, "foreign"),
        (_NON_INCIDENT_PATTERNS, "non_incident"),
    ):
        match = _search_patterns(combined, patterns, hint)
        if match:
            return match

    return None
