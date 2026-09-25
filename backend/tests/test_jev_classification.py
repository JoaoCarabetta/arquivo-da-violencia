"""Unit tests for the Jev Decisions adapter on headline classification."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest

from app.services.classification import (
    CLASSIFICATION_SYSTEM_PROMPT,
    classification_from_jev_answers,
    classify_headline,
)
from app.services.jev_decisions import (
    DECISIONS_URL,
    JevDecisionsError,
    is_jev_model,
    normalize_jev_model,
    submit_decisions,
)


def test_is_jev_model_accepts_official_slugs():
    assert is_jev_model("typesafe/jev-1.13")
    assert is_jev_model("~typesafe/jev-latest")
    assert is_jev_model("jev-1.13")
    assert is_jev_model("jev-latest")
    assert not is_jev_model("openai/gpt-oss-120b")
    assert not is_jev_model("google/gemini-2.5-flash-lite")
    assert not is_jev_model(None)
    assert not is_jev_model("")


def test_normalize_jev_model_maps_bare_ids():
    assert normalize_jev_model("typesafe/jev-1.13") == "typesafe/jev-1.13"
    assert normalize_jev_model("~typesafe/jev-latest") == "~typesafe/jev-latest"
    assert normalize_jev_model("jev-1.13") == "typesafe/jev-1.13"
    assert normalize_jev_model("jev-latest") == "~typesafe/jev-latest"


def test_classification_from_jev_answers_thresholds_noul():
    result = classification_from_jev_answers(
        {
            "is_violent_death": {"type": "noul", "noul": 0.96},
            "is_single_incident": {"type": "noul", "noul": 0.91},
            "content_class_hint": {
                "type": "choice",
                "choice": "incident",
                "confidence": 0.8,
                "probabilities": {"incident": 0.9},
            },
        }
    )
    assert result.is_violent_death is True
    assert result.is_single_incident is True
    assert result.confidence == "alta"
    assert result.content_class_hint == "incident"
    assert "0.960" in result.reasoning


def test_classification_from_jev_answers_false_below_threshold():
    result = classification_from_jev_answers(
        {
            "is_violent_death": {"type": "noul", "noul": 0.12},
            "is_single_incident": {"type": "noul", "noul": 0.4},
            "content_class_hint": {"type": "choice", "choice": "foreign"},
        }
    )
    assert result.is_violent_death is False
    assert result.is_single_incident is False
    assert result.confidence == "alta"
    assert result.content_class_hint == "foreign"


def test_classification_from_jev_answers_rejects_missing_noul():
    with pytest.raises(ValueError, match="missing numeric noul"):
        classification_from_jev_answers(
            {
                "is_violent_death": {"type": "noul"},
                "is_single_incident": {"type": "noul", "noul": 0.9},
            }
        )


def _jev_answers(noul: float = 0.96, incident: float = 0.91, hint: str = "incident"):
    return {
        "is_violent_death": {"type": "noul", "noul": noul},
        "is_single_incident": {"type": "noul", "noul": incident},
        "content_class_hint": {"type": "choice", "choice": hint, "confidence": 0.8},
    }


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self.status_code = status_code
        self._payload = payload
        self.text = "ok" if status_code < 400 else str(payload)

    @property
    def is_success(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


def test_submit_decisions_posts_official_shape(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, timeout=None):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return _FakeResponse(
                {
                    "answers": _jev_answers(),
                    "usage": {"input_tokens": 10, "output_tokens": 2, "cost": 0.0001},
                    "model": "typesafe/jev-1.13-20260917",
                }
            )

    monkeypatch.setattr("app.services.jev_decisions.httpx.Client", FakeClient)

    data = submit_decisions(
        model="jev-1.13",
        state={"headline": "Homem é morto a tiros"},
        questions={"is_violent_death": {"type": "noul", "instructions": "yes?"}},
        api_key="sk-test",
        timeout=30.0,
    )

    assert captured["url"] == DECISIONS_URL
    assert captured["json"]["model"] == "typesafe/jev-1.13"
    assert captured["json"]["state"]["headline"] == "Homem é morto a tiros"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["headers"]["Content-Type"] == "application/json"
    assert data["answers"]["is_violent_death"]["noul"] == 0.96


def test_submit_decisions_marks_429_retryable(monkeypatch):
    class FakeClient:
        def __init__(self, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json=None, headers=None):
            return _FakeResponse("rate limited", status_code=429)

    monkeypatch.setattr("app.services.jev_decisions.httpx.Client", FakeClient)

    with pytest.raises(JevDecisionsError) as exc:
        submit_decisions(
            model="typesafe/jev-1.13",
            state="x",
            questions={},
            api_key="sk-test",
        )
    assert exc.value.retryable is True
    assert exc.value.status_code == 429


def test_classify_headline_jev_uses_decisions_not_chat(monkeypatch):
    captured = {}

    def fake_submit(**kwargs):
        captured.update(kwargs)
        return {"answers": _jev_answers()}

    monkeypatch.setattr(
        "app.services.classification.get_settings",
        lambda: SimpleNamespace(
            openrouter_api_key="sk-test",
            selection_model="typesafe/jev-1.13",
        ),
    )
    monkeypatch.setattr("app.services.classification.submit_decisions", fake_submit)
    instructor_client = MagicMock()
    monkeypatch.setattr(
        "app.services.classification.get_classification_client",
        lambda **kwargs: instructor_client,
    )

    result = classify_headline(
        "Homem é morto a tiros em operação policial",
        model="typesafe/jev-1.13",
    )

    instructor_client.create.assert_not_called()
    assert captured["model"] == "typesafe/jev-1.13"
    assert captured["api_key"] == "sk-test"
    assert captured["state"]["headline"] == "Homem é morto a tiros em operação policial"
    assert captured["state"]["policy"] == CLASSIFICATION_SYSTEM_PROMPT
    assert captured["questions"]["is_violent_death"]["type"] == "noul"
    assert captured["questions"]["is_single_incident"]["type"] == "noul"
    assert captured["questions"]["content_class_hint"]["type"] == "choice"
    assert result.is_violent_death is True
    assert result.is_single_incident is True
    assert result.content_class_hint == "incident"


def test_classify_headline_jev_keeps_heuristics(monkeypatch):
    monkeypatch.setattr(
        "app.services.classification.get_settings",
        lambda: SimpleNamespace(
            openrouter_api_key="sk-test",
            selection_model="typesafe/jev-1.13",
        ),
    )
    monkeypatch.setattr(
        "app.services.classification.submit_decisions",
        lambda **kwargs: {"answers": _jev_answers(noul=0.99)},
    )

    result = classify_headline(
        "Jovem baleado na cabeça durante assalto a padaria tem quadro estável no hospital.",
        model="~typesafe/jev-latest",
    )
    assert result.is_violent_death is False


def test_classify_headline_non_jev_still_uses_instructor(monkeypatch):
    instructor_client = MagicMock()
    instructor_client.create.return_value = classification_from_jev_answers(_jev_answers())
    monkeypatch.setattr(
        "app.services.classification.get_classification_client",
        lambda **kwargs: instructor_client,
    )
    monkeypatch.setattr(
        "app.services.classification.get_settings",
        lambda: SimpleNamespace(
            openrouter_api_key="sk-test",
            selection_model="openai/gpt-oss-120b",
        ),
    )

    result = classify_headline("Homem é morto a tiros", model="openai/gpt-oss-120b")

    instructor_client.create.assert_called_once()
    messages = instructor_client.create.call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert "Homem é morto a tiros" in messages[1]["content"]
    assert result.is_violent_death is True


def test_eval_variant_selects_jev_slug():
    from eval.variants import load_classification_variant

    variant = load_classification_variant("bench-jev-113")
    assert variant.selection_model == "typesafe/jev-1.13"
    assert variant.system_prompt is None


def test_submit_decisions_retries_transport_error(monkeypatch):
    class FakeClient:
        def __init__(self, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json=None, headers=None):
            raise httpx.ConnectError("boom")

    monkeypatch.setattr("app.services.jev_decisions.httpx.Client", FakeClient)

    with pytest.raises(JevDecisionsError) as exc:
        submit_decisions(
            model="typesafe/jev-1.13",
            state="x",
            questions={},
            api_key="sk-test",
        )
    assert exc.value.retryable is True
