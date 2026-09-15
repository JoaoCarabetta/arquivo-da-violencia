"""
São Paulo SSP resolução 160 monthly adapter (issue #244).

Reads an unpivoted municipal-monthly extract of the official SSP-SP
"Ocorrências Policiais registradas por Mês" table (resolução SSP 160/2001)
and writes Formulário 1 bag + extra indicators into OfficialViolenceCount
with source_id=sp.

This is NOT the Transparência SSP boletim (BO / RDO) dump.

Source:
  Portal: https://www.ssp.sp.gov.br/estatistica/dados-mensais
  Grain: municipality × calendar month (select município on the portal)
  Live layout (sampled 2026-09-15): HTML table, natureza as rows, months as
  columns. "Exportar Dados" dumps the displayed table. There is no stable
  statewide bulk CSV; operators unpivot the municipal table into long CSV.

Format of the extract this adapter consumes (long CSV, semicolon):
  codigo_ibge;municipio;ano;mes;natureza;vitimas;revisao
  - codigo_ibge: 7-digit IBGE municipal code
  - natureza: SSP label as published (footnotes like "(2)" / "(3)" stripped)
  - vitimas: count for that natureza × month
  - revisao: preliminar | consolidado
    SSP publishes on the website before Diário Oficial (Lei 9.155/95,
    Resolução 161/01) and may rectify until DOE; tag those snapshots
    preliminar vs consolidado on the extract.

Typology: SSP labels are aliased to canonical VDE natureza strings, then
passed through shared map_natureza (bag / extra / unmapped). Prefer
"Nº DE VÍTIMAS EM …" rows over occurrence rows when both map to the same
indicator. Traffic-accident homicides, tentativas, furtos, etc. are not
aliased and are skipped — do not invent types.

Intervenção (MDIP) is an extra when present (Produtividade / complementary
extracts); it is not on the default 23-row criminal table.

Window: default since 2025-09 (municipality × month official phase).
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Tuple

from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.official_violence_data import OfficialRevision, OfficialSourceId
from app.services.official_typology import map_natureza
from app.services.official_violence_data import upsert_official_indicator_counts

SSP_SP_PORTAL_URL = "https://www.ssp.sp.gov.br/estatistica/dados-mensais"
SSP_SP_SOURCE = "SSP-SP Resolução 160 — série mensal por município"

DEFAULT_SINCE = "2025-09"

# Thin SP label normalizer: SSP natureza → canonical VDE natureza → map_natureza.
# Not a second typology map. Keys are _normalize_sp_label() output.
# Victim-count labels (prefer=True) win over occurrence labels for the same
# indicator so we never double-count HOMICÍDIO DOLOSO + Nº DE VÍTIMAS.
_SP_LABEL_ALIASES: dict[str, tuple[str, bool]] = {
    "n de vítimas em homicídio doloso": ("Homicídio doloso", True),
    "homicídio doloso": ("Homicídio doloso", False),
    "n de vítimas em latrocínio": ("Roubo seguido de morte (latrocínio)", True),
    "latrocínio": ("Roubo seguido de morte (latrocínio)", False),
    "n de vítimas em lesão corporal seguida de morte": (
        "Lesão corporal seguida de morte",
        True,
    ),
    "lesão corporal seguida de morte": ("Lesão corporal seguida de morte", False),
    "n de vítimas em feminicídio": ("Feminicídio", True),
    "feminicídio": ("Feminicídio", False),
    "n de vítimas em homicídio decorrente de intervenção policial": (
        "Morte por intervenção de Agente do Estado",
        True,
    ),
    "homicídio decorrente de intervenção policial": (
        "Morte por intervenção de Agente do Estado",
        False,
    ),
    "n de vítimas em morte decorrente de intervenção policial": (
        "Morte por intervenção de Agente do Estado",
        True,
    ),
    "morte decorrente de intervenção policial": (
        "Morte por intervenção de Agente do Estado",
        False,
    ),
}

# Public alias table (raw-ish labels → VDE) for tests / docs. Victim labels only
# for rows that exist as both occurrence and victims on the portal.
SP_LABEL_TO_NATUREZA: dict[str, str] = {
    "Nº DE VÍTIMAS EM HOMICÍDIO DOLOSO (3)": "Homicídio doloso",
    "HOMICÍDIO DOLOSO (2)": "Homicídio doloso",
    "Nº DE VÍTIMAS EM LATROCÍNIO": "Roubo seguido de morte (latrocínio)",
    "LATROCÍNIO": "Roubo seguido de morte (latrocínio)",
    "LESÃO CORPORAL SEGUIDA DE MORTE": "Lesão corporal seguida de morte",
    "FEMINICÍDIO": "Feminicídio",
    "Nº DE VÍTIMAS EM HOMICÍDIO DECORRENTE DE INTERVENÇÃO POLICIAL": (
        "Morte por intervenção de Agente do Estado"
    ),
}


def _normalize_sp_label(raw: str) -> str:
    """Strip footnotes, ordinal signs, collapse whitespace, casefold for alias lookup.

    NFKC compatibility-maps MASCULINE ORDINAL INDICATOR (U+00BA, 'º') to 'o',
    so 'Nº' would become 'No'/'no'. Drop º/° before any compatibility
    normalize so victim-count labels stay 'n de vítimas …'.
    """
    text = (raw or "").replace("\u00ba", "").replace("\u00b0", "").replace("\u00aa", "")
    text = unicodedata.normalize("NFC", text).strip().lower()
    text = re.sub(r"\s*\(\d+\)\s*", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def revision_from_ssp(value: Any) -> OfficialRevision:
    """Map extract `revisao` to OfficialRevision.

    Website publication before Diário Oficial is preliminar; post-DOE /
    rectified snapshots are consolidado. Blank defaults to consolidado
    (historical extracts).
    """
    text = str(value or "").strip().lower()
    if text in {"1", "preliminar", "parcial", "pre"}:
        return OfficialRevision.PRELIMINAR
    return OfficialRevision.CONSOLIDADO


def decode_ssp_sp_bytes(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _parse_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    text = str(value).strip().replace(" ", "")
    if text == "" or text in {".", "…", "...", "-", "–"}:
        return None
    # Brazilian thousands: 1.193 / 13.998
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", text):
        text = text.replace(".", "")
    else:
        text = text.replace(",", ".")
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _year_month(ano: Any, mes: Any) -> Optional[str]:
    ano_text = str(ano or "").strip()
    mes_text = str(mes or "").strip()
    if not ano_text or not mes_text:
        return None
    try:
        return f"{int(ano_text):04d}-{int(mes_text):02d}"
    except (TypeError, ValueError):
        return None


def _ibge_code(row: Dict[str, str]) -> Optional[int]:
    raw = (
        row.get("codigo_ibge")
        or row.get("code_muni")
        or row.get("cod_municipio")
        or row.get("codigo")
        or ""
    ).strip()
    try:
        code = int(raw)
    except (TypeError, ValueError):
        return None
    # 7-digit IBGE municipal codes for SP are 3500000–3599999
    if 3_500_000 <= code <= 3_599_999:
        return code
    return None


def parse_ssp_sp_csv(
    text: str,
    *,
    since: str = DEFAULT_SINCE,
) -> List[Dict[str, Any]]:
    """
    Parse long municipal-monthly SSP-SP rows into mapped records.

    Each record: code_muni, year_month, natureza, indicator, kind,
    victim_count, revision. Unmapped naturezas are omitted. When both a
    victim-count label and an occurrence label map to the same indicator,
    the victim-count row is kept. Rows before ``since`` are skipped.
    """
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    collected: List[Dict[str, Any]] = []

    for row in reader:
        parsed = _parse_long_row(row, since=since)
        if parsed:
            collected.append(parsed)

    return _prefer_victim_counts(collected)


def _parse_long_row(row: Dict[str, str], *, since: str) -> Optional[Dict[str, Any]]:
    # DictReader keys may have BOM / stray spaces
    normalized_row = {(k or "").strip(): (v if v is not None else "") for k, v in row.items()}

    code_muni = _ibge_code(normalized_row)
    if code_muni is None:
        return None

    year_month = _year_month(normalized_row.get("ano"), normalized_row.get("mes"))
    if not year_month or year_month < since:
        return None

    natureza_raw = (normalized_row.get("natureza") or "").strip()
    if not natureza_raw:
        return None

    alias = _SP_LABEL_ALIASES.get(_normalize_sp_label(natureza_raw))
    if not alias:
        return None
    vde_natureza, prefer = alias
    mapped = map_natureza(vde_natureza)
    if mapped["kind"] == "unmapped" or not mapped["indicator"]:
        return None

    victim_count = _parse_int(
        normalized_row.get("vitimas")
        or normalized_row.get("vítimas")
        or normalized_row.get("registros")
        or normalized_row.get("total")
    )
    if victim_count is None:
        return None

    revision = revision_from_ssp(
        normalized_row.get("revisao") or normalized_row.get("revisão") or normalized_row.get("revision")
    )
    municipality_name = (normalized_row.get("municipio") or normalized_row.get("município") or "").strip()

    return {
        "code_muni": code_muni,
        "municipality_name": municipality_name,
        "year_month": year_month,
        "natureza": vde_natureza,
        "indicator": mapped["indicator"],
        "kind": mapped["kind"],
        "victim_count": victim_count,
        "revision": revision,
        "prefer": prefer,
    }


def _prefer_victim_counts(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep Nº DE VÍTIMAS rows when occurrence + victims both map to one indicator."""
    by_key: Dict[Tuple[int, str, str, OfficialRevision], Dict[str, Any]] = {}
    for record in records:
        key = (
            record["code_muni"],
            record["year_month"],
            record["indicator"],
            record["revision"],
        )
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = record
            continue
        if record.get("prefer") and not existing.get("prefer"):
            by_key[key] = record
    cleaned: List[Dict[str, Any]] = []
    for record in by_key.values():
        row = dict(record)
        row.pop("prefer", None)
        cleaned.append(row)
    return cleaned


