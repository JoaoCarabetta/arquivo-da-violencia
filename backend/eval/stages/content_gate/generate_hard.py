"""Generate challenging content-gate benchmark cases with a strong Gemini model.

The content gate reads the article BODY (not just the headline), so hard cases
are full articles where the headline looks like one thing but the body reveals
another (aggregate statistics, foreign events, survivors, roundups, etc.).
"""

from __future__ import annotations

import json
from pathlib import Path

import instructor
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.classification import CONTENT_CLASSIFICATION_SYSTEM_PROMPT

DEFAULT_OUT = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "eval"
    / "content_gate_hard.json"
)

GENERATOR_MODEL = "google/gemini-2.5-pro"

GENERATOR_SYSTEM_PROMPT = """
Você cria casos de teste adversariais para um classificador de ARTIGOS JORNALÍSTICOS
(manchete + corpo) sobre mortes violentas no Brasil. O classificador decide:
1. is_violent_death: o artigo trata de morte(s) violenta(s) no Brasil?
2. is_single_incident: descreve UM ÚNICO incidente específico?

O artigo só passa no gate se AMBOS forem true.

Use EXATAMENTE os critérios do classificador (abaixo) para rotular cada caso.
O objetivo é produzir artigos DIFÍCEIS: a manchete deve parecer apontar numa direção,
mas o corpo revela a verdade. Os rótulos devem ser inequívocos para um humano que leu
o corpo inteiro.

Produza artigos realistas em português brasileiro, estilo portais de notícia locais
(G1, Band, portais regionais). Corpo com 2-5 parágrafos (300-900 caracteres).
"""

GENERATOR_USER_PROMPT = """
Gere exatamente 20 casos adversariais para benchmark do gate de conteúdo.

Distribua entre estas categorias (tags), com rótulos corretos:
- aggregate_statistics (gate=false): manchete parece um caso, corpo é balanço/estatística
- foreign (gate=false): manchete ambígua, corpo revela evento fora do Brasil
- survivor (gate=false): manchete sugere morte, corpo diz que a vítima sobreviveu
- roundup (gate=false): corpo cobre vários incidentes não relacionados
- legal_process (gate=false): julgamento/prisão de crime antigo, sem novo óbito
- suicide (gate=false): corpo revela suicídio
- buried_incident (gate=true): manchete genérica/estatística, mas corpo descreve UM
  incidente específico de morte violenta no Brasil
- hard_true (gate=true): incidente único real mas com linguagem indireta
  ("não resistiu aos ferimentos", jargão policial)

Inclua ~12 casos gate=false e ~8 casos gate=true.

Para cada caso forneça:
- headline: manchete
- content: corpo do artigo (2-5 parágrafos)
- is_violent_death: rótulo correto
- is_single_incident: rótulo correto
- tags: 1-2 tags da lista acima
- notes: 1 frase explicando por que é difícil
"""


class GeneratedCase(BaseModel):
    headline: str = Field(..., min_length=10, max_length=250)
    content: str = Field(..., min_length=200, max_length=2500)
    is_violent_death: bool
    is_single_incident: bool
    tags: list[str] = Field(..., min_length=1, max_length=2)
    notes: str = Field(..., min_length=5, max_length=300)


class GeneratedHardSet(BaseModel):
    cases: list[GeneratedCase] = Field(..., min_length=20, max_length=20)


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
                "content": GENERATOR_SYSTEM_PROMPT
                + "\n\nCRITÉRIOS DO CLASSIFICADOR:\n"
                + CONTENT_CLASSIFICATION_SYSTEM_PROMPT,
            },
            {"role": "user", "content": GENERATOR_USER_PROMPT},
        ],
        max_retries=2,
    )


def to_fixture(generated: GeneratedHardSet, *, model: str) -> dict:
    from eval.schemas import CaseMetadata
    from eval.schemas_content_gate import (
        ContentGateCase,
        ContentGateExpected,
        ContentGateFixture,
        ContentGateFixtureMeta,
        ContentGateInput,
        dump_content_gate_fixture,
        update_content_gate_fixture_counts,
    )

    cases: list[ContentGateCase] = []
    for i, item in enumerate(generated.cases, start=1):
        cases.append(
            ContentGateCase(
                id=f"cg-hard-{i:03d}",
                tags=item.tags,
                label_status="labeled",
                input=ContentGateInput(headline=item.headline, content=item.content),
                expected=ContentGateExpected(
                    is_violent_death=item.is_violent_death,
                    is_single_incident=item.is_single_incident,
                ),
                metadata=CaseMetadata(notes=item.notes),
            )
        )

    fixture = ContentGateFixture(
        meta=ContentGateFixtureMeta(generator_model=model),
        cases=cases,
    )
    update_content_gate_fixture_counts(fixture)
    return dump_content_gate_fixture(fixture)


def write_hard_fixture(out_path: Path, model: str = GENERATOR_MODEL) -> tuple[Path, int, int]:
    generated = generate_hard_cases(model=model)
    fixture_dict = to_fixture(generated, model=model)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(fixture_dict, ensure_ascii=False, indent=2))
    gate_true = sum(1 for c in generated.cases if c.is_violent_death and c.is_single_incident)
    gate_false = len(generated.cases) - gate_true
    return out_path, gate_true, gate_false
