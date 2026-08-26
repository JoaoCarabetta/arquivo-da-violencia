"""Tests for post-download content heuristics (AQV-32)."""

from pathlib import Path

from app.services.content_filters import apply_content_heuristics

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_heuristic_rejects_cvli_aggregate():
    headline = "CVLI: estado registra mortes violentas em 2025"
    content = (
        "O painel de indicadores registrou 4.241 mortes violentas em todo o estado "
        "durante o ano de 2025, segundo dados consolidados."
    )
    match = apply_content_heuristics(headline, content)
    assert match is not None
    assert match.hint == "aggregate_statistics"
    assert match.rule == "cvli_year_report"


def test_heuristic_rejects_large_national_total():
    headline = "Estudo revela número de vítimas no Brasil"
    content = (
        "A pesquisa nacional apontou 42.441 vítimas de homicídios violentos "
        "em levantamento divulgado nesta quarta-feira."
    )
    match = apply_content_heuristics(headline, content)
    assert match is not None
    assert match.hint == "aggregate_statistics"


def test_heuristic_rejects_foreign_earthquake():
    headline = "Terremoto deixa centenas de mortos"
    content = (
        "Um terremoto de magnitude 6,8 atingiu a Venezuela nesta terça-feira "
        "e deixou centenas de mortos em diversas cidades."
    )
    match = apply_content_heuristics(headline, content)
    assert match is not None
    assert match.hint == "foreign"
    assert match.rule == "foreign_earthquake"


def test_heuristic_rejects_suicide():
    headline = "Homem é encontrado morto em casa"
    content = (
        "A polícia investiga um caso de suicídio ocorrido na manhã desta segunda "
        "em um apartamento no centro da cidade."
    )
    match = apply_content_heuristics(headline, content)
    assert match is not None
    assert match.hint == "non_incident"


def test_heuristic_passes_single_incident():
    headline = "Homem é morto a tiros em operação policial no Rio"
    content = (
        "Um homem foi morto a tiros durante uma operação policial na Zona Norte "
        "do Rio de Janeiro na noite de sábado. A vítima ainda não foi identificada."
    )
    assert apply_content_heuristics(headline, content) is None


def test_heuristic_passes_chilean_homicide_not_earthquake():
    """Chilean homicide should not be rejected by earthquake regex (issue #129)."""
    headline = "Hombre asesinado en Santiago"
    content = (
        "Un hombre fue asesinado a balazos durante un operativo policial "
        "en Santiago de Chile. Las autoridades investigan el caso."
    )
    # Should not match earthquake pattern since Chile was removed from it
    assert apply_content_heuristics(headline, content) is None


def test_heuristic_still_rejects_venezuela_earthquake():
    """Venezuelan earthquake should still be rejected as foreign."""
    headline = "Terremoto deixa mortos"
    content = (
        "Um terremoto de magnitude 6,5 atingiu a Venezuela e deixou "
        "dezenas de mortos em várias cidades."
    )
    match = apply_content_heuristics(headline, content)
    assert match is not None
    assert match.hint == "foreign"
    assert match.rule == "foreign_earthquake"


def test_heuristic_rejects_google_language_picker():
    """Google language picker page should be rejected (issue #208)."""
    fixture_path = FIXTURES_DIR / "google_language_picker.txt"
    content = fixture_path.read_text(encoding="utf-8")
    headline = "Notícias"
    
    match = apply_content_heuristics(headline, content)
    assert match is not None, "Language picker content should be rejected"
    assert match.hint == "non_incident"
    assert match.rule == "google_language_picker"


def test_heuristic_rejects_google_consent_page():
    """Google consent/cookie page should be rejected (issue #208)."""
    fixture_path = FIXTURES_DIR / "google_consent_page.txt"
    content = fixture_path.read_text(encoding="utf-8")
    headline = ""
    
    match = apply_content_heuristics(headline, content)
    assert match is not None, "Consent page content should be rejected"
    assert match.hint == "non_incident"
    assert match.rule == "google_consent_page"


def test_heuristic_passes_real_article_with_language_name():
    """Real homicide article mentioning 'English' or language names should pass (issue #208)."""
    headline = "Homem é morto a tiros em operação no Rio"
    content = (
        "Um homem identificado como John English foi morto a tiros durante "
        "uma operação policial na favela do Alemão. A vítima tinha "
        "passagens pela polícia e era procurado por homicídio. "
        "O caso foi registrado na delegacia local e a perícia está no local."
    )
    
    # Article mentions "English" as a surname but should still pass
    match = apply_content_heuristics(headline, content)
    assert match is None, "Real article with language name should not be rejected"


def test_heuristic_passes_article_mentioning_portuguese():
    """Real article mentioning Portuguese language in context should pass (issue #208)."""
    headline = "Tradutor é assassinado em São Paulo"
    content = (
        "Um tradutor que trabalhava com textos em português e inglês "
        "foi assassinado a facadas em seu apartamento em São Paulo. "
        "A polícia investiga o crime que teria ocorrido durante a madrugada. "
        "Vizinhos relataram ter ouvido gritos por volta das 3h da manhã."
    )
    
    # Article mentions Portuguese but is clearly a homicide report
    match = apply_content_heuristics(headline, content)
    assert match is None, "Real article mentioning language should not be rejected"
