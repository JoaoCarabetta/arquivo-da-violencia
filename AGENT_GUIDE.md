# Agent Guide - Arquivo da Violencia

This document provides context for AI agents working on this repository.

## Project Overview
**Goal**: Track violence (specifically murders) in Rio de Janeiro using news articles and social media.
**Current State**:
- Fetches news from Google News RSS.
- Resolves encrypted Google News URLs.
- Extracts content and matches keywords ("tiroteio", "homicídio", etc.).
- Stores data in SQLite.
- Displays a simple list of incidents in a Flask web app.

## Development Philosophy: Test-Based Development (TBD)

**All backend code must be developed using Test-Based Development (TBD).**

### Core Principles

1. **Tests First**: Write comprehensive tests BEFORE implementing or modifying functionality
2. **Test Coverage**: Aim for 100% coverage of business logic (services, models, utilities)
3. **Test Quality**: Tests should be:
   - **Fast**: Run in milliseconds, not seconds
   - **Isolated**: Each test is independent and doesn't affect others
   - **Deterministic**: Same input always produces same output
   - **Readable**: Test names clearly describe what they test
   - **Comprehensive**: Cover happy paths, edge cases, and error conditions

4. **No Code Without Tests**: Any new feature or bug fix must include tests
5. **Tests as Documentation**: Tests serve as executable documentation of expected behavior

### Testing Workflow

1. **Red**: Write a failing test that describes the desired behavior
2. **Green**: Write the minimum code to make the test pass
3. **Refactor**: Improve code quality while keeping tests green
4. **Repeat**: Continue this cycle for each feature

## Tech Stack
- **Language**: Python 3.11+
- **Manager**: `uv`
- **Testing**: `pytest`, `pytest-mock`
- **Web**: Flask, Jinja2
- **Database**: SQLite, SQLAlchemy
- **Crawler**: `feedparser`, `trafilatura`, `googlenewsdecoder`
- **CLI**: `click`

## Directory Structure
```text
arquivo-da-violencia/
├── app/
│   ├── __init__.py          # App Factory
│   ├── models.py            # DB Models (Source, ExtractedEvent, Incident)
│   ├── routes.py            # Web Routes
│   ├── templates/           # HTML Templates
│   └── services/            # Core Logic (The Pipeline)
│       ├── ingestion.py     # Stage 1: RSS -> Source
│       ├── extraction.py    # Stage 2: Content/Keywords -> ExtractedEvent
│       ├── enrichment.py    # Stage 3: Link -> Incident
│       ├── keywords.py      # Keyword management
│       └── locations.py     # Location queries
├── tests/                   # Test Suite
│   ├── __init__.py
│   ├── conftest.py          # Pytest fixtures (app, db, etc.)
│   ├── test_ingestion.py    # Tests for ingestion.py
│   ├── test_extraction.py   # Tests for extraction.py
│   ├── test_enrichment.py   # Tests for enrichment.py
│   └── test_models.py       # Tests for models.py
├── scripts/
│   ├── ingest_data.py       # Manual Data Entry CLI
│   ├── migrate_db.py        # Database Migration Helper
│   └── debug/               # Debugging scripts
├── manage.py                # Main CLI Orchestrator
├── run.py                   # Web Server Entry Point
└── instance/
    └── violence.db          # SQLite Database
```

## Test Structure

### Test Organization

Tests mirror the application structure:
- `tests/test_ingestion.py` → `app/services/ingestion.py`
- `tests/test_extraction.py` → `app/services/extraction.py`
- `tests/test_enrichment.py` → `app/services/enrichment.py`
- `tests/test_models.py` → `app/models.py`

### Test Naming Conventions

- Test files: `test_<module_name>.py`
- Test classes: `Test<ClassName>` (e.g., `TestFetchFeed`)
- Test functions: `test_<functionality>` (e.g., `test_fetch_feed_basic`)

### Test Fixtures (`tests/conftest.py`)

