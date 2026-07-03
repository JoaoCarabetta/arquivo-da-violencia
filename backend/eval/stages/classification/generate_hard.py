"""Generate challenging classification benchmark cases with a strong Gemini model."""

from __future__ import annotations

import json
from pathlib import Path

import instructor
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.classification import CLASSIFICATION_SYSTEM_PROMPT

DEFAULT_OUT = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "eval"
    / "classification_hard.json"
)

GENERATOR_MODEL = "google/gemini-3.1-pro-preview"

GENERATOR_SYSTEM_PROMPT = """
Você cria casos de teste adversariais para um classificador de manchetes de notícias
sobre mortes violentas no Brasil (homicídios, assassinatos, execuções).

Use EXATAMENTE os mesmos critérios de classificação abaixo para rotular cada manchete.
O objetivo é produzir manchetes DIFÍCEIS que confundiriam modelos leves, mas com rótulo
correto inequívoco para um humano que conhece as regras.

CRITÉRIOS (is_violent_death):
TRUE: manchete sobre morte violenta no Brasil (homicídio, assassinato, execução,
corpo/restos mortais com violência, tiroteio COM morte, feminicídio, latrocínio,
morte em operação/confronto, jargão policial como "neutralizado" ou "CPF cancelado").
FALSE: feridos ou vítimas que sobreviveram, tentativa sem morte, prisões, apreensões,
políticas de segurança, metáforas, morte culposa/acidente, morte natural, entretenimento,
notícias de morte violenta NO EXTERIOR (EUA, Europa, guerras fora do BR), tiroteio/operação
SEM menção a morte, processo judicial sobre crime passado sem notícia de nova morte.

Produza manchetes realistas em português brasileiro, estilo Google News, curtas.
Evite repetir estruturas. Cada manchete deve ser desafiadora por um motivo diferente.
Balanceie ~15 TRUE e ~15 FALSE.
"""

GENERATOR_USER_PROMPT = """
Gere exatamente 30 casos adversariais para benchmark de classificação.

Inclua variedade entre estas categorias (tags):
- implied_death: morte implícita mas corretamente rotulável
- explicit_non_death: violência clara sem morte
- accident_vs_violent: acidente/culposo vs homicídio
- metaphor_or_fiction: linguagem figurada ou entretenimento
- police_op_ambiguous: operação/confronto/tiroteio sem ou com morte explícita
- victim_status_unclear: vítima em estado incerto na manchete
- legal_process: investigação/julgamento/prisão relacionada a homicídio
- foreign_or_offtopic: falso positivo geográfico ou tema tangencial
- subtle_true: TRUE difícil (morte violenta fácil de perder)
- subtle_false: FALSE difícil (parece morte violenta mas não é)

Para cada caso forneça:
- headline: manchete
- is_violent_death: rótulo correto segundo as regras
- tags: 1-3 tags da lista acima
- notes: 1 frase explicando por que é difícil

Não copie manchetes do seed existente. Seja criativo e adversarial.
"""


class GeneratedCase(BaseModel):
    headline: str = Field(..., min_length=10, max_length=200)
    is_violent_death: bool
    tags: list[str] = Field(..., min_length=1, max_length=3)
    notes: str = Field(..., min_length=5, max_length=300)


class GeneratedHardSet(BaseModel):
    cases: list[GeneratedCase] = Field(..., min_length=30, max_length=30)


def generate_hard_cases(model: str = GENERATOR_MODEL) -> GeneratedHardSet:
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise ValueError("OPENROUTER_API_KEY not configured")

    client = instructor.from_provider(
        f"openrouter/{model}",
        api_key=settings.openrouter_api_key,
    )

    return client.create(
        response_model=GeneratedHardSet,
        messages=[
            {
                "role": "system",
                "content": GENERATOR_SYSTEM_PROMPT + "\n\n" + CLASSIFICATION_SYSTEM_PROMPT,
            },
            {"role": "user", "content": GENERATOR_USER_PROMPT},
        ],
        max_retries=2,
    )


def to_fixture(generated: GeneratedHardSet, *, model: str) -> dict:
    from eval.schemas import (
        CaseMetadata,
        ClassificationCase,
        ClassificationExpected,
        ClassificationFixture,
        ClassificationInput,
        FixtureMeta,
        dump_fixture,
        update_fixture_counts,
    )

    cases: list[ClassificationCase] = []
    for i, item in enumerate(generated.cases, start=1):
        cases.append(
            ClassificationCase(
                id=f"cls-hard-{i:03d}",
                tags=item.tags,
                label_status="labeled",
                input=ClassificationInput(headline=item.headline),
                expected=ClassificationExpected(is_violent_death=item.is_violent_death),
                metadata=CaseMetadata(notes=item.notes),
            )
        )

    fixture = ClassificationFixture(
        meta=FixtureMeta(generator_model=model),
        cases=cases,
    )

    update_fixture_counts(fixture)
    return dump_fixture(fixture)


def write_hard_fixture(out_path: Path, model: str = GENERATOR_MODEL) -> tuple[Path, int, int]:
    generated = generate_hard_cases(model=model)
    fixture_dict = to_fixture(generated, model=model)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(fixture_dict, ensure_ascii=False, indent=2))
    true_count = sum(1 for c in generated.cases if c.is_violent_death)
    false_count = len(generated.cases) - true_count
    return out_path, true_count, false_count
