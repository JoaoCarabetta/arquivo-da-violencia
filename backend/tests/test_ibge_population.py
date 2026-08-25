"""Tests for IBGE population service with float state code handling."""

import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
from sqlmodel import select

from app.services.ibge_population import load_ibge_data_from_geobr_and_sidra
from app.models.ibge_population import IBGEPopulation


@pytest.mark.asyncio
async def test_load_ibge_data_converts_float_state_codes(async_session):
    """
    Test that state codes from geobr (which may be floats or float strings)
    are correctly converted to zero-padded 2-digit strings.
    
    This fixes the staging issue where geobr returned '11.0' for Rondônia
    which couldn't fit into varchar(2).
    
    Test cases:
    - 11.0 (float) → '11'
    - 1.0 (float) → '01' (zero-padded)
    - '22.0' (string) → '22'
    """
    # Mock geobr data with float state codes (as returned by read_municipal_seat)
    mock_geobr_gdf = MagicMock()
    mock_geobr_df = pd.DataFrame({
        'code_muni': [1100015, 1100023, 2200053],
        'code_state': [11.0, 11.0, 22.0],  # Float format from geobr
        'name_muni': ['Alta Floresta D\'Oeste', 'Ariquemes', 'Açailândia'],
        'name_state': ['Rondônia', 'Rondônia', 'Maranhão'],
        'abbrev_state': ['RO', 'RO', 'MA'],
    })
    mock_geobr_gdf.drop.return_value = mock_geobr_df
    
    # Mock SIDRA population data
    mock_sidra_df = pd.DataFrame({
        'D1C': ['1100015', '1100023', '2200053'],
        'D1N': ['Alta Floresta D\'Oeste', 'Ariquemes', 'Açailândia'],
        'V': ['29200', '107862', '112445'],
    })
    
    with patch('app.services.ibge_population.read_municipal_seat') as mock_read_seat, \
         patch('app.services.ibge_population.sidrapy') as mock_sidrapy:
        
        mock_read_seat.return_value = mock_geobr_gdf
        mock_sidrapy.get_table.return_value = mock_sidra_df
        
        # Load data (should convert float state codes)
        await load_ibge_data_from_geobr_and_sidra(async_session, year=2022, force_reload=True)
    
    # Verify data was persisted with correctly formatted state codes
    query = select(IBGEPopulation).order_by(IBGEPopulation.code_muni)
    result = await async_session.execute(query)
    populations = result.scalars().all()
    
    assert len(populations) == 3, "Should have 3 municipalities"
    
    # Check Rondônia municipalities (code_state 11.0 → '11')
    ro_1 = populations[0]
    assert ro_1.code_muni == 1100015
    assert ro_1.code_state == '11', f"Expected '11', got '{ro_1.code_state}'"
    assert len(ro_1.code_state) == 2, "State code must be exactly 2 characters"
    assert ro_1.name_muni == 'Alta Floresta D\'Oeste'
    assert ro_1.abbrev_state == 'RO'
    assert ro_1.population == 29200
    
    ro_2 = populations[1]
    assert ro_2.code_muni == 1100023
    assert ro_2.code_state == '11', f"Expected '11', got '{ro_2.code_state}'"
    assert len(ro_2.code_state) == 2, "State code must be exactly 2 characters"
    
    # Check Maranhão municipality (code_state 22.0 → '22')
    ma_1 = populations[2]
    assert ma_1.code_muni == 2200053
    assert ma_1.code_state == '22', f"Expected '22', got '{ma_1.code_state}'"
    assert len(ma_1.code_state) == 2, "State code must be exactly 2 characters"
    assert ma_1.name_muni == 'Açailândia'
    assert ma_1.abbrev_state == 'MA'


@pytest.mark.asyncio
async def test_load_ibge_data_zero_pads_single_digit_states(async_session):
    """
    Test that single-digit state codes are zero-padded to 2 digits.
    
    Acre (code_state 1.0) should become '01', not '1'.
    """
    # Mock geobr data with single-digit state code
    mock_geobr_gdf = MagicMock()
    mock_geobr_df = pd.DataFrame({
        'code_muni': [1200013],
        'code_state': [1.0],  # Acre: single digit
        'name_muni': ['Acrelândia'],
        'name_state': ['Acre'],
        'abbrev_state': ['AC'],
    })
    mock_geobr_gdf.drop.return_value = mock_geobr_df
    
    # Mock SIDRA population data
    mock_sidra_df = pd.DataFrame({
        'D1C': ['1200013'],
        'D1N': ['Acrelândia'],
        'V': ['15256'],
    })
    
    with patch('app.services.ibge_population.read_municipal_seat') as mock_read_seat, \
         patch('app.services.ibge_population.sidrapy') as mock_sidrapy:
        
        mock_read_seat.return_value = mock_geobr_gdf
        mock_sidrapy.get_table.return_value = mock_sidra_df
        
        await load_ibge_data_from_geobr_and_sidra(async_session, year=2022, force_reload=True)
    
    # Verify Acre state code is zero-padded
    query = select(IBGEPopulation)
    result = await async_session.execute(query)
    pop = result.scalar_one()
    
    assert pop.code_state == '01', f"Expected '01', got '{pop.code_state}'"
    assert len(pop.code_state) == 2, "State code must be exactly 2 characters"
    assert pop.abbrev_state == 'AC'


@pytest.mark.asyncio
async def test_load_ibge_data_handles_string_float_codes(async_session):
    """
    Test that string-formatted float codes (e.g. '22.0') are handled correctly.
    
    Some data sources might return state codes as strings.
    """
    # Mock geobr data with string float state codes
    mock_geobr_gdf = MagicMock()
    mock_geobr_df = pd.DataFrame({
        'code_muni': [3550308],
        'code_state': ['35.0'],  # String float format
        'name_muni': ['São Paulo'],
        'name_state': ['São Paulo'],
        'abbrev_state': ['SP'],
    })
    mock_geobr_gdf.drop.return_value = mock_geobr_df
    
    # Mock SIDRA population data
    mock_sidra_df = pd.DataFrame({
        'D1C': ['3550308'],
        'D1N': ['São Paulo'],
        'V': ['11451245'],
    })
    
    with patch('app.services.ibge_population.read_municipal_seat') as mock_read_seat, \
         patch('app.services.ibge_population.sidrapy') as mock_sidrapy:
        
        mock_read_seat.return_value = mock_geobr_gdf
        mock_sidrapy.get_table.return_value = mock_sidra_df
        
        await load_ibge_data_from_geobr_and_sidra(async_session, year=2022, force_reload=True)
    
    # Verify string float code was converted correctly
    query = select(IBGEPopulation)
    result = await async_session.execute(query)
    pop = result.scalar_one()
    
    assert pop.code_state == '35', f"Expected '35', got '{pop.code_state}'"
    assert len(pop.code_state) == 2, "State code must be exactly 2 characters"
    assert pop.name_muni == 'São Paulo'
