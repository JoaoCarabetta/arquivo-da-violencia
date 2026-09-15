"""Official violence data model (Ministry of Justice VDE data)."""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Column, String
from sqlmodel import Field, SQLModel, UniqueConstraint


class OfficialSourceId(str, Enum):
    """Official data source identity."""

    VALIDADOR = "validador"
    RJ = "rj"
    MG = "mg"
    SP = "sp"


class OfficialRevision(str, Enum):
    """Official data revision stage."""

    PRELIMINAR = "preliminar"
    CONSOLIDADO = "consolidado"


class OfficialViolenceCount(SQLModel, table=True):
    """
    Official monthly victim counts from Ministry of Justice VDE (Validador de Dados Estatísticos).

    This table stores violence statistics at municipality granularity from the
    SINESP VDE system (bancovde-YYYY.xlsx files).

    Data source: https://www.gov.br/mj/pt-br/assuntos/sua-seguranca/seguranca-publica/estatistica/download/dnsp-base-de-dados/

    The four Formulário 1 indicators summed into the official municipal total:
    1. Homicídio doloso
    2. Feminicídio
    3. Latrocínio (roubo seguido de morte)
    4. Lesão corporal seguida de morte

    Note: Morte por intervenção do Estado is stored but NOT included in the municipal total.
    """
    __tablename__ = "official_violence_count"
    __table_args__ = (
        UniqueConstraint(
            "code_muni",
            "year_month",
            "indicator",
            "source_id",
            "revision",
            name="uq_official_violence_key",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    # Geographic key
    code_muni: int = Field(
        index=True,
        description="7-digit IBGE municipal code (e.g. 3550308 for São Paulo)"
    )

    # Temporal key
    year_month: str = Field(
        index=True,
        max_length=7,
        description="Year-month in YYYY-MM format (e.g. '2025-09')"
    )

    # Indicator key
    indicator: str = Field(
        index=True,
        max_length=50,
        description="Indicator slug (e.g. 'homicidio_doloso', 'feminicidio', 'mortes_violentas_intencionais')"
    )

    # Source identity and revision (stored as VARCHAR — avoids native Postgres enum drift)
    source_id: OfficialSourceId = Field(
        default=OfficialSourceId.VALIDADOR,
        sa_column=Column(String(20), nullable=False, index=True),
        description="Official data source (validador, rj, mg, sp)",
    )
    revision: OfficialRevision = Field(
        default=OfficialRevision.CONSOLIDADO,
        sa_column=Column(String(20), nullable=False, index=True),
        description="Data revision stage (preliminar or consolidado)",
    )

    # Value
    victim_count: int = Field(
        description="Total victim count (sum of male + female + unidentified)"
    )

    # Flag for summed total row
    is_total: bool = Field(
        default=False,
        description="True if this row is the summed official municipal total (Formulário 1 types only)"
    )

    # Metadata
    source: str = Field(
        default="SINESP VDE",
        max_length=100,
        description="Data source (e.g. 'SINESP VDE - Formulário 1')"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "code_muni": 3550308,
                "year_month": "2025-09",
                "indicator": "homicidio_doloso",
                "source_id": "validador",
                "revision": "consolidado",
                "victim_count": 53,
                "is_total": False,
                "source": "SINESP VDE - Formulário 1"
            }
        }
