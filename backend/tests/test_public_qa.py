"""Public Q&A: stats/series, event filters, ask, CORS, discovery."""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.models.unique_event import UniqueEvent
from app.services.public_qa import classify_question_heuristic, series_direction
from app.taxonomy import parse_legacy_homicide_type
from tests.test_public_stats import create_fake_event


def _event(**kwargs) -> UniqueEvent:
    return create_fake_event(**kwargs)


@pytest.mark.parametrize(
    ("current", "previous", "expected"),
    [
        (2, 1, "insufficient"),
        (10, 6, "up"),
        (6, 10, "down"),
        (20, 20, "flat"),
        (10, 0, "up"),
        (0, 0, "insufficient"),
    ],
)
def test_series_direction(current, previous, expected):
    direction, _ = series_direction(current, previous)
    assert direction == expected


def test_classify_umari_is_place():
    plan = classify_question_heuristic("Rua Umari 28, Rio de Janeiro")
    assert plan.intent == "place"
    assert "Umari" in (plan.place_query or "")
    near = classify_question_heuristic("Crimes near Rua Umari 28, Rio")
    assert near.intent == "place"


def test_classify_feminicidio_ceara_is_trend():
    plan = classify_question_heuristic("O feminicídio está subindo no Ceará?")
    assert plan.intent == "trend"
    assert plan.state == "CE"
    assert plan.subtype == "feminicidio"


