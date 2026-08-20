"""IBGE population data model."""

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class IBGEPopulation(SQLModel, table=True):
    """
    Cached IBGE population data for municipalities and states.
    
    This table stores population estimates from IBGE (Instituto Brasileiro de
    Geografia e Estatística) to avoid hitting external APIs on every request.
    """
    __tablename__ = "ibge_population"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # IBGE codes
    code_muni: Optional[int] = Field(
        default=None,
        index=True,
        description="7-digit IBGE municipal code (e.g. 3550308 for São Paulo)"
    )
    code_state: Optional[str] = Field(
        default=None,
        index=True,
        max_length=2,
        description="2-digit IBGE state code (e.g. 35 for SP)"
    )
    
    # Location names
    name_muni: Optional[str] = Field(default=None, max_length=200)
    name_state: Optional[str] = Field(default=None, max_length=100)
    abbrev_state: Optional[str] = Field(default=None, max_length=2)
    
    # Population data
    population: int = Field(description="Population count")
    year: int = Field(description="Census or estimate year (e.g. 2022)")
    
    # Metadata
    source: str = Field(
        default="IBGE",
        max_length=100,
        description="Data source (e.g. 'IBGE Censo 2022', 'IBGE Estimativa 2023')"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_schema_extra = {
            "example": {
                "code_muni": 3550308,
                "code_state": "35",
                "name_muni": "São Paulo",
                "name_state": "São Paulo",
                "abbrev_state": "SP",
                "population": 11451245,
                "year": 2022,
                "source": "IBGE Censo 2022"
            }
        }
