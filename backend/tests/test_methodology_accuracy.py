"""Tests for methodology copy accuracy against live country registry."""

from app.country_registry import BRAZIL_CONFIG


def test_methodology_matches_brazil_city_count():
    """
    Verify methodology.ts claims the same city count as BRAZIL_CONFIG.
    
    This test will fail if methodology.ts becomes stale when cities are added/removed.
    DO NOT hardcode both sides to the same number - that defeats the purpose.
    The methodology copy must match the live config count.
    """
    actual_count = len(BRAZIL_CONFIG.cities)
    
    # Read the methodology file
    import pathlib
    methodology_path = pathlib.Path(__file__).parent.parent.parent / "frontend" / "src" / "lib" / "methodology.ts"
    methodology_content = methodology_path.read_text()
    
    # Check that the file doesn't claim wrong counts
    # This is a basic smoke test - the frontend tests do more thorough validation
    assert "63 municípios" not in methodology_content.lower(), (
        "Methodology still claims 63 municipalities (stale)"
    )
    assert "63 municipalities" not in methodology_content.lower(), (
        "Methodology still claims 63 municipalities (stale)"
    )
    
    # The actual count should appear in the cities section
    # We check for the number in context to avoid false matches (line numbers, etc.)
    pt_cities_section = methodology_content[methodology_content.find("id: 'cities'"):methodology_content.find("id: 'cities'")+2000]
    en_cities_section = methodology_content[methodology_content.rfind("id: 'cities'"):methodology_content.rfind("id: 'cities'")+2000]
    
    assert f"{actual_count} municípios" in pt_cities_section or f"{actual_count} municipalities" in en_cities_section, (
        f"Methodology does not claim {actual_count} municipalities (BRAZIL_CONFIG has {actual_count} cities). "
        f"Update frontend/src/lib/methodology.ts when the city list changes."
    )
