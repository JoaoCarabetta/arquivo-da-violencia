"""
Comprehensive tests for enrichment.py service.

Tests cover:
- normalize_text: Text normalization for comparison
- fuzzy_match_score: Fuzzy string matching
- extract_neighborhood: Neighborhood extraction from location strings
- calculate_match_score: Matching score calculation between extraction and incident
- find_candidate_incidents: Finding candidate incidents by date range
- find_matching_incident: Finding best matching incident
- create_incident_from_extraction: Creating new incidents from extractions
- run_enrichment: Full enrichment pipeline
- link_extraction_to_incident: Manual linking
"""

import pytest
from datetime import datetime, timedelta
from app.services.enrichment import (
    normalize_text,
    fuzzy_match_score,
    extract_neighborhood,
    calculate_match_score,
    find_candidate_incidents,
    find_matching_incident,
    create_incident_from_extraction,
    run_enrichment,
    link_extraction_to_incident
)
from app.models import ExtractedEvent, Incident, Source


class TestNormalizeText:
    """Tests for normalize_text function."""
    
    def test_normalize_text_basic(self):
        """Test basic text normalization."""
        assert normalize_text("  Hello World  ") == "hello world"
        assert normalize_text("TEST") == "test"
        assert normalize_text("Mixed Case Text") == "mixed case text"
    
    def test_normalize_text_empty(self):
        """Test normalization of empty/None text."""
        assert normalize_text("") == ""
        assert normalize_text(None) == ""
        assert normalize_text("   ") == ""
    
    def test_normalize_text_special_chars(self):
        """Test normalization preserves special characters."""
        assert normalize_text("São Paulo") == "são paulo"
        assert normalize_text("Rua X, Bairro Y") == "rua x, bairro y"


class TestFuzzyMatchScore:
    """Tests for fuzzy_match_score function."""
    
    def test_fuzzy_match_score_exact_match(self):
        """Test exact string match."""
        assert fuzzy_match_score("hello", "hello") == 1.0
        assert fuzzy_match_score("Rio de Janeiro", "Rio de Janeiro") == 1.0
    
    def test_fuzzy_match_score_similar(self):
        """Test similar strings."""
        score = fuzzy_match_score("João Silva", "Joao Silva")
        assert score > 0.8  # Should be high similarity
    
    def test_fuzzy_match_score_different(self):
        """Test different strings."""
        score = fuzzy_match_score("Rio de Janeiro", "São Paulo")
        assert score < 0.5  # Should be low similarity
    
    def test_fuzzy_match_score_empty(self):
        """Test with empty strings."""
        assert fuzzy_match_score("", "hello") == 0.0
        assert fuzzy_match_score("hello", "") == 0.0
        assert fuzzy_match_score("", "") == 0.0
        assert fuzzy_match_score(None, "hello") == 0.0
        assert fuzzy_match_score("hello", None) == 0.0
    
    def test_fuzzy_match_score_case_insensitive(self):
        """Test that matching is case insensitive."""
        score1 = fuzzy_match_score("Hello", "hello")
        score2 = fuzzy_match_score("HELLO", "hello")
        assert score1 == 1.0
        assert score2 == 1.0
    
    def test_fuzzy_match_score_whitespace(self):
        """Test that whitespace is normalized."""
        score = fuzzy_match_score("  hello  world  ", "hello world")
        # After normalization, both become "hello world", so score should be 1.0
        # Note: SequenceMatcher may still give slightly less than 1.0 due to character comparison
        assert score >= 0.95  # Should be very high after normalization


