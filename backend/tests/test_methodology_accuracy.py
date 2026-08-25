"""Tests for methodology copy accuracy against live country registry."""

from app.country_registry import BRAZIL_CONFIG


def test_brazil_city_count_is_52():
    """Verify Brazil config has exactly 52 cities as claimed in methodology."""
    assert len(BRAZIL_CONFIG.cities) == 52, (
        f"Methodology claims 52 Brazilian cities, but config has {len(BRAZIL_CONFIG.cities)}. "
        f"Update frontend/src/lib/methodology.ts if the city list changed."
    )


def test_brazil_cities_includes_major_metros():
    """Verify Brazil config includes the major metros mentioned in methodology."""
    cities_str = " ".join(BRAZIL_CONFIG.cities)
    
    # Major metros (2M+) from methodology
    assert "São Paulo" in cities_str
    assert "Rio de Janeiro" in cities_str
    assert "Brasília" in cities_str
    assert "Salvador" in cities_str
    assert "Fortaleza" in cities_str
    assert "Belo Horizonte" in cities_str
    assert "Manaus" in cities_str


def test_brazil_cities_includes_smaller_capitals():
    """Verify Brazil config includes smaller capitals mentioned in methodology."""
    cities_str = " ".join(BRAZIL_CONFIG.cities)
    
    # Smaller capitals from methodology
    assert "Florianópolis" in cities_str
    assert "Vitória" in cities_str
    assert "Macapá" in cities_str
    assert "Boa Vista" in cities_str
    assert "Rio Branco" in cities_str
    assert "Palmas" in cities_str
