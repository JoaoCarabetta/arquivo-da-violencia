"""Tests for geocoding with country-specific region codes."""

import pytest
from unittest.mock import AsyncMock, patch
from app.services.geocoding import geocode_address, PRECISION_CITY
from app.country_registry import get_country_config


@pytest.mark.asyncio
class TestCountryGeocoding:
    """Test geocoding uses country-specific region codes."""
    
    async def test_ar_uses_region_ar(self):
        """Argentina geocoding uses region=ar."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "status": "OK",
            "results": [{
                "geometry": {
                    "location": {"lat": -34.6037, "lng": -58.3816},
                    "location_type": "GEOMETRIC_CENTER",
                },
                "formatted_address": "Buenos Aires, Argentina",
                "place_id": "ChIJvQz5TjvKvJURh47oiC6Bs6A",
                "types": ["locality", "political"],
            }],
        }
        mock_response.raise_for_status = AsyncMock()
        
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = AsyncMock()
        
        with patch("app.services.geocoding.httpx.AsyncClient", return_value=mock_client):
            with patch("app.services.geocoding.get_settings") as mock_settings:
                mock_settings.return_value.google_maps_api_key = "fake-key"
                
                result = await geocode_address(
                    "Buenos Aires, Argentina",
                    input_granularity=PRECISION_CITY,
                    country="AR"
                )
        
        # Verify the API was called with region=ar
        call_args = mock_client.get.call_args
        assert call_args is not None
        params = call_args.kwargs.get("params", {})
        
        # Check that region and language match Argentina config
        config = get_country_config("AR")
        assert params["region"] == config.geocode_region
        assert params["language"] == config.geocode_language
        assert "country:AR" in params.get("components", "")
    
    async def test_co_uses_region_co(self):
        """Colombia geocoding uses region=co."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "status": "OK",
            "results": [{
                "geometry": {
                    "location": {"lat": 4.7110, "lng": -74.0721},
                    "location_type": "GEOMETRIC_CENTER",
                },
                "formatted_address": "Bogotá, Colombia",
                "place_id": "ChIJKcumLf2bP44RFDmjIFVjnSM",
                "types": ["locality", "political"],
            }],
        }
        mock_response.raise_for_status = AsyncMock()
        
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = AsyncMock()
        
        with patch("app.services.geocoding.httpx.AsyncClient", return_value=mock_client):
            with patch("app.services.geocoding.get_settings") as mock_settings:
                mock_settings.return_value.google_maps_api_key = "fake-key"
                
                result = await geocode_address(
                    "Bogotá, Colombia",
                    input_granularity=PRECISION_CITY,
                    country="CO"
                )
        
        # Verify the API was called with region=co
        call_args = mock_client.get.call_args
        params = call_args.kwargs.get("params", {})
        
        config = get_country_config("CO")
        assert params["region"] == config.geocode_region
        assert params["language"] == config.geocode_language
    
    async def test_br_still_uses_region_br(self):
        """Brazil geocoding still uses region=br (unchanged)."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "status": "OK",
            "results": [{
                "geometry": {
                    "location": {"lat": -22.9068, "lng": -43.1729},
                    "location_type": "GEOMETRIC_CENTER",
                },
                "formatted_address": "Rio de Janeiro, Brasil",
                "place_id": "ChIJW6AIkVXemwARTtIvZ2xC3FA",
                "types": ["locality", "political"],
            }],
        }
        mock_response.raise_for_status = AsyncMock()
        
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = AsyncMock()
        
        with patch("app.services.geocoding.httpx.AsyncClient", return_value=mock_client):
            with patch("app.services.geocoding.get_settings") as mock_settings:
                mock_settings.return_value.google_maps_api_key = "fake-key"
                
                result = await geocode_address(
                    "Rio de Janeiro, Brasil",
                    input_granularity=PRECISION_CITY,
                    country="BR"
                )
        
        # Verify the API was called with region=br
        call_args = mock_client.get.call_args
        params = call_args.kwargs.get("params", {})
        
        config = get_country_config("BR")
        assert params["region"] == config.geocode_region
        assert params["language"] == config.geocode_language
