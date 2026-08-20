"""Test that extraction module can be imported without syntax errors."""


def test_extraction_module_imports():
    """Module must parse and import successfully."""
    import app.services.extraction
    
    # Verify the prompt is properly set
    assert isinstance(app.services.extraction.EXTRACTION_SYSTEM_PROMPT, str)
    assert len(app.services.extraction.EXTRACTION_SYSTEM_PROMPT) > 0
    assert "PRINCÍPIOS FUNDAMENTAIS" in app.services.extraction.EXTRACTION_SYSTEM_PROMPT


def test_extraction_prompt_equals_pt_default():
    """Default prompt should be the Portuguese version."""
    from app.services.extraction import (
        EXTRACTION_SYSTEM_PROMPT,
        EXTRACTION_SYSTEM_PROMPT_PT,
    )
    
    assert EXTRACTION_SYSTEM_PROMPT == EXTRACTION_SYSTEM_PROMPT_PT