class TestExtractNeighborhood:
    """Tests for extract_neighborhood function."""
    
    def test_extract_neighborhood_with_bairro(self):
        """Test extraction when 'bairro' is present."""
        location = "Rua X, Bairro Copacabana, Rio de Janeiro"
        assert extract_neighborhood(location) == "copacabana"
    
    def test_extract_neighborhood_with_comunidade(self):
        """Test extraction when 'comunidade' is present."""
        location = "Comunidade Rocinha"
        assert extract_neighborhood(location) == "rocinha"
    
    def test_extract_neighborhood_with_morro(self):
        """Test extraction when 'morro' is present."""
        location = "Morro do Alemão"
        assert extract_neighborhood(location) == "do alemão"
    
    def test_extract_neighborhood_with_favela(self):
        """Test extraction when 'favela' is present."""
        location = "Favela da Maré"
        assert extract_neighborhood(location) == "da maré"
    
    def test_extract_neighborhood_with_complexo(self):
        """Test extraction when 'complexo' is present."""
        location = "Complexo do Alemão"
        assert extract_neighborhood(location) == "do alemão"
    
    def test_extract_neighborhood_no_indicator(self):
        """Test extraction when no indicator is present."""
        location = "Copacabana"
        assert extract_neighborhood(location) == "Copacabana"
    
    def test_extract_neighborhood_empty(self):
        """Test extraction with empty/None location."""
        assert extract_neighborhood("") is None
        assert extract_neighborhood(None) is None
    
    def test_extract_neighborhood_multiple_commas(self):
        """Test extraction with multiple comma-separated parts."""
        location = "Rua X, Bairro Y, Zona Sul, Rio de Janeiro"
        assert extract_neighborhood(location) == "y"
    
    def test_extract_neighborhood_case_insensitive(self):
        """Test that extraction is case insensitive."""
        location = "BAIRRO COPACABANA"
        assert extract_neighborhood(location) == "copacabana"


class TestCalculateMatchScore:
    """Tests for calculate_match_score function."""
    
    def test_calculate_match_score_victim_name_match(self, app, db_session):
        """Test scoring with matching victim name."""
        with app.app_context():
            extraction = ExtractedEvent(
                extracted_victim_name="João Silva",
                extracted_location="Copacabana",
                summary="Homicide occurred"
            )
            
            incident = Incident(
                title="Morte de João Silva",
                date=datetime(2024, 1, 15),
                location="Copacabana",
                description="Homicide occurred"
            )
            
            score, components = calculate_match_score(extraction, incident)
            assert score > 0.5  # Should have high score due to name match
            assert any("victim" in comp for comp in components)
    
    def test_calculate_match_score_location_match(self, app, db_session):
        """Test scoring with matching location."""
        with app.app_context():
            extraction = ExtractedEvent(
                extracted_victim_name="Unknown",
                extracted_location="Copacabana, Rio de Janeiro",
                summary="Homicide"
            )
            
            incident = Incident(
                title="Homicide",
                date=datetime(2024, 1, 15),
                location="Copacabana",
                neighborhood="Copacabana"
            )
            
            score, components = calculate_match_score(extraction, incident)
            assert score > 0.0
            assert any("location" in comp for comp in components)
    
    def test_calculate_match_score_summary_match(self, app, db_session):
        """Test scoring with matching summary."""
        with app.app_context():
            extraction = ExtractedEvent(
                extracted_victim_name=None,
                extracted_location=None,
                summary="Young man killed in shooting"
            )
            
            incident = Incident(
                title="Homicide",
                date=datetime(2024, 1, 15),
                description="Young man killed in shooting"
            )
            
            score, components = calculate_match_score(extraction, incident)
            assert score > 0.0
            assert any("summary" in comp for comp in components)
    
    def test_calculate_match_score_no_matches(self, app, db_session):
        """Test scoring with no matches."""
        with app.app_context():
            extraction = ExtractedEvent(
                extracted_victim_name="João Silva",
                extracted_location="Copacabana",
                summary="Homicide"
            )
            
            incident = Incident(
                title="Different Person",
                date=datetime(2024, 1, 15),
                location="Ipanema",
                description="Different event"
            )
            
            score, components = calculate_match_score(extraction, incident)
            assert score < 0.3  # Should be low score
    
    def test_calculate_match_score_victim_in_description(self, app, db_session):
        """Test that victim name is also checked in description."""
        with app.app_context():
            extraction = ExtractedEvent(
                extracted_victim_name="João Silva",
                extracted_location=None,
                summary=None
            )
            
            incident = Incident(
                title="Homicide",
                date=datetime(2024, 1, 15),
                description="João Silva was killed"
            )
            
            score, components = calculate_match_score(extraction, incident)
            assert score > 0.0
            assert any("victim" in comp for comp in components)
    
    def test_calculate_match_score_neighborhood_comparison(self, app, db_session):
        """Test that neighborhood is extracted and compared."""
        with app.app_context():
            extraction = ExtractedEvent(
                extracted_victim_name=None,
                extracted_location="Rua X, Bairro Copacabana",
                summary=None
            )
            
            incident = Incident(
                title="Homicide",
                date=datetime(2024, 1, 15),
                location="Copacabana",
                neighborhood="Copacabana"
            )
            
            score, components = calculate_match_score(extraction, incident)
            assert score > 0.0
            assert any("location" in comp for comp in components)
    
    def test_calculate_match_score_missing_fields(self, app, db_session):
        """Test scoring with missing fields."""
        with app.app_context():
            extraction = ExtractedEvent(
                extracted_victim_name=None,
                extracted_location=None,
                summary=None
            )
            
            incident = Incident(
                title="Homicide",
                date=datetime(2024, 1, 15)
            )
            
            score, components = calculate_match_score(extraction, incident)
            assert score == 0.0
            assert len(components) == 0


