"""
Rio de Janeiro ISPDados adapter (issue #242).

Reads the public municipal monthly extract (wide CSV) and writes Formulário 1
bag + extra indicators into OfficialViolenceCount with source_id=rj.

Source:
  https://www.ispdados.rj.gov.br/Arquivos/BaseMunicipioMensal.csv
  Portal: https://www.ispdados.rj.gov.br/estatistica.html
  Grain: municipality (fmun_cod, 7-digit IBGE) × calendar month (ano, mes)

Format (live file, sampled 2026-09-15):
  - Semicolon-separated, latin-1
  - One row per municipality-month; crime titles as columns
  - `fase`: 1 = parcial/preliminar, 2 = consolidado, 3 = consolidado com errata

Typology: ISP column names are aliased to canonical VDE natureza strings, then
passed through shared map_natureza (bag / extra / unmapped). Composites such as
cvli and letalidade_violenta are not aliased and are skipped — do not invent types.

Window: default since 2025-09 (municipality × month official phase).
"""

from __future__ import annotations

import csv
import io
from typing import Any, Dict, Iterable, List, Optional

from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.official_violence_data import OfficialRevision, OfficialSourceId
from app.services.official_typology import map_natureza
from app.services.official_violence_data import upsert_official_indicator_counts

ISPDADOS_CSV_URL = "https://www.ispdados.rj.gov.br/Arquivos/BaseMunicipioMensal.csv"
ISPDADOS_PORTAL_URL = "https://www.ispdados.rj.gov.br/estatistica.html"
ISPDADOS_SOURCE = "ISPDados - série histórica mensal por município"

# Thin RJ label normalizer: ISP column → canonical VDE natureza → map_natureza.
# Not a second typology map.
ISP_COLUMN_TO_NATUREZA: dict[str, str] = {
    "hom_doloso": "Homicídio doloso",
    "feminicidio": "Feminicídio",
    "latrocinio": "Roubo seguido de morte (latrocínio)",
    "lesao_corp_morte": "Lesão corporal seguida de morte",
    "hom_por_interv_policial": "Morte por intervenção de Agente do Estado",
}

DEFAULT_SINCE = "2025-09"


def revision_from_fase(fase: Any) -> OfficialRevision:
    """Map ISP `fase` to OfficialRevision.

    ISP methodological notes (SINESP-VDE / divulgação):
    1 = dados parciais, 2 = consolidados, 3 = consolidados com errata.
    """
    if str(fase).strip() == "1":
        return OfficialRevision.PRELIMINAR
    return OfficialRevision.CONSOLIDADO


def decode_ispdados_bytes(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def parse_ispdados_csv(
    text: str,
    *,
    since: str = DEFAULT_SINCE,
) -> List[Dict[str, Any]]:
    """
    Unpivot ISPDados wide municipal-monthly rows into mapped records.

    Each record: code_muni, year_month, natureza, indicator, kind,
    victim_count, revision. Unmapped columns (cvli, tentat_hom, …) are skipped.
    Rows before `since` are skipped.
    """
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    records: List[Dict[str, Any]] = []

    for row in reader:
        parsed = _parse_wide_row(row, since=since)
        records.extend(parsed)

    return records


def _year_month_from_row(row: Dict[str, str]) -> Optional[str]:
    ano = (row.get("ano") or "").strip()
    mes = (row.get("mes") or "").strip()
    if not ano or not mes:
        return None
    try:
        return f"{int(ano):04d}-{int(mes):02d}"
    except (TypeError, ValueError):
        return None


def _parse_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        return int(float(text.replace(",", ".")))
    except (TypeError, ValueError):
        return None


def _parse_wide_row(row: Dict[str, str], *, since: str) -> List[Dict[str, Any]]:
    code_raw = (row.get("fmun_cod") or row.get("codigo") or "").strip()
    try:
        code_muni = int(code_raw)
    except (TypeError, ValueError):
        return []
    if code_muni <= 0:
        return []

    year_month = _year_month_from_row(row)
    if not year_month or year_month < since:
        return []

    revision = revision_from_fase(row.get("fase"))
    municipality_name = (row.get("fmun") or "").strip()

    records: List[Dict[str, Any]] = []
    for column, natureza in ISP_COLUMN_TO_NATUREZA.items():
        if column not in row:
            continue
        victim_count = _parse_int(row.get(column))
        if victim_count is None:
            continue
        mapped = map_natureza(natureza)
        if mapped["kind"] == "unmapped" or not mapped["indicator"]:
            continue
        records.append(
            {
                "code_muni": code_muni,
                "municipality_name": municipality_name,
                "year_month": year_month,
                "natureza": natureza,
                "indicator": mapped["indicator"],
                "kind": mapped["kind"],
                "victim_count": victim_count,
                "revision": revision,
            }
        )
    return records


async def ingest_ispdados_rows(
    session: AsyncSession,
    records: Iterable[Dict[str, Any]],
    *,
    source: str = ISPDADOS_SOURCE,
) -> None:
    """
    Write mapped ISPDados records into OfficialViolenceCount (source_id=rj).

    Unmapped kinds are skipped. code_muni must exist in ibge_population.
    Groups by (code_muni, year_month, indicator) within each revision.
    """
    from app.models.ibge_population import IBGEPopulation

    rows = list(records)
    if not rows:
        return

    result = await session.execute(select(IBGEPopulation.code_muni))
    known_codes = {code for (code,) in result.all()}

    grouped_by_revision: Dict[OfficialRevision, Dict[tuple, int]] = {}
    skipped_unmapped = 0
    skipped_unknown_muni = 0

    for row in rows:
        kind = row.get("kind")
        indicator = row.get("indicator")
        if kind == "unmapped" or not indicator:
            if "natureza" in row and not indicator:
                mapped = map_natureza(str(row.get("natureza") or ""))
                if mapped["kind"] == "unmapped" or not mapped["indicator"]:
                    skipped_unmapped += 1
                    continue
                indicator = mapped["indicator"]
                kind = mapped["kind"]
            else:
                skipped_unmapped += 1
                continue

        try:
            code_muni = int(row["code_muni"])
        except (KeyError, TypeError, ValueError):
            skipped_unknown_muni += 1
            continue
        if code_muni not in known_codes:
            skipped_unknown_muni += 1
            continue

        year_month = str(row.get("year_month") or "")
        if not year_month:
            continue

        revision = row.get("revision") or OfficialRevision.CONSOLIDADO
        if not isinstance(revision, OfficialRevision):
            revision = revision_from_fase(revision)

        victim_count = _parse_int(row.get("victim_count"))
        if victim_count is None:
            continue

        bucket = grouped_by_revision.setdefault(revision, {})
        key = (code_muni, year_month, indicator)
        bucket[key] = bucket.get(key, 0) + victim_count

    for revision, grouped in grouped_by_revision.items():
        await upsert_official_indicator_counts(
            session,
            grouped,
            source_id=OfficialSourceId.RJ,
            revision=revision,
            source=source,
        )

    logger.info(
        "Ingested ISPDados: revisions={} skipped_unmapped={} skipped_unknown_muni={}",
        len(grouped_by_revision),
        skipped_unmapped,
        skipped_unknown_muni,
    )