Common fixtures available to all tests:
- `app`: Flask application instance with test configuration
- `client`: Test client for making HTTP requests
- `db_session`: Database session with automatic rollback
- `sample_feed_entry`: Mock RSS feed entry
- `sample_source_data`: Sample source data dictionary

### Writing Tests

#### Example Test Structure

```python
from unittest.mock import Mock, patch
import pytest
from app.services.ingestion import fetch_feed

class TestFetchFeed:
    """Tests for fetch_feed function."""
    
    @patch('app.services.ingestion.feedparser')
    def test_fetch_feed_basic(self, mock_feedparser):
        """Test basic feed fetching without parameters."""
        # Setup
        mock_entry = Mock()
        mock_entry.link = "https://example.com/article"
        mock_feed = Mock()
        mock_feed.entries = [mock_entry]
        mock_feedparser.parse.return_value = mock_feed
        
        # Execute
        result = fetch_feed()
        
        # Assert
        assert len(result) == 1
        assert result[0].link == "https://example.com/article"
```

#### Testing Patterns

1. **Mock External Dependencies**: Always mock external APIs, network calls, file I/O
   ```python
   @patch('app.services.ingestion.feedparser')
   @patch('app.services.ingestion.trafilatura')
   ```

2. **Test Database Operations**: Use in-memory SQLite for fast, isolated tests
   ```python
   def test_create_source(self, app, db_session):
       with app.app_context():
           source = Source(url="https://example.com", title="Test")
           db_session.add(source)
           db_session.commit()
           assert Source.query.count() == 1
   ```

3. **Test Error Handling**: Always test exception paths
   ```python
   def test_fetch_feed_network_error(self, mock_feedparser):
       mock_feedparser.parse.side_effect = Exception("Network error")
       with pytest.raises(Exception):
           fetch_feed()
   ```

4. **Test Edge Cases**: Empty inputs, None values, boundary conditions
   ```python
   def test_fetch_feed_empty_result(self, mock_feedparser):
       mock_feedparser.parse.return_value.entries = []
       result = fetch_feed()
       assert result == []
   ```

5. **Test Concurrent Operations**: Mock ThreadPoolExecutor and futures
   ```python
   @patch('app.services.ingestion.concurrent.futures.wait')
   @patch('app.services.ingestion.concurrent.futures.ThreadPoolExecutor')
   ```

## Data Pipeline

The data ingestion follows a 3-stage pipeline orchestrated by `manage.py`:

1.  **Ingestion (`app/services/ingestion.py`)**:
    - Reads Google News RSS.
    - Creates `Source` records with `status='pending'`.
    - **Tests**: `tests/test_ingestion.py`
    - **Coverage**: All functions must have tests (fetch_feed, fetch_all_feeds, resolve_url, process_source_task, run_ingestion)

2.  **Extraction (`app/services/extraction.py`)**:
    - Resolves `news.google.com` URLs to original publisher URLs.
    - Downloads HTML/Text using `trafilatura`.
    - Checks for keywords (stored in `Keyword` table).
    - Creates `ExtractedEvent` if matches found.
    - **Tests**: `tests/test_extraction.py` (to be created)
    - **Coverage**: Keyword matching, LLM extraction, event creation

3.  **Enrichment (`app/services/enrichment.py`)**:
    - Deduplicates events.
    - Links extractions to `Incident` records.
    - **Tests**: `tests/test_enrichment.py` (to be created)
    - **Coverage**: Deduplication logic, incident linking

## Running Tests

### Run All Tests
```bash
uv run pytest
```

### Run Specific Test File
```bash
uv run pytest tests/test_ingestion.py
```

### Run Specific Test
```bash
uv run pytest tests/test_ingestion.py::TestFetchFeed::test_fetch_feed_basic
```

### Run with Coverage
```bash
uv run pytest --cov=app --cov-report=html
```

### Run Tests in Verbose Mode
```bash
uv run pytest -v
```