class TestFindCandidateIncidents:
    """Tests for find_candidate_incidents function."""
    
    def test_find_candidate_incidents_within_date_range(self, app, db_session):
        """Test finding candidates within date tolerance."""
        with app.app_context():
            # Create incidents
            incident1 = Incident(
                title="Incident 1",
                date=datetime(2024, 1, 15),
                location="Location 1"
            )
            incident2 = Incident(
                title="Incident 2",
                date=datetime(2024, 1, 16),  # Within 1 day tolerance
                location="Location 2"
            )
            incident3 = Incident(
                title="Incident 3",
                date=datetime(2024, 1, 20),  # Outside tolerance
                location="Location 3"
            )
            db_session.add_all([incident1, incident2, incident3])
            db_session.commit()
            
            # Create extraction with date
            extraction = ExtractedEvent(
                extracted_date=datetime(2024, 1, 15),
                extracted_location="Location"
            )
            
            candidates = find_candidate_incidents(extraction)
            candidate_ids = [c.id for c in candidates]
            assert incident1.id in candidate_ids
            assert incident2.id in candidate_ids
            assert incident3.id not in candidate_ids
    
    def test_find_candidate_incidents_no_date(self, app, db_session):
        """Test that extraction without date returns no candidates."""
        with app.app_context():
            extraction = ExtractedEvent(
                extracted_date=None,
                extracted_location="Location"
            )
            
            candidates = find_candidate_incidents(extraction)
            assert candidates == []
    
    def test_find_candidate_incidents_date_tolerance(self, app, db_session):
        """Test that date tolerance is applied correctly."""
        with app.app_context():
            # Create incidents at boundaries
            incident1 = Incident(
                title="Incident 1",
                date=datetime(2024, 1, 14),  # Exactly 1 day before
                location="Location 1"
            )
            incident2 = Incident(
                title="Incident 2",
                date=datetime(2024, 1, 16),  # Exactly 1 day after
                location="Location 2"
            )
            incident3 = Incident(
                title="Incident 3",
                date=datetime(2024, 1, 13),  # 2 days before (outside)
                location="Location 3"
            )
            db_session.add_all([incident1, incident2, incident3])
            db_session.commit()
            
            extraction = ExtractedEvent(
                extracted_date=datetime(2024, 1, 15),
                extracted_location="Location"
            )
            
            candidates = find_candidate_incidents(extraction)
            candidate_ids = [c.id for c in candidates]
            assert incident1.id in candidate_ids
            assert incident2.id in candidate_ids
            assert incident3.id not in candidate_ids
    
    def test_find_candidate_incidents_no_incidents(self, app, db_session):
        """Test when no incidents exist."""
        with app.app_context():
            extraction = ExtractedEvent(
                extracted_date=datetime(2024, 1, 15),
                extracted_location="Location"
            )
            
            candidates = find_candidate_incidents(extraction)
            assert candidates == []
    
    def test_find_candidate_incidents_incidents_without_date(self, app, db_session):
        """Test that incidents without dates are excluded."""
        with app.app_context():
            incident1 = Incident(
                title="Incident 1",
                date=datetime(2024, 1, 15),
                location="Location 1"
            )
            incident2 = Incident(
                title="Incident 2",
                date=None,  # No date
                location="Location 2"
            )
            db_session.add_all([incident1, incident2])
            db_session.commit()
            
            extraction = ExtractedEvent(
                extracted_date=datetime(2024, 1, 15),
                extracted_location="Location"
            )
            
            candidates = find_candidate_incidents(extraction)
            candidate_ids = [c.id for c in candidates]
            assert incident1.id in candidate_ids
            assert incident2.id not in candidate_ids


