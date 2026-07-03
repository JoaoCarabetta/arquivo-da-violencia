"""Generate adversarial extraction benchmark cases with Gemini Pro."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import instructor
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.extraction import EXTRACTION_SYSTEM_PROMPT

from eval.schemas import CaseMetadata
from eval.schemas_extraction import (
    DEFAULT_REQUIRED_FIELDS,
    CaseScoring,
    ExtractionCase,
    ExtractionFixture,
    ExtractionFixtureMeta,
    ExtractionInput,
    dump_extraction_fixture,
    load_extraction_fixture,
    update_extraction_fixture_counts,
)

DEFAULT_OUT = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "eval"
    / "extraction_hard.json"
)

GENERATOR_MODEL = "google/gemini-2.5-pro"

GENERATOR_SYSTEM_PROMPT = """
Você cria casos de teste adversariais para extração estruturada de notícias de morte violenta
no Brasil. Cada caso tem um artigo curto (300-800 palavras) e o JSON esperado nos campos
que o benchmark avalia.

Desafios a incluir (varie entre casos):
- datas relativas resolvíveis pela data de publicação ("ontem", "na sexta-feira")
- datas ausentes (date=null, has_explicit_date=false)
- múltiplas vítimas com contagem implícita
- jargão policial ("neutralizado", "CPF cancelado")
- local parcial (bairro sem rua, cidade vs estado)
- método ambíguo ou "Não especificado"
- latrocínio vs homicídio simples
- feminicídio
- artigo curto com poucas pistas

Use metadados realistas. Artigos em português brasileiro, estilo imprensa local.
"""

GENERATOR_USER_PROMPT = """
Gere exatamente 20 casos adversariais para benchmark de extração.

Para cada caso forneça:
- tags: 1-3 tags descritivas
- notes: por que é difícil
- input.content: texto do artigo (300-800 palavras)
- input.metadata: headline, published_at (ISO), publisher, url

Balanceie casos com e sem data explícita. Os rótulos serão gerados automaticamente depois.
"""


class GeneratedExtractionCase(BaseModel):
    tags: list[str] = Field(..., min_length=1, max_length=3)
    notes: str = Field(..., min_length=5, max_length=300)
    input: ExtractionInput


class GeneratedExtractionSet(BaseModel):
    cases: list[GeneratedExtractionCase] = Field(..., min_length=20, max_length=20)


def generate_hard_cases(model: str = GENERATOR_MODEL) -> GeneratedExtractionSet:
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise ValueError("OPENROUTER_API_KEY not configured")

    client = instructor.from_provider(
        f"openrouter/{model}",
        api_key=settings.openrouter_api_key,
    )

    return client.create(
        response_model=GeneratedExtractionSet,
        messages=[
            {
                "role": "system",
                "content": GENERATOR_SYSTEM_PROMPT + "\n\n" + EXTRACTION_SYSTEM_PROMPT,
            },
            {"role": "user", "content": GENERATOR_USER_PROMPT},
        ],
        max_retries=2,
    )


def to_fixture(generated: GeneratedExtractionSet, *, model: str) -> dict:
    cases: list[ExtractionCase] = []
    for i, item in enumerate(generated.cases, start=1):
        cases.append(
            ExtractionCase(
                id=f"ext-hard-{i:03d}",
                tags=item.tags,
                label_status="labeled",
                input=item.input,
                expected={},
                scoring=CaseScoring(required_fields=list(DEFAULT_REQUIRED_FIELDS)),
                metadata=CaseMetadata(notes=item.notes),
            )
        )

    fixture = ExtractionFixture(
        meta=ExtractionFixtureMeta(generator_model=model),
        cases=cases,
    )
    update_extraction_fixture_counts(fixture)
    return dump_extraction_fixture(fixture)


def _project_expected(event_dict: dict) -> dict:
    from eval.stages.extraction.build import _project_expected as project

    return project(event_dict)


def label_cases_with_pro(cases: list[ExtractionCase], model: str) -> list[ExtractionCase]:
    from app.services.extraction import extract_event_from_content

    labeled: list[ExtractionCase] = []
    for case in cases:
        metadata = case.input.metadata.model_dump(exclude_none=True)
        event = extract_event_from_content(
            case.input.content,
            metadata,
            model_id=model,
        )
        expected = _project_expected(event.model_dump(mode="json"))
        labeled.append(case.model_copy(update={"expected": expected}))
    return labeled


def relabel_fixture(out_path: Path, model: str = GENERATOR_MODEL) -> Path:
    fixture = load_extraction_fixture(json.loads(out_path.read_text()))
    fixture.cases = label_cases_with_pro(fixture.cases, model)
    update_extraction_fixture_counts(fixture)
    out_path.write_text(json.dumps(dump_extraction_fixture(fixture), ensure_ascii=False, indent=2))
    return out_path


def write_hard_fixture(out_path: Path, model: str = GENERATOR_MODEL) -> Path:
    generated = generate_hard_cases(model=model)
    fixture_dict = to_fixture(generated, model=model)
    fixture = load_extraction_fixture(fixture_dict)
    fixture.cases = label_cases_with_pro(fixture.cases, model)
    update_extraction_fixture_counts(fixture)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(dump_extraction_fixture(fixture), ensure_ascii=False, indent=2))
    return out_path
