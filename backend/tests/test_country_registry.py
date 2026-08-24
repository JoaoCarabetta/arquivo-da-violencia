"""Tests for country registry and multi-country support."""

import pytest
from app.country_registry import (
    COUNTRY_CONFIGS,
    ALL_COUNTRIES,
    get_country_config,
    get_country_name,
    is_valid_country,
)


class TestCountryRegistry:
    """Test the country registry structure and data."""
    
    def test_all_12_countries_present(self):
        """Each of the 12 SA countries has a config."""
        expected = {"AR", "BO", "BR", "CL", "CO", "EC", "GY", "PY", "PE", "SR", "UY", "VE"}
        assert set(ALL_COUNTRIES) == expected
        assert len(COUNTRY_CONFIGS) == 12
    
    def test_each_country_has_cities(self):
        """Each country config has at least one city."""
        for country_code in ALL_COUNTRIES:
            config = get_country_config(country_code)
            assert len(config.cities) > 0, f"{country_code} has no cities"
    
    def test_each_country_has_outlets(self):
        """Each country config has at least one news outlet."""
        for country_code in ALL_COUNTRIES:
            config = get_country_config(country_code)
            assert len(config.outlets) > 0, f"{country_code} has no outlets"
    
    def test_each_country_has_google_news_params(self):
        """Each country config has Google News hl/gl/ceid."""
        for country_code in ALL_COUNTRIES:
            config = get_country_config(country_code)
            assert config.google_news_hl, f"{country_code} missing hl"
            assert config.google_news_gl, f"{country_code} missing gl"
            assert config.google_news_ceid, f"{country_code} missing ceid"
    
    def test_each_country_has_geocode_params(self):
        """Each country config has geocode region and language."""
        for country_code in ALL_COUNTRIES:
            config = get_country_config(country_code)
            assert config.geocode_region, f"{country_code} missing geocode_region"
            assert config.geocode_language, f"{country_code} missing geocode_language"
    
    def test_spanish_countries_have_query_terms(self):
        """Spanish-speaking countries have homicide query terms."""
        spanish_countries = ["AR", "BO", "CL", "CO", "EC", "PY", "PE", "UY", "VE"]
        for country_code in spanish_countries:
            config = get_country_config(country_code)
            assert len(config.query_terms) > 0, f"{country_code} has no query terms"
            # Should include at least "homicidio" or "asesinato"
            terms_lower = [t.lower() for t in config.query_terms]
            assert "homicidio" in terms_lower or "asesinato" in terms_lower
    
    def test_guyana_has_english_terms(self):
        """Guyana has English query terms."""
        config = get_country_config("GY")
        assert config.language == "en"
        terms_lower = [t.lower() for t in config.query_terms]
        assert "murder" in terms_lower or "homicide" in terms_lower
    
    def test_suriname_has_dutch_terms(self):
        """Suriname has Dutch query terms."""
        config = get_country_config("SR")
        assert config.language == "nl"
        terms_lower = [t.lower() for t in config.query_terms]
        assert "moord" in terms_lower or "doodslag" in terms_lower
    
    def test_brazil_has_no_explicit_terms(self):
        """Brazil has no explicit query terms (context implicit)."""
        config = get_country_config("BR")
        assert len(config.query_terms) == 0
    
    def test_get_country_name(self):
        """Country name lookup works for all countries."""
        assert get_country_name("BR") == "Brasil"
        assert get_country_name("AR") == "Argentina"
        assert get_country_name("CL") == "Chile"
    
    def test_is_valid_country(self):
        """Country validation works."""
        assert is_valid_country("BR")
        assert is_valid_country("AR")
        assert not is_valid_country("US")
        assert not is_valid_country("MX")