class TestFindMatchingIncident:
    """Tests for find_matching_incident function."""
    
    def test_find_matching_incident_high_score(self, app, db_session):
        """Test finding incident with score above threshold."""
        with app.app_context():
            incident = Incident(
                title="Morte de João Silva",
                date=datetime(2024, 1, 15),
                location="Copacabana",
                description="João Silva was killed"
            )
            db_session.add(incident)
            db_session.commit()
            
            extraction = ExtractedEvent(
                extracted_date=datetime(2024, 1, 15),
                extracted_victim_name="João Silva",
                extracted_location="Copacabana",
                summary="João Silva was killed"
            )
            
            match, score = find_matching_incident(extraction)
            assert match is not None
            assert match.id == incident.id
            assert score >= 0.6  # Above threshold
    
    def test_find_matching_incident_low_score(self, app, db_session):
        """Test when no incident has score above threshold."""
        with app.app_context():
            incident = Incident(
                title="Different Person",
                date=datetime(2024, 1, 15),
                location="Ipanema",
                description="Different event"
            )
            db_session.add(incident)
            db_session.commit()
            
            extraction = ExtractedEvent(
                extracted_date=datetime(2024, 1, 15),
                extracted_victim_name="João Silva",
                extracted_location="Copacabana",
                summary="Different event"
            )
            
            match, score = find_matching_incident(extraction)
            assert match is None
            assert score < 0.6
    
    def test_find_matching_incident_no_candidates(self, app, db_session):
        """Test when no candidate incidents exist."""
        with app.app_context():
            extraction = ExtractedEvent(
                extracted_date=datetime(2024, 1, 15),
                extracted_victim_name="João Silva"
            )
            
            match, score = find_matching_incident(extraction)
            assert match is None
            assert score == 0.0
    
    def test_find_matching_incident_best_match(self, app, db_session):
        """Test that best matching incident is returned."""
        with app.app_context():
            incident1 = Incident(
                title="Morte de João Silva",
                date=datetime(2024, 1, 15),
                location="Copacabana",
                description="João Silva"
            )
            incident2 = Incident(
                title="Different Person",
                date=datetime(2024, 1, 15),
                location="Ipanema",
                description="Different"
            )
            db_session.add_all([incident1, incident2])
            db_session.commit()
            
            extraction = ExtractedEvent(
                extracted_date=datetime(2024, 1, 15),
                extracted_victim_name="João Silva",
                extracted_location="Copacabana"
            )
            
            match, score = find_matching_incident(extraction)
            assert match is not None
            assert match.id == incident1.id  # Should match the better one


class TestCreateIncidentFromExtraction:
    """Tests for create_incident_from_extraction function."""
    
    def test_create_incident_with_victim_name(self, app, db_session):
        """Test creating incident when victim name is available."""
        with app.app_context():
            extraction = ExtractedEvent(
                extracted_date=datetime(2024, 1, 15),
                extracted_victim_name="João Silva",
                extracted_location="Rua X, Bairro Copacabana",
                summary="Homicide occurred"
            )
            
            incident = create_incident_from_extraction(extraction)
            assert incident.title == "Morte de João Silva"
            assert incident.date == datetime(2024, 1, 15)
            assert incident.location == "Rua X, Bairro Copacabana"
            assert incident.city == "Rio de Janeiro"
            assert incident.neighborhood == "copacabana"
            assert incident.description == "Homicide occurred"
            assert incident.confirmed is False
    
    def test_create_incident_without_victim_name(self, app, db_session):
        """Test creating incident when victim name is not available."""
        with app.app_context():
            extraction = ExtractedEvent(
                extracted_date=datetime(2024, 1, 15),
                extracted_victim_name=None,
                extracted_location="Copacabana",
                summary="Homicide"
            )
            
            incident = create_incident_from_extraction(extraction)
            assert "Homicídio" in incident.title
            assert "15/01/2024" in incident.title
            assert incident.date == datetime(2024, 1, 15)
    
    def test_create_incident_without_date(self, app, db_session):
        """Test creating incident when date is not available."""
        with app.app_context():
            extraction = ExtractedEvent(
                extracted_date=None,
                extracted_victim_name=None,
                extracted_location="Copacabana",
                summary="Homicide"
            )
            
            incident = create_incident_from_extraction(extraction)
            assert "Data desconhecida" in incident.title
            assert incident.date is None
    
    def test_create_incident_neighborhood_extraction(self, app, db_session):
        """Test that neighborhood is extracted from location."""
        with app.app_context():
            extraction = ExtractedEvent(
                extracted_date=datetime(2024, 1, 15),
                extracted_victim_name="João Silva",
                extracted_location="Rua X, Bairro Ipanema, Rio de Janeiro",
                summary="Homicide"
            )
            
            incident = create_incident_from_extraction(extraction)
            assert incident.neighborhood == "ipanema"


