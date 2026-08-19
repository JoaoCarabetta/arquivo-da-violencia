"""Tests for Chile geocoding with region=cl (issue #131)."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.geocoding import geocode_address, PRECISION_CITY


@pytest.mark.asyncio
async def test_geocode_chile_santiago_uses_cl_region():
    """Santiago, Metropolitana + country CL → point in Chile (not Brazil)."""
    # Mock Google Maps API response for Chilean Santiago
    from unittest.mock import Mock
    
    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_response.json = Mock(return_value={
        "status": "OK",
        "results": [
            {
                "formatted_address": "Santiago, Región Metropolitana, Chile",
                "geometry": {
                    "location": {"lat": -33.4489, "lng": -70.6693},
                    "location_type": "APPROXIMATE",
                },
                "place_id": "ChIJL68lS64hYpYRhB07b0sMDUw",
                "types": ["locality", "political"],
            }
        ],
    })

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("app.services.geocoding.get_settings") as mock_settings:
        mock_settings.return_value.google_maps_api_key = "test-key"
        
        result = await geocode_address(
            "Santiago, Metropolitana, Chile",
            input_granularity=PRECISION_CITY,
            client=mock_client,
            country="CL",
        )

    # Verify the result is in Chile (latitude around -33)
    assert result is not None
    assert result["latitude"] == -33.4489
    assert result["longitude"] == -70.6693
    
    # Verify Google was called with region=cl and language=es
    mock_client.get.assert_called_once()
    call_args = mock_client.get.call_args
    assert call_args.kwargs["params"]["region"] == "cl"
    assert call_args.kwargs["params"]["language"] == "es"


@pytest.mark.asyncio
async def test_geocode_brazil_santiago_uses_br_region():
    """Santiago, RS + country BR → point in Brazil (not Chile)."""
    # Mock Google Maps API response for Brazilian Santiago
    from unittest.mock import Mock
    
    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_response.json = Mock(return_value={
        "status": "OK",
        "results": [
            {
                "formatted_address": "Santiago, RS, Brasil",
                "geometry": {
                    "location": {"lat": -29.1917, "lng": -54.8669},
                    "location_type": "APPROXIMATE",
                },
                "place_id": "ChIJcSL_aLRsGpURbufr5LRwBu0",
                "types": ["locality", "political"],
            }
        ],
    })

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("app.services.geocoding.get_settings") as mock_settings:
        mock_settings.return_value.google_maps_api_key = "test-key"
        
        result = await geocode_address(
            "Santiago, RS, Brasil",
            input_granularity=PRECISION_CITY,
            client=mock_client,
            country="BR",
        )

    # Verify the result is in Brazil (latitude around -29)
    assert result is not None
    assert result["latitude"] == -29.1917
    assert result["longitude"] == -54.8669
    
    # Verify Google was called with region=br and language=pt-BR
    mock_client.get.assert_called_once()
    call_args = mock_client.get.call_args
    assert call_args.kwargs["params"]["region"] == "br"
    assert call_args.kwargs["params"]["language"] == "pt-BR"


@pytest.mark.asyncio
async def test_geocode_legacy_brasil_uses_br_region():
    """Legacy country value "Brasil" → uses BR settings."""
    from unittest.mock import Mock
    
    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_response.json = Mock(return_value={
        "status": "OK",
        "results": [
            {
                "formatted_address": "Rio de Janeiro, RJ, Brasil",
                "geometry": {
                    "location": {"lat": -22.9068, "lng": -43.1729},
                    "location_type": "APPROXIMATE",
                },
                "place_id": "ChIJW6AIkVXemwARTtIvZ2xC3FA",
                "types": ["locality", "political"],
            }
        ],
    })

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("app.services.geocoding.get_settings") as mock_settings:
        mock_settings.return_value.google_maps_api_key = "test-key"
        
        result = await geocode_address(
            "Rio de Janeiro, Brasil",
            input_granularity=PRECISION_CITY,
            client=mock_client,
            country="Brasil",
        )

    # Verify the result
    assert result is not None
    assert result["latitude"] == -22.9068
    
    # Verify Google was called with region=br (legacy "Brasil" → BR)
    mock_client.get.assert_called_once()
    call_args = mock_client.get.call_args
    assert call_args.kwargs["params"]["region"] == "br"
    assert call_args.kwargs["params"]["language"] == "pt-BR"
