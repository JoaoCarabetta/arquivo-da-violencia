"""Unit tests for near-dup pair_signal hardening (named↔anonymous / MO overlap)."""

from app.services.dedup_scan import _victim_name_keys, pair_signal


def test_victim_keys_ignore_narrative_summary():
    keys = _victim_name_keys(
        {
            "victims_summary": (
                "Uma mulher trans de 45 anos foi assassinada com aproximadamente "
                "25 golpes de faca. O suspeito, homem de 21 anos, tentou incendiar o corpo."
            ),
            "merged_data": None,
        }
    )
    assert keys == set()


def test_victim_keys_from_named_summary_and_merged():
    keys = _victim_name_keys(
        {
            "victims_summary": "Wal, mulher trans de 45 anos, foi morta por Kauã Bryan",
            "merged_data": {
                "victims": {
                    "identifiable_victims": [
                        {"name": "Wal (identificada apenas como)", "age": 45}
                    ]
                }
            },
        }
    )
    assert any("wal" in k for k in keys)


def test_pair_signal_contagem_named_vs_anonymous_mo():
    named = {
        "id": 9780,
        "title": "FEMINICÍDIO - RESIDÊNCIA DA VÍTIMA CONTAGEM - 04/07/2026",
        "city": "Contagem",
        "event_date": "2026-07-04",
        "neighborhood": "Carajás",
        "victims_summary": "Wal, mulher trans de 45 anos, foi morta com ao menos 25 facadas.",
        "chronological_description": (
            "No dia 4 de julho de 2026, no bairro Carajás, Contagem/MG, a vítima Wal "
            "foi morta com cerca de 25 facadas; o autor tentou incendiar o corpo."
        ),
        "merged_data": {
            "victims": {"identifiable_victims": [{"name": "Wal", "age": 45}]}
        },
    }
    anonymous = {
        "id": 9788,
        "title": "Homicídio de mulher trans com 25 facadas e tentativa de incêndio em Contagem",
        "city": "Contagem",
        "event_date": "2026-07-04",
        "neighborhood": "Carajás",
        "victims_summary": (
            "Uma mulher trans de 45 anos foi assassinada com aproximadamente 25 golpes "
            "de faca. O suspeito tentou incendiar o corpo."
        ),
        "chronological_description": (
            "No dia 04/07/2026, em kitnet no bairro Carajás, Contagem/MG, o suspeito "
            "desferiu aproximadamente 25 golpes de faca e tentou incendiar o corpo."
        ),
        "merged_data": {"victims": {"identifiable_victims": [{"name": None, "age": 45}]}},
    }
    hit = pair_signal(named, anonymous)
    assert hit is not None
    assert hit[1] in {"mo_context", "title_soft_mo", "description_fuzzy", "victim_name"}


def test_pair_signal_alhandra_name_conflict_same_mo():
    a = {
        "id": 9945,
        "title": "Homicídio Simples - Residência em Alhandra - 07/07/2026",
        "city": "Alhandra",
        "event_date": "2026-07-07",
        "victims_summary": "Leandro Barros Maciel, 36 anos, morto com mais de 30 disparos.",
        "chronological_description": (
            "Cinco indivíduos mascarados e armados invadiram a residência, retiraram a "
            "vítima na presença da esposa e filho e efetuaram mais de 30 disparos na cabeça."
        ),
        "merged_data": {
            "victims": {
                "identifiable_victims": [{"name": "Leandro Barros Maciel", "age": 36}]
            }
        },
    }
    b = {
        "id": 9946,
        "title": "HOMICÍDIO QUALIFICADO - RESIDÊNCIA ZONA RURAL ALHANDRA - 07/07/2026",
        "city": "Alhandra",
        "event_date": "2026-07-07",
        "victims_summary": "Jailson, 36 anos, morto com mais de 30 tiros.",
        "chronological_description": (
            "Cinco suspeitos mascarados chegaram a pé, retiraram Jailson de casa com "
            "esposa e filho presentes e dispararam mais de 30 tiros no rosto e cabeça."
        ),
        "merged_data": {
            "victims": {"identifiable_victims": [{"name": "Jailson", "age": 36}]}
        },
    }
    hit = pair_signal(a, b)
    assert hit is not None
    assert hit[1] in {"mo_context", "title_soft_mo", "description_fuzzy"}


def test_pair_signal_keeps_distinct_jacarei_incidents_separate():
    a = {
        "id": 9836,
        "title": "Homicídio doloso após discussão de trânsito - Jardim das Indústrias",
        "city": "Jacareí",
        "event_date": "2026-07-05",
        "neighborhood": "Jardim das Indústrias",
        "victims_summary": "Weverton Innocente, 45 anos, motociclista.",
        "chronological_description": (
            "Após discussão de trânsito, Weverton Innocente foi morto no Jardim das Indústrias."
        ),
        "merged_data": {
            "victims": {
                "identifiable_victims": [{"name": "Weverton Innocente", "age": 45}]
            }
        },
    }
    b = {
        "id": 9837,
        "title": "Homicídio em residência no Parque dos Príncipes em Jacareí",
        "city": "Jacareí",
        "event_date": "2026-07-05",
        "neighborhood": "Parque dos Príncipes",
        "victims_summary": "Gilberto Messias de Souza, 54 anos.",
        "chronological_description": (
            "Gilberto Messias de Souza encontrado sem vida com ferimentos no pescoço "
            "em residência no Parque dos Príncipes."
        ),
        "merged_data": {
            "victims": {
                "identifiable_victims": [{"name": "Gilberto Messias de Souza", "age": 54}]
            }
        },
    }
    assert pair_signal(a, b) is None
