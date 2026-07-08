"""Unit tests for extraction post-LLM heuristics."""

from app.services.extraction_heuristics import (
    _norm,
    apply_extraction_heuristics,
    fix_same_day_relative_weekday,
    fix_weekday_paren_day,
    infer_fatal_victim_count,
    infer_method_from_text,
    infer_state_from_metadata,
    is_insufficient_classification_case,
    is_patrol_shootout_not_intervention,
    normalize_date_string,
    should_be_qualificado,
)
from app.services.extraction_schemas import (
    DateTime,
    DateVerification,
    HomicideDynamic,
    IdentifiableVictim,
    Location,
    Victims,
    ViolentDeathEvent,
)


def _date_verification(**kwargs) -> DateVerification:
    defaults = {
        "has_explicit_date": True,
        "date_source": "explicit",
        "year_explicitly_mentioned": True,
        "verification_reasoning": "test fixture",
    }
    defaults.update(kwargs)
    return DateVerification(**defaults)


def _event(**kwargs) -> ViolentDeathEvent:
    defaults = {
        "event_family": "homicidio",
        "event_subtype": "simples",
        "content_class": "incident",
        "location_info": Location(city="Salvador", state="BA"),
        "date_time": DateTime(
            date="2024-05-20",
            date_verification=_date_verification(),
        ),
        "victims": Victims(
            identifiable_victims=[IdentifiableVictim(name="Vítima")],
            number_of_identifiable_victims=1,
            number_of_victims=1,
        ),
        "homicide_dynamic": HomicideDynamic(
            title="HOMICÍDIO - TEST",
            method=None,
            chronological_description="desc",
        ),
    }
    defaults.update(kwargs)
    return ViolentDeathEvent(**defaults)


def test_infer_method_firearms():
    assert infer_method_from_text("vítima baleada com múltiplos disparos") == "Arma de fogo"


def test_qualificado_from_execution_and_shots():
    text = (
        "Homem executado a tiros. Múltiplos disparos à queima-roupa contra a vítima."
    )
    assert should_be_qualificado(text)


def test_hypothesis_executado_not_qualificado():
    text = (
        "Corpo com marcas de tiros. A principal hipótese é de que ele tenha sido "
        "executado em outro local."
    )
    assert not should_be_qualificado(text)


def test_fix_weekday_paren_day_prioritizes_day_number():
    content = "Crime ocorreu no início da noite de domingo (10) no bairro."
    fixed = fix_weekday_paren_day(
        content,
        {"published_at": "2025-03-11T12:00:00Z"},
        "2025-03-09",
    )
    assert fixed == "2025-03-10"


def test_fix_same_day_relative_weekday():
    content = "Corpo encontrado na manhã deste sábado em terreno baldio."
    fixed = fix_same_day_relative_weekday(
        content,
        {"published_at": "2025-04-05T13:15:00Z"},
        None,
    )
    assert fixed == "2025-04-05"


def test_infer_fatal_victim_count_excludes_wounded():
    source = (
        "Chacina deixou três pessoas mortas e uma ferida em um bar. "
        "A quarta pessoa atingida foi hospitalizada."
    )
    assert infer_fatal_victim_count(_norm(source)) == 3


def test_normalize_date_string_strips_time():
    assert normalize_date_string("2024-07-19T00:00:00") == "2024-07-19"


def test_apply_downgrades_false_qualificado():
    event = _event(event_subtype="qualificado")
    content = (
        "Jovem foi atingido por vários disparos de arma de fogo em via pública. "
        "Polícia investiga autoria."
    )
    result = apply_extraction_heuristics(event, content, None)
    assert result.event_subtype == "simples"


def test_apply_fixes_espancamento_over_contundente():
    event = _event(
        event_subtype="latrocinio",
        homicide_dynamic=HomicideDynamic(
            title="LATROCÍNIO",
            method="Objeto contundente",
            chronological_description="desc",
        ),
    )
    content = (
        "Aposentado encontrado amarrado e com sinais de espancamento dentro de casa."
    )
    result = apply_extraction_heuristics(event, content, None)
    assert result.homicide_dynamic.method == "Espancamento"


def test_patrol_shootout_not_intervention():
    text = (
        "Patrulhamento da PM quando foram recebidas a tiros por criminosos. "
        "Suspeito neutralizado."
    )
    assert is_patrol_shootout_not_intervention(text)


def test_apply_downgrades_intervention_on_patrol_shootout():
    event = _event(event_subtype="intervencao_policial")
    content = (
        "Confronto entre policiais militares da ROTA e suspeitos. "
        "Os indivíduos reagiram atirando durante patrulhamento tático."
    )
    result = apply_extraction_heuristics(event, content, {"headline": "Troca de tiros com ROTA"})
    assert result.event_subtype == "simples"


def test_apply_upgrades_qualificado_and_method():
    event = _event(event_subtype="simples")
    content = (
        "O carona efetuou múltiplos disparos à queima-roupa. Homem executado a tiros."
    )
    result = apply_extraction_heuristics(
        event, content, {"headline": "Homem é executado a tiros em bar"}
    )
    assert result.event_subtype == "qualificado"
    assert result.homicide_dynamic.method == "Arma de fogo"


def test_apply_acidente_sets_content_class():
    event = _event(
        event_family="acidente_fatal",
        event_subtype="transito_culposo",
        content_class="incident",
    )
    result = apply_extraction_heuristics(event, "Atropelamento fatal na BR-101", None)
    assert result.content_class == "accident_disaster"


def test_unspecified_method_when_undetermined():
    event = _event()
    content = (
        "Corpo encontrado boiando. A perícia inicial não conseguiu determinar "
        "o objeto usado no crime."
    )
    result = apply_extraction_heuristics(
        event, content, {"headline": "Homem encontrado morto em igarapé"}
    )
    assert result.homicide_dynamic.method == "Não especificado"


def test_unspecified_overrides_llm_contundente_guess():
    event = _event(
        homicide_dynamic=HomicideDynamic(
            title="HOMICÍDIO",
            method="Objeto contundente",
            chronological_description="desc",
        ),
    )
    content = (
        "Corpo com ferimento profundo na cabeça. A perícia inicial não conseguiu "
        "determinar o objeto usado no crime."
    )
    result = apply_extraction_heuristics(event, content, None)
    assert result.homicide_dynamic.method == "Não especificado"


def test_scant_campo_grande_case():
    content = (
        "Um corpo foi achado em um terreno em Campo Grande. A polícia foi chamada. "
        "Não há detalhes sobre a identidade da vítima ou a causa da morte. "
        "Nenhuma outra informação foi divulgada."
    )
    meta = {
        "headline": "Corpo encontrado em terreno em Campo Grande",
        "publisher": "Campo Grande News",
        "url": "https://www.campograndenews.com.br/cidades/capital/corpo-encontrado-terreno",
    }
    assert is_insufficient_classification_case(_source_norm(content, meta))
    assert infer_state_from_metadata("Campo Grande", meta) == "MS"
    event = _event(
        location_info=Location(city="Campo Grande", state=None),
        homicide_dynamic=HomicideDynamic(
            title="HOMICÍDIO",
            method=None,
            chronological_description="desc",
        ),
    )
    result = apply_extraction_heuristics(event, content, meta)
    assert result.event_family == "nao_classificado"
    assert result.event_subtype == "outro"
    assert result.location_info.state == "MS"


def _source_norm(content: str, metadata: dict) -> str:
    from app.services.extraction_heuristics import _source_text

    return _source_text(content, metadata)
