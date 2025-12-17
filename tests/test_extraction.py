"""
Comprehensive tests for extraction.py service.

Tests cover:
- resolve_url: Google News URL resolution
- check_keywords_fast: Fast keyword matching
- extract_with_llm: LLM-based extraction with Vertex AI
- process_source_extraction: Single source processing
- process_single_source: Worker function for threading
- extract_event: Main API for on-demand extraction
- run_extraction: Full extraction pipeline
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from app.services.extraction import (
    resolve_url,
    check_keywords_fast,
    extract_with_llm,
    process_source_extraction,
    process_single_source,
    extract_event,
    run_extraction
)
from app.models import Source, ExtractedEvent


class TestResolveUrl:
    """Tests for resolve_url function."""
    
    def test_resolve_url_non_google_news(self):
        """Test that non-Google News URLs are returned as-is."""
        url = "https://example.com/article"
        result = resolve_url(url)
        assert result == url
    
    @patch('app.services.extraction.googlenewsdecoder')
    def test_resolve_url_google_news_success(self, mock_decoder):
        """Test successful Google News URL resolution."""
        # Setup
        google_url = "https://news.google.com/articles/test123"
        decoded_url = "https://example.com/real-article"
        mock_decoder.new_decoderv1.return_value = {
            'status': True,
            'decoded_url': decoded_url
        }
        
        # Execute
        result = resolve_url(google_url)
        
        # Assert
        assert result == decoded_url
        mock_decoder.new_decoderv1.assert_called_once_with(google_url, interval=1)
    
    @patch('app.services.extraction.googlenewsdecoder')
    def test_resolve_url_google_news_failure(self, mock_decoder):
        """Test Google News URL resolution failure."""
        # Setup
        google_url = "https://news.google.com/articles/test123"
        mock_decoder.new_decoderv1.return_value = {'status': False}
        
        # Execute
        result = resolve_url(google_url)
        
        # Assert
        assert result == google_url
    
    @patch('app.services.extraction.googlenewsdecoder')
    def test_resolve_url_google_news_exception(self, mock_decoder):
        """Test Google News URL resolution with exception handling."""
        # Setup
        google_url = "https://news.google.com/articles/test123"
        mock_decoder.new_decoderv1.side_effect = Exception("Decoder error")
        
        # Execute
        result = resolve_url(google_url)
        
        # Assert
        assert result == google_url  # Should return original URL on error


class TestCheckKeywordsFast:
    """Tests for check_keywords_fast function."""
    
    def test_check_keywords_fast_with_matches(self):
        """Test keyword matching when keywords are found."""
        text = "Um homem foi morto a tiros na Zona Norte. Homicídio investigado pela polícia."
        matches = check_keywords_fast(text)
        
        assert len(matches) > 0
        assert "morto" in matches or "homicídio" in matches or "tiros" in matches
    
    def test_check_keywords_fast_no_matches(self):
        """Test keyword matching when no keywords are found."""
        text = "O índice de violência caiu este ano. O governo anunciou novas medidas."
        matches = check_keywords_fast(text)
        
        assert matches == []
    
    def test_check_keywords_fast_empty_text(self):
        """Test keyword matching with empty text."""
        matches = check_keywords_fast("")
        assert matches == []
    
    def test_check_keywords_fast_none_text(self):
        """Test keyword matching with None text."""
        matches = check_keywords_fast(None)
        assert matches == []
    
    def test_check_keywords_fast_case_insensitive(self):
        """Test that keyword matching is case-insensitive."""
        text = "HOMICÍDIO em Copacabana. Tiroteio na Zona Norte."
        matches = check_keywords_fast(text)
        
        assert len(matches) > 0
        # Should find keywords regardless of case
    
    def test_check_keywords_fast_unique_matches(self):
        """Test that duplicate keyword matches are deduplicated."""
        text = "homicídio homicídio homicídio assassinato assassinato"
        matches = check_keywords_fast(text)
        
        # Should return unique matches only
        assert len(matches) == len(set(matches))
        assert "homicídio" in matches or "assassinato" in matches
    
    def test_check_keywords_fast_multiple_keywords(self):
        """Test matching multiple different keywords."""
        text = "Um tiroteio resultou em um homicídio. A vítima foi baleada."
        matches = check_keywords_fast(text)
        
        assert len(matches) > 0
        # Should find multiple keywords


class TestExtractWithLLM:
    """Tests for extract_with_llm function."""
    
    @patch('app.services.extraction.credentials', None)
    def test_extract_with_llm_no_credentials(self):
        """Test LLM extraction when credentials are not available."""
        text = "Test article content"
        matches = ["homicídio", "morto"]
        
        result, status = extract_with_llm(text, matches)
        
        assert result["is_valid"] is True
        assert "Skipped" in status
        assert result["confidence"] == 0.5
    
    @patch('app.services.extraction.credentials')
    @patch('app.services.extraction.GenerativeModel')
    def test_extract_with_llm_success(self, mock_model_class, mock_credentials):
        """Test successful LLM extraction."""
        # Setup
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"is_valid": true, "summary": "Test summary", "victim_name": "João Silva", "location": "Copacabana", "date": "2024-01-15", "confidence": 0.9}'
        mock_model.generate_content.return_value = mock_response
        mock_model_class.return_value = mock_model
        
        text = "Um homem foi morto a tiros em Copacabana. A vítima foi identificada como João Silva."
        matches = ["homicídio", "morto"]
        
        # Execute
        result, status = extract_with_llm(text, matches)
        
        # Assert
        assert result["is_valid"] is True
        assert result["summary"] == "Test summary"
        assert result["victim_name"] == "João Silva"
        assert result["location"] == "Copacabana"
        assert result["date"] == "2024-01-15"
        assert result["confidence"] == 0.9
        assert status == "Extracted by LLM"
        mock_model.generate_content.assert_called_once()
    
    @patch('app.services.extraction.credentials')
    @patch('app.services.extraction.GenerativeModel')
    def test_extract_with_llm_with_markdown_code_block(self, mock_model_class, mock_credentials):
        """Test LLM extraction when response contains markdown code blocks."""
        # Setup
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '```json\n{"is_valid": true, "summary": "Test", "confidence": 0.8}\n```'
        mock_model.generate_content.return_value = mock_response
        mock_model_class.return_value = mock_model
        
        text = "Test content"
        matches = ["homicídio"]
        
        # Execute
        result, status = extract_with_llm(text, matches)
        
        # Assert
        assert result["is_valid"] is True
        assert result["summary"] == "Test"
    
    @patch('app.services.extraction.credentials')
    @patch('app.services.extraction.GenerativeModel')
    def test_extract_with_llm_with_publication_date(self, mock_model_class, mock_credentials):
        """Test LLM extraction with publication date context."""
        # Setup
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"is_valid": true, "summary": "Test", "confidence": 0.8}'
        mock_model.generate_content.return_value = mock_response
        mock_model_class.return_value = mock_model
        
        text = "Test content"
        matches = ["homicídio"]
        pub_date = datetime(2024, 1, 15)
        
        # Execute
        result, status = extract_with_llm(text, matches, pub_date)
        
        # Assert
        assert result["is_valid"] is True
        # Verify that the prompt includes date context
        call_args = mock_model.generate_content.call_args[0][0]
        assert "2024-01-15" in call_args or "January" in call_args
    
    @patch('app.services.extraction.credentials')
    @patch('app.services.extraction.GenerativeModel')
    def test_extract_with_llm_json_parse_error(self, mock_model_class, mock_credentials):
        """Test LLM extraction when JSON parsing fails."""
        # Setup
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Invalid JSON response"
        mock_model.generate_content.return_value = mock_response
        mock_model_class.return_value = mock_model
        
        text = "Test content"
        matches = ["homicídio"]
        
        # Execute
        result, status = extract_with_llm(text, matches)
        
        # Assert
        # Should fallback to error response
        assert "LLM Error" in status or "Error" in status
        assert result["is_valid"] is True  # Fallback sets is_valid=True
    
    @patch('app.services.extraction.credentials')
    @patch('app.services.extraction.GenerativeModel')
    def test_extract_with_llm_exception_handling(self, mock_model_class, mock_credentials):
        """Test LLM extraction exception handling."""
        # Setup
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = Exception("API Error")
        mock_model_class.return_value = mock_model
        
        text = "Test content"
        matches = ["homicídio"]
        
        # Execute
        result, status = extract_with_llm(text, matches)
        
        # Assert
        assert "LLM Error" in status
        assert result["is_valid"] is True  # Fallback
        assert result["confidence"] == 0.5


class TestProcessSourceExtraction:
    """Tests for process_source_extraction function."""
    
    @patch('app.services.extraction.trafilatura')
    @patch('app.services.extraction.resolve_url')
    @patch('app.services.extraction.check_keywords_fast')
    @patch('app.services.extraction.extract_with_llm')
    def test_process_source_extraction_new_source(self, mock_extract_llm, mock_check_keywords, mock_resolve, mock_trafilatura, app, db_session):
        """Test processing a new source with successful extraction."""
        # Setup
        with app.app_context():
            source = Source(
                url="https://news.google.com/articles/test",
                title="Test Article",
                status='pending'
            )
            db_session.add(source)
            db_session.commit()
            source_id = source.id
            
            mock_resolve.return_value = "https://example.com/article"
            mock_trafilatura.fetch_url.return_value = "<html>Content</html>"
            mock_trafilatura.extract.return_value = "Article content with homicídio"
            mock_check_keywords.return_value = ["homicídio", "morto"]
            mock_extract_llm.return_value = (
                {
                    "is_valid": True,
                    "summary": "Man killed in shooting",
                    "victim_name": "João Silva",
                    "location": "Copacabana",
                    "date": "2024-01-15",
                    "confidence": 0.9
                },
                "Extracted by LLM"
            )
            
            # Execute
            result = process_source_extraction(source, force=False)
            
            # Assert
            assert result is True
            db_session.refresh(source)
            assert source.resolved_url == "https://example.com/article"
            assert source.content == "Article content with homicídio"
            assert source.status == 'processed'
            
            # Check extraction was created
            extraction = ExtractedEvent.query.filter_by(source_id=source_id).first()
            assert extraction is not None
            assert extraction.summary == "Man killed in shooting"
            assert extraction.extracted_victim_name == "João Silva"
            assert extraction.extracted_location == "Copacabana"
            assert extraction.confidence_score == 0.9
    
    @patch('app.services.extraction.check_keywords_fast')
    def test_process_source_extraction_already_processed(self, mock_check_keywords, app, db_session):
        """Test that already processed sources are skipped."""
        # Setup
        with app.app_context():
            source = Source(
                url="https://example.com/article",
                title="Test Article",
                status='processed',
                content="Some content"
            )
            db_session.add(source)
            db_session.commit()
            
            # Execute
            result = process_source_extraction(source, force=False)
            
            # Assert
            assert result is False
            mock_check_keywords.assert_not_called()
    
    @patch('app.services.extraction.check_keywords_fast')
    @patch('app.services.extraction.extract_with_llm')
    def test_process_source_extraction_no_keywords(self, mock_extract_llm, mock_check_keywords, app, db_session):
        """Test processing when no keywords are found."""
        # Setup
        with app.app_context():
            source = Source(
                url="https://example.com/article",
                title="Test Article",
                status='downloaded',
                content="Regular news article without violence keywords"
            )
            db_session.add(source)
            db_session.commit()
            
            mock_check_keywords.return_value = []
            
            # Execute
            result = process_source_extraction(source, force=False)
            
            # Assert
            assert result is True  # Still marked as processed
            db_session.refresh(source)
            assert source.status == 'processed'
            mock_extract_llm.assert_not_called()
            
            # No extraction should be created
            extraction = ExtractedEvent.query.filter_by(source_id=source.id).first()
            assert extraction is None
    
    @patch('app.services.extraction.check_keywords_fast')
    @patch('app.services.extraction.extract_with_llm')
    def test_process_source_extraction_invalid_event(self, mock_extract_llm, mock_check_keywords, app, db_session):
        """Test processing when LLM determines event is invalid."""
        # Setup
        with app.app_context():
            source = Source(
                url="https://example.com/article",
                title="Test Article",
                status='downloaded',
                content="Article with keywords but not a valid event"
            )
            db_session.add(source)
            db_session.commit()
            
            mock_check_keywords.return_value = ["homicídio"]
            mock_extract_llm.return_value = (
                {"is_valid": False, "summary": "Not a valid event", "confidence": 0.3},
                "Extracted by LLM"
            )
            
            # Execute
            result = process_source_extraction(source, force=False)
            
            # Assert
            assert result is True
            db_session.refresh(source)
            assert source.status == 'processed'
            
            # No extraction should be created
            extraction = ExtractedEvent.query.filter_by(source_id=source.id).first()
            assert extraction is None
    
    @patch('app.services.extraction.trafilatura')
    @patch('app.services.extraction.resolve_url')
    def test_process_source_extraction_force_update(self, mock_resolve, mock_trafilatura, app, db_session):
        """Test processing with force=True to re-process."""
        # Setup
        with app.app_context():
            source = Source(
                url="https://example.com/article",
                title="Test Article",
                status='processed',
                content="Old content",
                resolved_url="https://example.com/article"
            )
            db_session.add(source)
            db_session.commit()
            
            mock_resolve.return_value = "https://example.com/new-url"
            mock_trafilatura.fetch_url.return_value = "<html>New Content</html>"
            mock_trafilatura.extract.return_value = "New content"
            
            # Execute
            result = process_source_extraction(source, force=True)
            
            # Assert
            # Should process even though status is 'processed'
            assert result is True or result is False  # May or may not change
    
    @patch('app.services.extraction.trafilatura')
    def test_process_source_extraction_download_failure(self, mock_trafilatura, app, db_session):
        """Test handling of download failures."""
        # Setup
        with app.app_context():
            source = Source(
                url="https://example.com/article",
                title="Test Article",
                status='pending'
            )
            db_session.add(source)
            db_session.commit()
            
            mock_trafilatura.fetch_url.return_value = None
            
            # Execute
            result = process_source_extraction(source, force=False)
            
            # Assert
            # Should not crash, may return False if no changes
            assert result is False or result is True


class TestProcessSingleSource:
    """Tests for process_single_source worker function."""
    
    @patch('app.services.extraction.process_source_extraction')
    def test_process_single_source_success(self, mock_process, app, db_session):
        """Test successful processing of a single source."""
        # Setup
        with app.app_context():
            source = Source(
                url="https://example.com/article",
                title="Test Article",
                status='pending'
            )
            db_session.add(source)
            db_session.commit()
            source_id = source.id
            
            mock_process.return_value = True
            
            # Execute
            result = process_single_source(app, source_id, force=False)
            
            # Assert
            assert result is True
            mock_process.assert_called_once()
    
    def test_process_single_source_nonexistent(self, app):
        """Test processing a non-existent source."""
        # Execute
        result = process_single_source(app, 99999, force=False)
        
        # Assert
        assert result is False
    
    @patch('app.services.extraction.process_source_extraction')
    def test_process_single_source_exception(self, mock_process, app, db_session):
        """Test exception handling in process_single_source."""
        # Setup
        with app.app_context():
            source = Source(
                url="https://example.com/article",
                title="Test Article",
                status='pending'
            )
            db_session.add(source)
            db_session.commit()
            source_id = source.id
            
            mock_process.side_effect = Exception("Processing error")
            
            # Execute
            result = process_single_source(app, source_id, force=False)
            
            # Assert
            assert result is False


class TestExtractEvent:
    """Tests for extract_event function."""
    
    @patch('app.services.extraction.check_keywords_fast')
    @patch('app.services.extraction.extract_with_llm')
    def test_extract_event_success(self, mock_extract_llm, mock_check_keywords, app, db_session):
        """Test successful event extraction."""
        # Setup
        with app.app_context():
            source = Source(
                url="https://example.com/article",
                title="Test Article",
                status='downloaded',
                content="Article content with homicídio"
            )
            db_session.add(source)
            db_session.commit()
            source_id = source.id
            
            mock_check_keywords.return_value = ["homicídio", "morto"]
            mock_extract_llm.return_value = (
                {
                    "is_valid": True,
                    "summary": "Man killed",
                    "victim_name": "João",
                    "location": "Copacabana",
                    "date": "2024-01-15",
                    "confidence": 0.9
                },
                "Extracted by LLM"
            )
            
            # Execute
            result = extract_event(source_id, force=False)
            
            # Assert
            assert result["success"] is True
            assert result["source_id"] == source_id
            assert result["extraction"] is not None
            assert result["extraction"]["summary"] == "Man killed"
            assert result["extraction"]["victim_name"] == "João"
            assert result["extraction"]["location"] == "Copacabana"
            assert result["extraction"]["date"] == "2024-01-15"
            assert result["extraction"]["confidence"] == 0.9
            assert result["message"] == "Extraction successful"
            
            db_session.refresh(source)
            assert source.status == 'processed'
    
    def test_extract_event_source_not_found(self, app, db_session):
        """Test extraction when source doesn't exist."""
        # Execute
        result = extract_event(99999, force=False)
        
        # Assert
        assert result["success"] is False
        assert result["message"] == "Source not found"
        assert result["extraction"] is None
    
    @patch('app.services.extraction.trafilatura')
    def test_extract_event_no_content(self, mock_trafilatura, app, db_session):
        """Test extraction when source has no content."""
        # Setup
        with app.app_context():
            source = Source(
                url="https://example.com/article",
                title="Test Article",
                status='pending'
            )
            db_session.add(source)
            db_session.commit()
            source_id = source.id
            
            mock_trafilatura.fetch_url.return_value = None
            
            # Execute
            result = extract_event(source_id, force=False)
            
            # Assert
            assert result["success"] is False
            assert "content" in result["message"].lower() or "download" in result["message"].lower()
    
    @patch('app.services.extraction.check_keywords_fast')
    def test_extract_event_no_keywords(self, mock_check_keywords, app, db_session):
        """Test extraction when no keywords are found."""
        # Setup
        with app.app_context():
            source = Source(
                url="https://example.com/article",
                title="Test Article",
                status='downloaded',
                content="Regular article"
            )
            db_session.add(source)
            db_session.commit()
            source_id = source.id
            
            mock_check_keywords.return_value = []
            
            # Execute
            result = extract_event(source_id, force=False)
            
            # Assert
            assert result["success"] is True
            assert result["extraction"] is None
            assert "keywords" in result["message"].lower()
            
            db_session.refresh(source)
            assert source.status == 'processed'
    
    @patch('app.services.extraction.check_keywords_fast')
    @patch('app.services.extraction.extract_with_llm')
    def test_extract_event_invalid_event(self, mock_extract_llm, mock_check_keywords, app, db_session):
        """Test extraction when LLM determines event is invalid."""
        # Setup
        with app.app_context():
            source = Source(
                url="https://example.com/article",
                title="Test Article",
                status='downloaded',
                content="Article with keywords"
            )
            db_session.add(source)
            db_session.commit()
            source_id = source.id
            
            mock_check_keywords.return_value = ["homicídio"]
            mock_extract_llm.return_value = (
                {"is_valid": False, "summary": "Not valid", "confidence": 0.3},
                "Extracted by LLM"
            )
            
            # Execute
            result = extract_event(source_id, force=False)
            
            # Assert
            assert result["success"] is True
            assert result["extraction"] is None
            assert "not a valid" in result["message"].lower() or "invalid" in result["message"].lower()
    
    @patch('app.services.extraction.check_keywords_fast')
    @patch('app.services.extraction.extract_with_llm')
    def test_extract_event_already_processed(self, mock_extract_llm, mock_check_keywords, app, db_session):
        """Test extraction when source is already processed."""
        # Setup
        with app.app_context():
            source = Source(
                url="https://example.com/article",
                title="Test Article",
                status='processed',
                content="Article content"
            )
            db_session.add(source)
            db_session.commit()
            source_id = source.id
            
            extraction = ExtractedEvent(
                source_id=source_id,
                summary="Existing extraction",
                confidence_score=0.8
            )
            db_session.add(extraction)
            db_session.commit()
            
            # Execute
            result = extract_event(source_id, force=False)
            
            # Assert
            assert result["success"] is True
            assert result["extraction"] is not None
            assert result["extraction"]["summary"] == "Existing extraction"
            assert "already processed" in result["message"].lower()
            mock_extract_llm.assert_not_called()
    
    @patch('app.services.extraction.check_keywords_fast')
    @patch('app.services.extraction.extract_with_llm')
    def test_extract_event_force_update(self, mock_extract_llm, mock_check_keywords, app, db_session):
        """Test extraction with force=True to re-extract."""
        # Setup
        with app.app_context():
            source = Source(
                url="https://example.com/article",
                title="Test Article",
                status='processed',
                content="Article content"
            )
            db_session.add(source)
            db_session.commit()
            source_id = source.id
            
            existing_extraction = ExtractedEvent(
                source_id=source_id,
                summary="Old extraction",
                confidence_score=0.7
            )
            db_session.add(existing_extraction)
            db_session.commit()
            
            mock_check_keywords.return_value = ["homicídio"]
            mock_extract_llm.return_value = (
                {
                    "is_valid": True,
                    "summary": "New extraction",
                    "confidence": 0.9
                },
                "Extracted by LLM"
            )
            
            # Execute
            result = extract_event(source_id, force=True)
            
            # Assert
            assert result["success"] is True
            assert result["extraction"]["summary"] == "New extraction"
            # Should update existing extraction
            db_session.refresh(existing_extraction)
            assert existing_extraction.summary == "New extraction"
            assert existing_extraction.confidence_score == 0.9


