"""Tests for post-download content heuristics (AQV-32)."""

from app.services.content_filters import apply_content_heuristics


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
