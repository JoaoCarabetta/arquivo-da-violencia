"""Tests for classification heuristics with SA countries in-scope."""

import pytest
from app.services.classification_heuristics import should_force_non_violent_death


class TestCountryClassificationHeuristics:
    """Test that SA countries are in-scope for classification."""
    
    def test_colombian_asesinato_is_in_scope(self):
        """Colombian homicide is in-scope (not foreign)."""
        headline = "Asesinato en Bogotá deja dos muertos"
        # Should NOT be forced to non-violent-death (foreign marker removed)
        assert not should_force_non_violent_death(headline)
    
    def test_argentinian_homicidio_is_in_scope(self):
        """Argentinian homicide is in-scope (not foreign)."""
        headline = "Homicidio en Buenos Aires: Un hombre fue asesinado"
        assert not should_force_non_violent_death(headline)
    
    def test_peruvian_shooting_is_in_scope(self):
        """Peruvian shooting is in-scope (not foreign)."""
        headline = "Tiroteo en Lima deja tres muertos"
        assert not should_force_non_violent_death(headline)
    
    def test_bolivian_violence_is_in_scope(self):
        """Bolivian violence is in-scope (not foreign)."""
        headline = "Muerte violenta en La Paz"
        assert not should_force_non_violent_death(headline)
    
    def test_venezuelan_event_is_in_scope(self):
        """Venezuelan event is in-scope (not foreign, even though previously listed)."""
        headline = "Homicidio en Caracas"
        # Venezuela was in the old foreign markers list but should now be in-scope
        assert not should_force_non_violent_death(headline)
    
    def test_us_shooting_still_foreign(self):
        """US shooting is still foreign (out of scope)."""
        headline = "Mass shooting in Texas leaves 5 dead"
        # Should be forced to non-violent-death (US is foreign)
        assert should_force_non_violent_death(headline)
    
    def test_mexican_violence_still_foreign(self):
        """Mexican violence is still foreign (not SA)."""
        headline = "Tiroteo en México deja varios muertos"
        # México is not in South America, should be foreign
        assert should_force_non_violent_death(headline)
    
    def test_brazilian_homicide_is_in_scope(self):
        """Brazilian homicide is obviously in-scope."""
        headline = "Homicídio no Rio de Janeiro deixa dois mortos"
        assert not should_force_non_violent_death(headline)
    
    def test_chilean_femicidio_is_in_scope(self):
        """Chilean femicide is in-scope."""
        headline = "Femicidio en Santiago: mujer asesinada por ex pareja"
        assert not should_force_non_violent_death(headline)
    
    def test_guyanese_murder_is_in_scope(self):
        """Guyana murder (English) is in-scope (not foreign)."""
        headline = "Murder in Georgetown leaves one dead"
        # Should NOT be forced to non-violent-death
        assert not should_force_non_violent_death(headline)
    
    def test_suriname_moord_is_in_scope(self):
        """Suriname moord (Dutch) is in-scope (not foreign)."""
        headline = "Moord in Paramaribo: man doodgeschoten"
        # Should NOT be forced to non-violent-death
        assert not should_force_non_violent_death(headline)