class TestRunEnrichment:
    """Tests for run_enrichment function."""
    
    def test_run_enrichment_link_to_existing(self, app, db_session):
        """Test linking extraction to existing incident."""
        with app.app_context():
            # Create source and extraction
            source = Source(url="https://example.com/article", title="Article")
            db_session.add(source)
            db_session.flush()
            
            incident = Incident(
                title="Morte de João Silva",
                date=datetime(2024, 1, 15),
                location="Copacabana",
                description="João Silva"
            )
            db_session.add(incident)
            db_session.commit()
            
            extraction = ExtractedEvent(
                source_id=source.id,
                extracted_date=datetime(2024, 1, 15),
                extracted_victim_name="João Silva",
                extracted_location="Copacabana",
                summary="João Silva was killed"
            )
            db_session.add(extraction)
            db_session.commit()
            
            # Run enrichment
            result = run_enrichment(auto_create=False, dry_run=False)
            
            # Verify
            db_session.refresh(extraction)
            assert extraction.incident_id == incident.id
            assert result["linked"] == 1
            assert result["created"] == 0
            assert result["skipped"] == 0
    
    def test_run_enrichment_create_new(self, app, db_session):
        """Test creating new incident for unmatched extraction."""
        with app.app_context():
            # Create source and extraction
            source = Source(url="https://example.com/article", title="Article")
            db_session.add(source)
            db_session.flush()
            
            extraction = ExtractedEvent(
                source_id=source.id,
                extracted_date=datetime(2024, 1, 15),
                extracted_victim_name="João Silva",
                extracted_location="Copacabana",
                summary="Homicide"
            )
            db_session.add(extraction)
            db_session.commit()
            
            # Run enrichment
            result = run_enrichment(auto_create=True, dry_run=False)
            
            # Verify
            db_session.refresh(extraction)
            assert extraction.incident_id is not None
            assert result["linked"] == 0
            assert result["created"] == 1
            assert result["skipped"] == 0
            
            # Check incident was created
            incident = Incident.query.get(extraction.incident_id)
            assert incident is not None
            assert incident.title == "Morte de João Silva"
    
    def test_run_enrichment_skip_when_no_match(self, app, db_session):
        """Test skipping extraction when no match and auto_create=False."""
        with app.app_context():
            # Create source and extraction
            source = Source(url="https://example.com/article", title="Article")
            db_session.add(source)
            db_session.flush()
            
            extraction = ExtractedEvent(
                source_id=source.id,
                extracted_date=datetime(2024, 1, 15),
                extracted_victim_name="João Silva",
                extracted_location="Copacabana",
                summary="Homicide"
            )
            db_session.add(extraction)
            db_session.commit()
            
            # Run enrichment
            result = run_enrichment(auto_create=False, dry_run=False)
            
            # Verify
            db_session.refresh(extraction)
            assert extraction.incident_id is None
            assert result["linked"] == 0
            assert result["created"] == 0
            assert result["skipped"] == 1
    
    def test_run_enrichment_dry_run(self, app, db_session):
        """Test dry run mode doesn't commit changes."""
        with app.app_context():
            # Create source and extraction
            source = Source(url="https://example.com/article", title="Article")
            db_session.add(source)
            db_session.flush()
            
            extraction = ExtractedEvent(
                source_id=source.id,
                extracted_date=datetime(2024, 1, 15),
                extracted_victim_name="João Silva",
                extracted_location="Copacabana",
                summary="Homicide"
            )
            db_session.add(extraction)
            db_session.commit()
            
            # Run enrichment in dry run mode
            result = run_enrichment(auto_create=True, dry_run=True)
            
            # Verify changes were not committed
            db_session.refresh(extraction)
            assert extraction.incident_id is None
            assert result["created"] == 1  # Counts what would happen
    
    def test_run_enrichment_skip_linked_extractions(self, app, db_session):
        """Test that already linked extractions are skipped."""
        with app.app_context():
            # Create source, incident, and linked extraction
            source = Source(url="https://example.com/article", title="Article")
            db_session.add(source)
            db_session.flush()
            
            incident = Incident(
                title="Existing Incident",
                date=datetime(2024, 1, 15)
            )
            db_session.add(incident)
            db_session.commit()
            
            extraction = ExtractedEvent(
                source_id=source.id,
                incident_id=incident.id,  # Already linked
                extracted_date=datetime(2024, 1, 15),
                extracted_victim_name="João Silva"
            )
            db_session.add(extraction)
            db_session.commit()
            
            # Run enrichment
            result = run_enrichment(auto_create=True, dry_run=False)
            
            # Verify
            assert result["linked"] == 0
            assert result["created"] == 0
            assert result["skipped"] == 0  # Not even considered
    
    def test_run_enrichment_skip_extractions_without_date(self, app, db_session):
        """Test that extractions without dates are skipped."""
        with app.app_context():
            # Create source and extraction without date
            source = Source(url="https://example.com/article", title="Article")
            db_session.add(source)
            db_session.flush()
            
            extraction = ExtractedEvent(
                source_id=source.id,
                extracted_date=None,  # No date
                extracted_victim_name="João Silva",
                extracted_location="Copacabana"
            )
            db_session.add(extraction)
            db_session.commit()
            
            # Run enrichment
            result = run_enrichment(auto_create=True, dry_run=False)
            
            # Verify
            assert result["linked"] == 0
            assert result["created"] == 0
            assert result["skipped"] == 0  # Not even considered
    
    def test_run_enrichment_multiple_extractions(self, app, db_session):
        """Test processing multiple extractions."""
        with app.app_context():
            # Create source
            source = Source(url="https://example.com/article", title="Article")
            db_session.add(source)
            db_session.flush()
            
            # Create existing incident
            incident = Incident(
                title="Morte de João Silva",
                date=datetime(2024, 1, 15),
                location="Copacabana",
                description="João Silva"
            )
            db_session.add(incident)
            db_session.commit()
            
            # Create multiple extractions
            extraction1 = ExtractedEvent(
                source_id=source.id,
                extracted_date=datetime(2024, 1, 15),
                extracted_victim_name="João Silva",
                extracted_location="Copacabana",
                summary="João Silva"
            )
            extraction2 = ExtractedEvent(
                source_id=source.id,
                extracted_date=datetime(2024, 1, 16),
                extracted_victim_name="Maria Santos",
                extracted_location="Ipanema",
                summary="Maria Santos"
            )
            db_session.add_all([extraction1, extraction2])
            db_session.commit()
            
            # Run enrichment
            result = run_enrichment(auto_create=True, dry_run=False)
            
            # Verify
            db_session.refresh(extraction1)
            db_session.refresh(extraction2)
            assert extraction1.incident_id == incident.id  # Linked
            assert extraction2.incident_id is not None  # Created
            assert result["linked"] == 1
            assert result["created"] == 1


