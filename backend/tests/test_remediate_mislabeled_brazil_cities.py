"""Tests for mislabeled Brasil UniqueEvent remediator (issue #234)."""

from datetime import datetime
from unittest.mock import patch

import pytest

from app.models.unique_event import UniqueEvent
from app.routers.public import include_in_unfiltered_brazil_city_ranking
from app.services.maintenance import (
    infer_country_from_mislabeled_geography,
    remediate_mislabeled_brazil_cities,
)


class _TestSessionMaker:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _make_event(
    *,
    event_id: int | None = None,
    city: str,
    state: str | None,
    country: str = "Brasil",
    title: str | None = None,
) -> UniqueEvent:
    kwargs = dict(
        title=title or f"Event in {city}",
        event_date=datetime(2026, 8, 1),
        country=country,
        state=state,
        city=city,
        event_family="homicidio",
        event_subtype="simples",
        content_class="incident",
        homicide_type="Homicídio simples",
        victim_count=1,
        source_count=1,
    )
    if event_id is not None:
        kwargs["id"] = event_id
    return UniqueEvent(**kwargs)


def test_infer_country_from_known_cities_and_states():
    assert infer_country_from_mislabeled_geography("Tumbler Ridge", "Colúmbia Britânica") == "CA"
    assert infer_country_from_mislabeled_geography("Joanesburgo", None) == "ZA"
    assert infer_country_from_mislabeled_geography("Paramaribo", "") == "SR"
    assert infer_country_from_mislabeled_geography("Homs", "Síria") == "SY"
    assert infer_country_from_mislabeled_geography("São Paulo", "SP") is None


@pytest.mark.asyncio
async def test_remediator_relabels_known_pollution_and_skips_real_br(async_session):
    tumbler = _make_event(
        event_id=8240, city="Tumbler Ridge", state="Colúmbia Britânica"
    )
    tumbler_dup = _make_event(
        event_id=8258, city="Tumbler Ridge", state="BC"
    )
    joanesburgo = _make_event(event_id=17, city="Joanesburgo", state=None)
    paramaribo = _make_event(event_id=1061, city="Paramaribo", state="")
    homs = _make_event(event_id=837, city="Homs", state="Síria")
    salvador = _make_event(city="Salvador", state="BA", country="BR")
    sao_paulo = _make_event(city="São Paulo", state="SP", country="Brasil")

    async_session.add_all(
        [tumbler, tumbler_dup, joanesburgo, paramaribo, homs, salvador, sao_paulo]
    )
    await async_session.commit()

    with patch(
        "app.services.maintenance.async_session_maker",
        _TestSessionMaker(async_session),
    ):
        dry = await remediate_mislabeled_brazil_cities(dry_run=True)

    await async_session.refresh(tumbler)
    assert tumbler.country == "Brasil"
    assert dry["dry_run"] is True
    assert dry["would_update"] == 5
    assert dry["updated"] == 0
    assert set(dry["ids"]) == {17, 837, 1061, 8240, 8258}

    with patch(
        "app.services.maintenance.async_session_maker",
        _TestSessionMaker(async_session),
    ):
        audit = await remediate_mislabeled_brazil_cities(dry_run=False)

    for event in (tumbler, tumbler_dup, joanesburgo, paramaribo, homs, salvador, sao_paulo):
        await async_session.refresh(event)

    assert tumbler.country == "CA"
    assert tumbler_dup.country == "CA"
    assert joanesburgo.country == "ZA"
    assert paramaribo.country == "SR"
    assert homs.country == "SY"
    assert salvador.country == "BR"
    assert sao_paulo.country == "Brasil"
    assert audit["updated"] == 5
    assert audit["relabeled"] == 5

    # Defense in depth: even the old Brasil+foreign-state combo would fail the UF gate.
    assert not include_in_unfiltered_brazil_city_ranking("Brasil", "Colúmbia Britânica")
    assert not include_in_unfiltered_brazil_city_ranking("Brasil", "Síria")
    assert not include_in_unfiltered_brazil_city_ranking("Brasil", None)
    assert not include_in_unfiltered_brazil_city_ranking(tumbler.country, tumbler.state)
    assert include_in_unfiltered_brazil_city_ranking(salvador.country, salvador.state)
    assert include_in_unfiltered_brazil_city_ranking(sao_paulo.country, sao_paulo.state)


@pytest.mark.asyncio
async def test_remediator_skips_already_correct_country(async_session):
    already_ca = _make_event(
        event_id=8240, city="Tumbler Ridge", state="Colúmbia Britânica", country="CA"
    )
    async_session.add(already_ca)
    await async_session.commit()

    with patch(
        "app.services.maintenance.async_session_maker",
        _TestSessionMaker(async_session),
    ):
        audit = await remediate_mislabeled_brazil_cities(dry_run=False)

    await async_session.refresh(already_ca)
    assert already_ca.country == "CA"
    assert audit["updated"] == 0
    assert audit["would_update"] == 0


@pytest.mark.asyncio
async def test_remediator_skips_known_id_with_real_br_uf_and_br_city(async_session):
    """Do not relabel a known id that looks like a real Brazilian event."""
    real_br = _make_event(
        event_id=17, city="São Paulo", state="SP", country="Brasil"
    )
    async_session.add(real_br)
    await async_session.commit()

    with patch(
        "app.services.maintenance.async_session_maker",
        _TestSessionMaker(async_session),
    ):
        audit = await remediate_mislabeled_brazil_cities(dry_run=False)

    await async_session.refresh(real_br)
    assert real_br.country == "Brasil"
    assert audit["updated"] == 0