async def ingest_ssp_sp_rows(
    session: AsyncSession,
    records: Iterable[Dict[str, Any]],
    *,
    source: str = SSP_SP_SOURCE,
    revision: Optional[OfficialRevision] = None,
) -> None:
    """
    Write mapped SSP-SP records into OfficialViolenceCount (source_id=sp).

    Unmapped kinds are skipped. code_muni must exist in ibge_population.
    Groups by (code_muni, year_month, indicator) within each revision.
    ``revision`` overrides per-row revision when the extract has none.
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

        row_revision = row.get("revision") or revision or OfficialRevision.CONSOLIDADO
        if not isinstance(row_revision, OfficialRevision):
            row_revision = revision_from_ssp(row_revision)

        victim_count = _parse_int(row.get("victim_count"))
        if victim_count is None:
            continue

        bucket = grouped_by_revision.setdefault(row_revision, {})
        key = (code_muni, year_month, indicator)
        bucket[key] = bucket.get(key, 0) + victim_count

    for rev, grouped in grouped_by_revision.items():
        await upsert_official_indicator_counts(
            session,
            grouped,
            source_id=OfficialSourceId.SP,
            revision=rev,
            source=source,
        )

    logger.info(
        "Ingested SSP-SP resolução 160: revisions={} skipped_unmapped={} skipped_unknown_muni={}",
        len(grouped_by_revision),
        skipped_unmapped,
        skipped_unknown_muni,
    )