class TestLinkExtractionToIncident:
    """Tests for link_extraction_to_incident function."""
    
    def test_link_extraction_to_incident_success(self, app, db_session):
        """Test successful manual linking."""
        with app.app_context():
            # Create source, extraction, and incident
            source = Source(url="https://example.com/article", title="Article")
            db_session.add(source)
            db_session.flush()
            
            extraction = ExtractedEvent(
                source_id=source.id,
                extracted_date=datetime(2024, 1, 15)
            )
            incident = Incident(
                title="Test Incident",
                date=datetime(2024, 1, 15)
            )
            db_session.add_all([extraction, incident])
            db_session.commit()
            
            extraction_id = extraction.id
            incident_id = incident.id
            
            # Link
            result = link_extraction_to_incident(extraction_id, incident_id)
            
            # Verify
            assert result["success"] is True
            assert f"Extraction {extraction_id}" in result["message"]
            assert f"Incident {incident_id}" in result["message"]
            assert result["incident_title"] == "Test Incident"
            
            db_session.refresh(extraction)
            assert extraction.incident_id == incident_id
    
    def test_link_extraction_to_incident_extraction_not_found(self, app, db_session):
        """Test linking when extraction doesn't exist."""
        with app.app_context():
            incident = Incident(
                title="Test Incident",
                date=datetime(2024, 1, 15)
            )
            db_session.add(incident)
            db_session.commit()
            
            result = link_extraction_to_incident(99999, incident.id)
            
            assert result["success"] is False
            assert "not found" in result["message"]
    
    def test_link_extraction_to_incident_incident_not_found(self, app, db_session):
        """Test linking when incident doesn't exist."""
        with app.app_context():
            source = Source(url="https://example.com/article", title="Article")
            db_session.add(source)
            db_session.flush()
            
            extraction = ExtractedEvent(
                source_id=source.id,
                extracted_date=datetime(2024, 1, 15)
            )
            db_session.add(extraction)
            db_session.commit()
            
            result = link_extraction_to_incident(extraction.id, 99999)
            
            assert result["success"] is False
            assert "not found" in result["message"]

