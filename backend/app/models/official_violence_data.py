"""Official violence data model (Ministry of Justice VDE data)."""

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class OfficialViolenceCount(SQLModel, table=True):
    """
    Official monthly victim counts from Ministry of Justice VDE (Validador de Dados Estatísticos).
    
    This table stores violence statistics at municipality granularity from the
    SINESP VDE system (Formulário 1: Vítimas por sexo e municípios).
    
    Data source: https://dados.mj.gov.br/dataset/sistema-nacional-de-estatisticas-de-seguranca-publica
    
    The five indicators summed into "mortes violentas intencionais":
    1. Homicídio doloso
    2. Feminicídio
    3. Latrocínio (roubo seguido de morte)
    4. Lesão corporal seguida de morte
    5. Morte por intervenção policial
    """
    __tablename__ = "official_violence_count"
    
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
    
    # Value
    victim_count: int = Field(
        description="Total victim count (sum of male + female + unidentified)"
    )
    
    # Flag for summed total row
    is_total: bool = Field(
        default=False,
        description="True if this row is the summed 'mortes_violentas_intencionais' total"
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
                "victim_count": 53,
                "is_total": False,
                "source": "SINESP VDE - Formulário 1"
            }
        }
