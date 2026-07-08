"""Deterministic post-LLM fixes for headline classification."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from unidecode import unidecode

if TYPE_CHECKING:
    from app.services.classification import ViolentDeathClassification

_SURVIVAL_PATTERNS = (
    re.compile(r"\bsobrevive\b", re.IGNORECASE),
    re.compile(r"\bsobreviveu\b", re.IGNORECASE),
    re.compile(r"\bsobreviveram\b", re.IGNORECASE),
    re.compile(r"quadro estavel", re.IGNORECASE),
    re.compile(r"quadro estável", re.IGNORECASE),
    re.compile(r"\bhospital\b", re.IGNORECASE),
    re.compile(r"centro cirurgico", re.IGNORECASE),
    re.compile(r"centro cirúrgico", re.IGNORECASE),
    re.compile(r"\binternad", re.IGNORECASE),
    re.compile(r"\bsocorrid", re.IGNORECASE),
    re.compile(r"\bferid[oa]s?\b", re.IGNORECASE),
    re.compile(r"chora ao ver", re.IGNORECASE),
    re.compile(r"banco dos reus", re.IGNORECASE),
    re.compile(r"banco dos réus", re.IGNORECASE),
    re.compile(r"\bsao presos\b", re.IGNORECASE),
    re.compile(r"\bsão presos\b", re.IGNORECASE),
    re.compile(r"\bforam presos\b", re.IGNORECASE),
)

_FOREIGN_MARKERS = (
    " texas",
    " eua",
    " nos eua",
    "estados unidos",
    " russia",
    " rússia",
    " ucrania",
    " ucrânia",
    " venezuela",
    " mexico",
    " méxico",
    " base militar russa",
)

_METAPHOR_MARKERS = (
    "assassinato da lingua",
    "assassinato da língua",
    "executa o orcamento",
    "executa o orçamento",
    "ultimo capitulo da novela",
    "último capítulo da novela",
    "virou piada",
)

_ACCIDENT_MARKERS = (
    "morte instantanea",
    "morte instantânea",
    "cair do",
    "falta de epi",
    "perdeu a vida preso",
    "perde a vida preso",
    "perde freio",
    "infarto fulminante",
)

_EXPLICIT_DEATH_MARKERS = (
    "nao resistiu",
    "não resistiu",
    "nao resiste",
    "não resiste",
    "morre no hospital",
    "morre apos",
    "morre após",
    "veio a obito",
    "veio a óbito",
    "faleceu",
    "falece",
    "obito",
    "óbito",
    "encontrado morto",
    "achado morto",
)

_NON_DEATH_POLICE_MARKERS = (
    "cumpre mandados",
    "apreende arsenal",
    "seria usado para cometer",
)

_IMPLIED_FATAL_MARKERS = (
    "crivado de balas",
    "crivada de balas",
    "restos mortais",
    "carbonizado no porta-malas",
    "carbonizado no portamalas",
    "achado carbonizado",
    "neutralizado",
    "tombaram",
    "tombou",
    "cpf cancelado",
    "cpfs cancelados",
    "nao deixa sobreviventes",
    "não deixa sobreviventes",
    "linchado ate parar de respirar",
    "linchado até parar de respirar",
    "ossada humana",
    "marca de tiro no cranio",
    "marca de tiro no crânio",
    "corpo amarrado",
    "execucao brutal",
    "execução brutal",
    "nao resistiu aos ferimentos",
    "não resistiu aos ferimentos",
    "nao resiste",
    "não resiste",
    "feminicidio",
    "feminicídio",
    "homicidio doloso",
    "homicídio doloso",
    "duplo homicidio",
    "duplo homicídio",
    "chacina",
)

_TROCA_TIROS = re.compile(r"troca tiros", re.IGNORECASE)
_DEATH_HINT = re.compile(
    r"neutraliz|morto|morta|mortos|mortas|tomb|cpf cancel|deixa sobreviventes|chacina",
    re.IGNORECASE,
)


def _norm(text: str) -> str:
    return unidecode(text.lower())


def should_force_non_violent_death(headline: str) -> bool:
    normalized = _norm(headline)
    if any(marker in normalized for marker in _EXPLICIT_DEATH_MARKERS):
        return False
    if any(pattern.search(normalized) for pattern in _SURVIVAL_PATTERNS):
        return True
    if any(marker in normalized for marker in _FOREIGN_MARKERS):
        return True
    if any(marker in normalized for marker in _METAPHOR_MARKERS):
        return True
    if any(marker in normalized for marker in _ACCIDENT_MARKERS):
        return True
    if any(marker in normalized for marker in _NON_DEATH_POLICE_MARKERS):
        return True
    if _TROCA_TIROS.search(normalized) and not _DEATH_HINT.search(normalized):
        return True
    return False


def should_force_violent_death(headline: str) -> bool:
    if should_force_non_violent_death(headline):
        return False
    normalized = _norm(headline)
    return any(marker in normalized for marker in _IMPLIED_FATAL_MARKERS)


def apply_classification_heuristics(
    headline: str,
    result: ViolentDeathClassification,
) -> ViolentDeathClassification:
    """Apply deterministic overrides for implied-death and clear false positives."""
    if should_force_non_violent_death(headline):
        if result.is_violent_death:
            return result.model_copy(
                update={
                    "is_violent_death": False,
                    "confidence": "alta",
                    "reasoning": (
                        f"{result.reasoning} "
                        "[heuristic: survival/foreign/metaphor/accident/non-death police op]"
                    ).strip(),
                }
            )
        return result

    if should_force_violent_death(headline) and not result.is_violent_death:
        return result.model_copy(
            update={
                "is_violent_death": True,
                "confidence": "alta",
                "reasoning": (
                    f"{result.reasoning} "
                    "[heuristic: implied fatal violence in headline]"
                ).strip(),
            }
        )

    return result
