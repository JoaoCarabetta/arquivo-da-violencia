"""
Shared typology map for SINESP VDE (Validador) naturezas.

Formulário 1 bag types feed the municipal official total.
Extra categories (e.g. morte por intervenção do Estado) are stored separately.
Unmapped naturezas are excluded from ingest and labelled "não mapeado".
"""

from typing import Literal, TypedDict, Optional

TypologyKind = Literal["bag", "extra", "unmapped"]


class NaturezaMapping(TypedDict):
    kind: TypologyKind
    indicator: Optional[str]
    label: str


# Bag: Formulário 1 types included in municipal official total
_BAG_NATUREZAS: dict[str, tuple[str, str]] = {
    "Homicídio doloso": ("homicidio_doloso", "Homicídio doloso"),
    "Feminicídio": ("feminicidio", "Feminicídio"),
    "Roubo seguido de morte (latrocínio)": ("latrocinio", "Roubo seguido de morte (latrocínio)"),
    "Lesão corporal seguida de morte": ("lesao_corporal_seguida_morte", "Lesão corporal seguida de morte"),
}

# Extra: stored as own indicator, never in bag / is_total
_EXTRA_NATUREZAS: dict[str, tuple[str, str]] = {
    "Morte por intervenção de Agente do Estado": (
        "morte_intervencao_policial",
        "Morte por intervenção de Agente do Estado",
    ),
}

# Compatibility exports (all known natureza → indicator slugs)
INDICATOR_MAPPING: dict[str, str] = {
    natureza: slug for natureza, (slug, _) in {**_BAG_NATUREZAS, **_EXTRA_NATUREZAS}.items()
}

MVI_INDICATORS: list[str] = [
    "homicidio_doloso",
    "feminicidio",
    "latrocinio",
    "lesao_corporal_seguida_morte",
]


def formulario_1_indicators() -> list[str]:
    """Return the four Formulário 1 bag indicator slugs."""
    return list(MVI_INDICATORS)


def map_natureza(natureza: str) -> NaturezaMapping:
    """
    Map a VDE evento/natureza string to typology metadata.

    Returns:
        kind: "bag" (Formulário 1), "extra" (own indicator), or "unmapped"
        indicator: slug when mapped, None when unmapped
        label: source label when mapped, exactly "não mapeado" when unmapped
    """
    if natureza in _BAG_NATUREZAS:
        indicator, label = _BAG_NATUREZAS[natureza]
        return {"kind": "bag", "indicator": indicator, "label": label}

    if natureza in _EXTRA_NATUREZAS:
        indicator, label = _EXTRA_NATUREZAS[natureza]
        return {"kind": "extra", "indicator": indicator, "label": label}

    return {"kind": "unmapped", "indicator": None, "label": "não mapeado"}