### Run Tests with Output
```bash
uv run pytest -s
```

## Test Requirements by Module

### `app/services/ingestion.py`
✅ **COMPLETE** - All functions tested:
- `fetch_feed`: Basic fetching, query params, date filters, empty results
- `fetch_all_feeds`: Generator behavior, date ranges, query parameters
- `resolve_url`: Google News URL resolution, error handling
- `process_source_task`: Source processing, content download, error handling
- `run_ingestion`: Full pipeline, query expansion, geo expansion, duplicate handling

### `app/services/extraction.py`
⏳ **TODO** - Tests needed for:
- `check_keywords_fast`: Keyword matching logic
- `extract_with_llm`: LLM-based extraction
- `run_extraction`: Full extraction pipeline
- Error handling for API failures
- Edge cases (empty content, malformed data)

### `app/services/enrichment.py`
⏳ **TODO** - Tests needed for:
- Deduplication algorithms
- Incident linking logic
- Confidence score calculations
- Data validation

### `app/models.py`
⏳ **TODO** - Tests needed for:
- Model creation and validation
- Relationships (Source → ExtractedEvent → Incident)
- Database constraints
- Model methods (if any)

## Key Commands
*   **Run Web Server**: `uv run run.py` (http://127.0.0.1:5000)
*   **Run Full Pipeline**: `uv run manage.py run-all`
*   **Run Full Pipeline (Force Update)**: `uv run manage.py run-all --force`
*   **Run Tests**: `uv run pytest`
*   **Run Tests with Coverage**: `uv run pytest --cov=app`
*   **Manual Data Entry**: `uv run scripts/ingest_data.py --help`

## Database Models (`app/models.py`)
*   `Source`: Raw URL entry. Has `url`, `resolved_url`, `content`, `status`.
*   `ExtractedEvent`: A potential incident found in a source. Has `confidence_score`, `summary`.
*   `Incident`: A canonical, confirmed event (e.g. "Murder in Copacabana"). Linked to multiple extractions.
*   `Keyword`: Terms used to filter news (e.g. "baleado", "tiroteio").

## Best Practices

### When Adding New Features

1. **Start with Tests**: Write tests that describe the desired behavior
2. **Mock External Dependencies**: Never make real network calls in tests
3. **Use Fixtures**: Leverage `conftest.py` fixtures for common setup
4. **Test Edge Cases**: Don't just test the happy path
5. **Keep Tests Fast**: Use in-memory databases, mock slow operations
6. **One Assertion Per Test**: Or at least, one concept per test
7. **Descriptive Names**: Test names should read like documentation

### When Fixing Bugs

1. **Reproduce in Test**: Write a failing test that reproduces the bug
2. **Fix the Code**: Make the test pass
3. **Verify**: Ensure no other tests break
4. **Document**: Add comments explaining the fix if needed

### Code Quality

- **No Warnings**: All known warnings are suppressed in `pyproject.toml`
- **Clean Output**: Tests should run without warnings or errors
- **Fast Execution**: Test suite should complete in < 5 seconds
- **Isolated**: Tests don't depend on external services or filesystem state

## Common Pitfalls to Avoid

1. **Don't test implementation details**: Test behavior, not how it's implemented
2. **Don't skip mocking**: Real network calls make tests slow and flaky
3. **Don't share state**: Each test should be independent
4. **Don't ignore edge cases**: Empty inputs, None values, large inputs
5. **Don't write tests after code**: Write tests first (TBD principle)

## Next Steps

When working on this codebase:

1. **Check existing tests**: Always look at existing test patterns first
2. **Follow the structure**: Mirror the application structure in tests
3. **Run tests frequently**: Run tests after every change
4. **Keep tests green**: Never commit code that breaks existing tests
5. **Add tests for new code**: No exceptions - all new code needs tests

---

**Remember**: Tests are not a burden - they are your safety net. They catch bugs early, document behavior, and give you confidence to refactor. Write tests first, and the code will follow.