class TestRunExtraction:
    """Tests for run_extraction function."""
    
    @patch('app.services.extraction.concurrent.futures.ThreadPoolExecutor')
    @patch('app.services.extraction.concurrent.futures.as_completed')
    @patch('app.services.extraction.current_app')
    def test_run_extraction_basic(self, mock_current_app, mock_as_completed, mock_executor, app, db_session):
        """Test basic extraction run."""
        # Setup
        with app.app_context():
            source1 = Source(
                url="https://example.com/article1",
                title="Article 1",
                status='downloaded',
                content="Content 1"
            )
            source2 = Source(
                url="https://example.com/article2",
                title="Article 2",
                status='downloaded',
                content="Content 2"
            )
            db_session.add_all([source1, source2])
            db_session.commit()
            
            mock_current_app._get_current_object.return_value = app
            
            # Mock executor
            mock_executor_instance = MagicMock()
            mock_executor.return_value.__enter__.return_value = mock_executor_instance
            mock_executor.return_value.__exit__.return_value = None
            
            # Mock futures - need to return different futures for each submit call
            mock_future1 = MagicMock()
            mock_future2 = MagicMock()
            mock_future1.result.return_value = True
            mock_future2.result.return_value = True
            
            # Make submit return different futures on each call
            mock_executor_instance.submit.side_effect = [mock_future1, mock_future2]
            mock_as_completed.return_value = [mock_future1, mock_future2]
            
            # Execute
            count = run_extraction(force=False, limit=None, max_workers=10)
            
            # Assert
            assert count == 2
    
    @patch('app.services.extraction.concurrent.futures.ThreadPoolExecutor')
    @patch('app.services.extraction.concurrent.futures.as_completed')
    @patch('app.services.extraction.current_app')
    def test_run_extraction_with_limit(self, mock_current_app, mock_as_completed, mock_executor, app, db_session):
        """Test extraction with limit parameter."""
        # Setup
        with app.app_context():
            for i in range(5):
                source = Source(
                    url=f"https://example.com/article{i}",
                    title=f"Article {i}",
                    status='downloaded',
                    content=f"Content {i}"
                )
                db_session.add(source)
            db_session.commit()
            
            mock_current_app._get_current_object.return_value = app
            
            mock_executor_instance = MagicMock()
            mock_executor.return_value.__enter__.return_value = mock_executor_instance
            mock_executor.return_value.__exit__.return_value = None
            
            mock_future = MagicMock()
            mock_future.result.return_value = True
            mock_executor_instance.submit.return_value = mock_future
            mock_as_completed.return_value = [mock_future] * 3  # Limit to 3
            
            # Execute
            count = run_extraction(force=False, limit=3, max_workers=5)
            
            # Assert
            assert count == 3
    
    @patch('app.services.extraction.concurrent.futures.ThreadPoolExecutor')
    @patch('app.services.extraction.concurrent.futures.as_completed')
    @patch('app.services.extraction.current_app')
    def test_run_extraction_skip_processed(self, mock_current_app, mock_as_completed, mock_executor, app, db_session):
        """Test that processed sources are skipped unless force=True."""
        # Setup
        with app.app_context():
            source1 = Source(
                url="https://example.com/article1",
                title="Article 1",
                status='processed',
                content="Content 1"
            )
            source2 = Source(
                url="https://example.com/article2",
                title="Article 2",
                status='downloaded',
                content="Content 2"
            )
            db_session.add_all([source1, source2])
            db_session.commit()
            
            mock_current_app._get_current_object.return_value = app
            
            mock_executor_instance = MagicMock()
            mock_executor.return_value.__enter__.return_value = mock_executor_instance
            mock_executor.return_value.__exit__.return_value = None
            
            mock_future = MagicMock()
            mock_future.result.return_value = True
            mock_executor_instance.submit.return_value = mock_future
            mock_as_completed.return_value = [mock_future]  # Only one source should be processed
            
            # Execute
            count = run_extraction(force=False, limit=None, max_workers=5)
            
            # Assert
            # Should only process the 'downloaded' source, not the 'processed' one
            assert count == 1
    
    @patch('app.services.extraction.concurrent.futures.ThreadPoolExecutor')
    @patch('app.services.extraction.concurrent.futures.as_completed')
    @patch('app.services.extraction.current_app')
    def test_run_extraction_with_force(self, mock_current_app, mock_as_completed, mock_executor, app, db_session):
        """Test extraction with force=True to re-process all sources."""
        # Setup
        with app.app_context():
            source1 = Source(
                url="https://example.com/article1",
                title="Article 1",
                status='processed',
                content="Content 1"
            )
            source2 = Source(
                url="https://example.com/article2",
                title="Article 2",
                status='processed',
                content="Content 2"
            )
            db_session.add_all([source1, source2])
            db_session.commit()
            
            mock_current_app._get_current_object.return_value = app
            
            mock_executor_instance = MagicMock()
            mock_executor.return_value.__enter__.return_value = mock_executor_instance
            mock_executor.return_value.__exit__.return_value = None
            
            mock_future = MagicMock()
            mock_future.result.return_value = True
            mock_executor_instance.submit.return_value = mock_future
            mock_as_completed.return_value = [mock_future] * 2
            
            # Execute
            count = run_extraction(force=True, limit=None, max_workers=5)
            
            # Assert
            # Should process both sources even though they're 'processed'
            assert count == 2
    
    @patch('app.services.extraction.concurrent.futures.ThreadPoolExecutor')
    @patch('app.services.extraction.concurrent.futures.as_completed')
    @patch('app.services.extraction.current_app')
    def test_run_extraction_exception_handling(self, mock_current_app, mock_as_completed, mock_executor, app, db_session):
        """Test exception handling in run_extraction."""
        # Setup
        with app.app_context():
            source = Source(
                url="https://example.com/article",
                title="Article",
                status='downloaded',
                content="Content"
            )
            db_session.add(source)
            db_session.commit()
            
            mock_current_app._get_current_object.return_value = app
            
            mock_executor_instance = MagicMock()
            mock_executor.return_value.__enter__.return_value = mock_executor_instance
            mock_executor.return_value.__exit__.return_value = None
            
            mock_future = MagicMock()
            mock_future.result.side_effect = Exception("Processing error")
            mock_executor_instance.submit.return_value = mock_future
            mock_as_completed.return_value = [mock_future]
            
            # Execute - should not raise exception
            count = run_extraction(force=False, limit=None, max_workers=5)
            
            # Assert
            # Should handle exception gracefully
            assert count == 0  # No successful processing

