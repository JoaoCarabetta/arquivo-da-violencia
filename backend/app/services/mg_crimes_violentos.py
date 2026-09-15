"""
Minas Gerais SEJUSP Crimes Violentos adapter (issue #243).

Reads the public municipal monthly extract (long CSV) and writes Formulário 1
bag indicators into OfficialViolenceCount with source_id=mg.

Source:
  Portal: https://dados.mg.gov.br/dataset/crimes-violentos
  Annual CSV per calendar year (semicolon-separated), e.g. crimes_violentos_2025.csv
  Resource IDs on the portal datapackage (CKAN upload URLs).

Live layout (sampled crimes_violentos_2025.csv, 2026-09-15):
  registros;natureza;municipio;cod_municipio;mes;ano;risp;rmbh
  - Grain: municipality (cod_municipio, 6-digit SEJUSP prefix) × calendar month
  - registros: occurrence count for that natureza
  - cod_municipio maps to 7-digit IBGE via code_muni // 10 (MG only)

Revision: the SEJUSP CSV does not encode preliminar vs consolidado. Assign at
ingest via the ``revision`` kwarg / CLI ``--revision`` (default consolidado),
same pattern as Validador bancovde.

Typology: SEJUSP natureza strings are aliased to canonical VDE labels, then
passed through shared map_natureza (bag / extra / unmapped). Tentative crimes,
sexual violence, robbery, etc. are not aliased and are skipped.

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

MG_CRIMES_VIOLENTOS_PORTAL = "https://dados.mg.gov.br/dataset/crimes-violentos"
MG_SOURCE = "SEJUSP-MG Crimes Violentos - município × mês"

# CKAN resource IDs from dados.mg.gov.br datapackage (crimes-violentos dataset).
MG_RESOURCE_IDS: dict[int, str] = {
    2019: "216a5c59-497e-49d2-bfc0-23cbedb1d665",
    2020: "637c3391-50ea-4bd5-b2f1-8d2347b4758a",
    2021: "151a95ee-49af-4feb-9d23-8a6868d82077",
    2022: "a96028d5-1808-4166-b680-91b3f8f6aa17",
    2023: "3d935565-0f56-4594-9c26-7b6db71c25d2",
    2024: "15ac6aff-1349-4589-8739-76ed7c52b3b0",
    2025: "d23fed6e-c59a-488e-a1da-72c5091edb30",
    2026: "476f959e-e4bc-4960-b5c4-b3c22fc6fefb",
}

# Thin MG label normalizer → canonical VDE natureza → map_natureza.
MG_NATUREZA_TO_VDE: dict[str, str] = {
    "HOMICIDIO CONSUMADO (REGISTROS)": "Homicídio doloso",
    "FEMINICIDIO CONSUMADO (REGISTROS)": "Feminicídio",
}

DEFAULT_SINCE = "2025-09"


def mg_csv_url(year: int) -> str:
    """Return the CKAN download URL for crimes_violentos_YYYY.csv."""
    resource_id = MG_RESOURCE_IDS.get(year)
    if not resource_id:
        raise ValueError(
            f"No MG Crimes Violentos resource id for year {year}. "
            f"Known years: {sorted(MG_RESOURCE_IDS)}"
        )
    return (
        f"https://dados.mg.gov.br/dataset/crimes-violentos/resource/"
        f"{resource_id}/download/crimes_violentos_{year}.csv"
    )


def decode_mg_bytes(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def build_mg_ibge_lookup(ibge_codes: Iterable[int]) -> Dict[int, int]:
    """
    Map SEJUSP 6-digit cod_municipio prefix → 7-digit IBGE code_muni (MG only).

    SEJUSP publishes cod_municipio without the IBGE check digit; for MG
    municipalities code_muni // 10 is unique.
    """
    lookup: Dict[int, int] = {}
    for code_muni in ibge_codes:
        # MG municipal IBGE codes are 3100000–3199999 (7 digits, state prefix 31)
        if 3_100_000 <= code_muni <= 3_199_999:
            lookup[code_muni // 10] = code_muni
    return lookup


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


def _year_month_from_row(row: Dict[str, str]) -> Optional[str]:
    ano = (row.get("ano") or "").strip()
    mes = (row.get("mes") or "").strip()
    if not ano or not mes:
        return None
    try:
        return f"{int(ano):04d}-{int(mes):02d}"
    except (TypeError, ValueError):
        return None


def parse_mg_crimes_violentos_csv(
    text: str,
    *,
    since: str = DEFAULT_SINCE,
    ibge_lookup: Optional[Dict[int, int]] = None,
) -> List[Dict[str, Any]]:
    """
    Parse SEJUSP long-format municipal-monthly rows into mapped records.

    Each record: code_muni, year_month, natureza, indicator, kind,
    victim_count, revision (caller sets revision at ingest). Unmapped naturezas
    are omitted. Rows before ``since`` are skipped.
    """
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    records: List[Dict[str, Any]] = []

    for row in reader:
        parsed = _parse_long_row(row, since=since, ibge_lookup=ibge_lookup or {})
        records.extend(parsed)

    return records


def _parse_long_row(
    row: Dict[str, str],
    *,
    since: str,
    ibge_lookup: Dict[int, int],
) -> List[Dict[str, Any]]:
    cod_raw = (row.get("cod_municipio") or "").strip()
    try:
        cod_prefix = int(cod_raw)
    except (TypeError, ValueError):
        return []

    code_muni = ibge_lookup.get(cod_prefix)
    if code_muni is None:
        return []

    year_month = _year_month_from_row(row)
    if not year_month or year_month < since:
        return []

    natureza_raw = (row.get("natureza") or "").strip()
    if not natureza_raw or natureza_raw.lower() == "natureza":
        return []

    vde_natureza = MG_NATUREZA_TO_VDE.get(natureza_raw.upper())
    if not vde_natureza:
        return []

    mapped = map_natureza(vde_natureza)
    if mapped["kind"] == "unmapped" or not mapped["indicator"]:
        return []

    victim_count = _parse_int(row.get("registros"))
    if victim_count is None:
        return []

    municipality_name = (row.get("municipio") or "").strip()

    return [
        {
            "code_muni": code_muni,
            "municipality_name": municipality_name,
            "year_month": year_month,
            "natureza": vde_natureza,
            "indicator": mapped["indicator"],
            "kind": mapped["kind"],
            "victim_count": victim_count,
        }
    ]


async def ingest_mg_crimes_violentos_rows(
    session: AsyncSession,
    records: Iterable[Dict[str, Any]],
    *,
    revision: OfficialRevision = OfficialRevision.CONSOLIDADO,
    source: str = MG_SOURCE,
) -> None:
    """
    Write mapped MG records into OfficialViolenceCount (source_id=mg).

    Unmapped kinds are skipped. code_muni must exist in ibge_population.
    Groups by (code_muni, year_month, indicator) for the given revision.
    """
    from app.models.ibge_population import IBGEPopulation

    rows = list(records)
    if not rows:
        return

    result = await session.execute(
        select(IBGEPopulation.code_muni).where(IBGEPopulation.abbrev_state == "MG")
    )
    ibge_lookup = build_mg_ibge_lookup(code for (code,) in result.all())
    known_codes = set(ibge_lookup.values())

    grouped: Dict[tuple, int] = {}
    skipped_unmapped = 0
    skipped_unknown_muni = 0

    for row in rows:
        kind = row.get("kind")
        indicator = row.get("indicator")
        if kind == "unmapped" or not indicator:
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

        victim_count = _parse_int(row.get("victim_count"))
        if victim_count is None:
            continue

        key = (code_muni, year_month, indicator)
        grouped[key] = grouped.get(key, 0) + victim_count

    await upsert_official_indicator_counts(
        session,
        grouped,
        source_id=OfficialSourceId.MG,
        revision=revision,
        source=source,
    )

    logger.info(
        "Ingested MG Crimes Violentos: rows={} skipped_unmapped={} skipped_unknown_muni={}",
        len(grouped),
        skipped_unmapped,
        skipped_unknown_muni,
    )