@pytest.mark.asyncio
async def test_stats_series_feminicidio_ce(app, async_session, client: AsyncClient):
    now = datetime.utcnow()
    family, subtype = parse_legacy_homicide_type("Feminicídio")
    async_session.add_all(
        [
            _event(
                title="Feminicídio atual CE",
                event_date=now - timedelta(days=10),
                state="CE",
                city="Fortaleza",
                homicide_type="Feminicídio",
                event_family=family,
                event_subtype=subtype,
                victim_count=1,
                latitude=Decimal("-3.7172"),
                longitude=Decimal("-38.5433"),
            )
            for _ in range(6)
        ]
        + [
            _event(
                title="Feminicídio anterior CE",
                event_date=now - timedelta(days=400),
                state="CE",
                city="Fortaleza",
                homicide_type="Feminicídio",
                event_family=family,
                event_subtype=subtype,
                victim_count=1,
                latitude=Decimal("-3.7172"),
                longitude=Decimal("-38.5433"),
            )
            for _ in range(3)
        ]
        + [
            _event(
                title="Homicídio CE",
                event_date=now - timedelta(days=5),
                state="CE",
                city="Fortaleza",
                homicide_type="Homicídio",
                victim_count=1,
            ),
            _event(
                title="Feminicídio RJ",
                event_date=now - timedelta(days=5),
                state="RJ",
                city="Rio de Janeiro",
                homicide_type="Feminicídio",
                event_family=family,
                event_subtype=subtype,
                victim_count=1,
            ),
        ]
    )
    await async_session.commit()

    response = await client.get(
        "/api/public/stats/series",
        params={"state": "CE", "subtype": "feminicidio", "interval": "week", "days": 365},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "CE"
    assert data["subtype"] == "feminicidio"
    assert data["current"]["event_count"] == 6
    assert data["previous"]["event_count"] == 3
    assert data["direction"] == "up"
    assert data["source"] == "Arquivo da Violência"
    assert "metodologia" in data["methodology_url"]
    assert data["methodology"]["coverage_bias"] is True
    assert "SIM/FBSP" in data["methodology"]["not_official"]
    assert data["series"]


@pytest.mark.asyncio
async def test_events_accepts_city_dates_and_subtype(app, async_session, client: AsyncClient):
    now = datetime.utcnow()
    family, subtype = parse_legacy_homicide_type("Feminicídio")
    async_session.add_all(
        [
            _event(
                title="Alvo",
                event_date=now - timedelta(days=3),
                state="CE",
                city="Fortaleza",
                homicide_type="Feminicídio",
                event_family=family,
                event_subtype=subtype,
                location_precision="city_center",
            ),
            _event(
                title="Outra cidade",
                event_date=now - timedelta(days=3),
                state="CE",
                city="Caucaia",
                homicide_type="Feminicídio",
                event_family=family,
                event_subtype=subtype,
            ),
            _event(
                title="Fora da janela",
                event_date=now - timedelta(days=40),
                state="CE",
                city="Fortaleza",
                homicide_type="Feminicídio",
                event_family=family,
                event_subtype=subtype,
            ),
        ]
    )
    await async_session.commit()

    start = (now - timedelta(days=7)).date().isoformat()
    end = now.date().isoformat()
    response = await client.get(
        "/api/public/events",
        params={
            "city": "fortaleza",
            "subtype": "feminicidio",
            "date_from": start,
            "date_to": end,
        },
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "Alvo"
    assert items[0]["location_precision"] == "city_center"

    alias = await client.get(
        "/api/public/events",
        params={"homicide_type": "feminicidio", "city": "Fortaleza"},
    )
    assert alias.status_code == 200
    assert alias.json()["total"] >= 1


@pytest.mark.asyncio
async def test_nearby_surfaces_location_precision(app, async_session, client: AsyncClient):
    now = datetime.utcnow()
    async_session.add(
        _event(
            title="Perto",
            event_date=now - timedelta(days=2),
            state="RJ",
            city="Rio de Janeiro",
            latitude=Decimal("-22.9068"),
            longitude=Decimal("-43.1729"),
            location_precision="city_center",
        )
    )
    await async_session.commit()

    response = await client.get(
        "/api/public/nearby",
        params={"lat": -22.9068, "lng": -43.1729, "radius_km": 5, "days": 30},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["events"][0]["location_precision"] == "city_center"
    assert data["summary"]["by_precision"]
    assert data["summary"]["precision_note"]


@pytest.mark.asyncio
async def test_ask_feminicidio_ceara(app, async_session, client: AsyncClient):
    now = datetime.utcnow()
    family, subtype = parse_legacy_homicide_type("Feminicídio")
    async_session.add_all(
        [
            _event(
                title=f"Fem CE {i}",
                event_date=now - timedelta(days=8 + i),
                state="CE",
                city="Fortaleza",
                homicide_type="Feminicídio",
                event_family=family,
                event_subtype=subtype,
                victim_count=1,
            )
            for i in range(6)
        ]
        + [
            _event(
                title=f"Fem CE old {i}",
                event_date=now - timedelta(days=400 + i),
                state="CE",
                city="Fortaleza",
                homicide_type="Feminicídio",
                event_family=family,
                event_subtype=subtype,
                victim_count=1,
            )
            for i in range(3)
        ]
    )
    await async_session.commit()

    response = await client.post(
        "/api/public/ask",
        json={"question": "O feminicídio está subindo no Ceará?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["query"]["intent"] == "trend"
    assert data["query"]["state"] == "CE"
    assert data["query"]["subtype"] == "feminicidio"
    assert data["data"]["direction"] in {"up", "down", "flat", "insufficient"}
    assert data["data"]["direction"] == "up"
    assert "notícias" in data["answer"].lower() or "arquivo" in data["answer"].lower()
    assert any("oficial" in c.lower() or "SIM" in c for c in data["caveats"])
    assert data["source"] == "Arquivo da Violência"
    assert data["methodology_url"].endswith("/metodologia")
    assert any("metodologia" in c["url"] for c in data["citations"])


@pytest.mark.asyncio
async def test_ask_rua_umari(app, async_session, client: AsyncClient):
    now = datetime.utcnow()
    async_session.add(
        _event(
            title="Homicídio na Tijuca",
            event_date=now - timedelta(days=4),
            state="RJ",
            city="Rio de Janeiro",
            neighborhood="Tijuca",
            latitude=Decimal("-22.9068"),
            longitude=Decimal("-43.1729"),
            location_precision="neighborhood_center",
        )
    )
    await async_session.commit()

    fake_geo = {
        "latitude": -22.9068,
        "longitude": -43.1729,
        "label": "Rua Umari, Tijuca, Rio de Janeiro - RJ, Brasil",
        "source": "test",
        "zoom": 16,
    }
    with patch(
        "app.services.geocoding.geocode_user_query",
        new=AsyncMock(return_value=fake_geo),
    ):
        response = await client.post(
            "/api/public/ask",
            json={"question": "Rua Umari 28, Rio de Janeiro"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["query"]["intent"] == "place"
    assert "RJ" in data["data"]["geocode"]["label"] or "Rio" in data["data"]["geocode"]["label"]
    assert data["data"]["summary"]["total"] >= 1
    assert data["data"]["events"][0]["location_precision"]
    assert any("rua" in c.lower() or "bairro" in c.lower() for c in data["caveats"])
    assert any("/eventos/" in c["url"] for c in data["citations"])
    assert data["map"]["lat"] == pytest.approx(-22.9068)


@pytest.mark.asyncio
async def test_public_cors_allows_any_origin(client: AsyncClient):
    response = await client.options(
        "/api/public/stats/series",
        headers={
            "Origin": "https://claude.ai",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 204
    assert response.headers.get("access-control-allow-origin") == "*"

    get_resp = await client.get(
        "/api/public/stats",
        headers={"Origin": "https://example.com"},
    )
    assert get_resp.status_code == 200
    assert get_resp.headers.get("access-control-allow-origin") == "*"


@pytest.mark.asyncio
async def test_admin_cors_is_not_wildcard(client: AsyncClient):
    response = await client.get(
        "/api/pipeline/status",
        headers={"Origin": "https://evil.example"},
    )
    assert response.headers.get("access-control-allow-origin") != "*"


@pytest.mark.asyncio
async def test_llms_txt_and_openapi(client: AsyncClient):
    llms = await client.get("/llms.txt")
    assert llms.status_code == 200
    text = llms.text
    assert "/api/openapi.json" in text
    assert "feminicidio" in text
    assert "Rua Umari" in text

    spec = await client.get("/api/openapi.json")
    assert spec.status_code == 200
    body = spec.json()
    assert "/api/public/ask" in body["paths"]
    assert "/api/public/stats/series" in body["paths"]
    assert "SIM/FBSP" in body["info"]["description"]
