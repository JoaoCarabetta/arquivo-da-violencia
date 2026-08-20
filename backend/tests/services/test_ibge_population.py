"""Tests for IBGE population data loading and code_state conversion."""

import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.ibge_population import IBGEPopulation
from app.services.ibge_population import load_ibge_data_from_geobr_and_sidra


@pytest.mark.asyncio
async def test_code_state_float_to_string_conversion(async_session: AsyncSession):
    """
    Test that code_state from geobr (as float) is correctly converted to 2-char string.
    
    Geobr returns code_state as float (e.g. 11.0), which becomes '11.0' if naively
    converted to string. This would fail varchar(2) constraint.
    
    Expected: 11.0 → '11', 1.0 → '01'
    """
    mock_geobr_data = pd.DataFrame({
        'code_muni': [1100015, 1100023, 1100031],
        'code_state': [11.0, 11.0, 11.0],  # Float from geobr
        'name_muni': ['Alta Floresta d\'Oeste', 'Ariquemes', 'Cabixi'],
        'name_state': ['Rondônia', 'Rondônia', 'Rondônia'],
        'abbrev_state': ['RO', 'RO', 'RO']
    })
    
    mock_sidra_data = pd.DataFrame({
        'D1C': ['1100015', '1100023', '1100031'],
        'D1N': ['Alta Floresta d\'Oeste', 'Ariquemes', 'Cabixi'],
        'V': ['24913', '111148', '6314']
    })
    
    mock_gdf = MagicMock()
    mock_gdf.drop.return_value = mock_geobr_data
    
    with patch('geobr.read_municipal_seat', return_value=mock_gdf):
        with patch('sidrapy.get_table', return_value=mock_sidra_data):
            await load_ibge_data_from_geobr_and_sidra(async_session, year=2022, force_reload=True)
    
    query = select(IBGEPopulation).where(IBGEPopulation.code_muni == 1100015)
    result = await async_session.execute(query)
    pop = result.scalar_one_or_none()
    
    assert pop is not None
    assert pop.code_state == '11', f"Expected '11', got '{pop.code_state}'"
    assert len(pop.code_state) == 2, f"code_state must be exactly 2 chars, got {len(pop.code_state)}"


@pytest.mark.asyncio
async def test_code_state_single_digit_zero_padding(async_session: AsyncSession):
    """
    Test that single-digit state codes are zero-padded to 2 chars.
    
    Some states have codes 01-09. Geobr may return these as 1.0, 2.0, etc.
    Expected: 1.0 → '01', 2.0 → '02'
    """
    mock_geobr_data = pd.DataFrame({
        'code_muni': [1200013],
        'code_state': [1.0],  # Should become '01' (Acre)
        'name_muni': ['Acrelândia'],
        'name_state': ['Acre'],
        'abbrev_state': ['AC']
    })
    
    mock_sidra_data = pd.DataFrame({
        'D1C': ['1200013'],
        'D1N': ['Acrelândia'],
        'V': ['16277']
    })
    
    mock_gdf = MagicMock()
    mock_gdf.drop.return_value = mock_geobr_data
    
    with patch('geobr.read_municipal_seat', return_value=mock_gdf):
        with patch('sidrapy.get_table', return_value=mock_sidra_data):
            await load_ibge_data_from_geobr_and_sidra(async_session, year=2022, force_reload=True)
    
    query = select(IBGEPopulation).where(IBGEPopulation.code_muni == 1200013)
    result = await async_session.execute(query)
    pop = result.scalar_one_or_none()
    
    assert pop is not None
    assert pop.code_state == '01', f"Expected '01', got '{pop.code_state}'"
    assert len(pop.code_state) == 2, f"code_state must be exactly 2 chars, got {len(pop.code_state)}"


@pytest.mark.asyncio
async def test_code_state_string_float_format(async_session: AsyncSession):
    """
    Test that code_state as string '11.0' is also handled correctly.
    
    Depending on pandas dtype inference, code_state might come as string '11.0'.
    Expected: '11.0' → '11'
    """
    mock_geobr_data = pd.DataFrame({
        'code_muni': [2200051],
        'code_state': ['22.0'],  # String with .0
        'name_muni': ['Água Branca'],
        'name_state': ['Piauí'],
        'abbrev_state': ['PI']
    })
    
    mock_sidra_data = pd.DataFrame({
        'D1C': ['2200051'],
        'D1N': ['Água Branca'],
        'V': ['16200']
    })
    
    mock_gdf = MagicMock()
    mock_gdf.drop.return_value = mock_geobr_data
    
    with patch('geobr.read_municipal_seat', return_value=mock_gdf):
        with patch('sidrapy.get_table', return_value=mock_sidra_data):
            await load_ibge_data_from_geobr_and_sidra(async_session, year=2022, force_reload=True)
    
    query = select(IBGEPopulation).where(IBGEPopulation.code_muni == 2200051)
    result = await async_session.execute(query)
    pop = result.scalar_one_or_none()
    
    assert pop is not None
    assert pop.code_state == '22', f"Expected '22', got '{pop.code_state}'"
    assert len(pop.code_state) == 2, f"code_state must be exactly 2 chars, got {len(pop.code_state)}"
