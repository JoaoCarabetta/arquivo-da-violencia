"""Seed geocoded unique events for local portal / filter testing.

Run from repo root:

    docker compose -f docker-compose.dev.yml exec api python -m app.dev.seed_portal
    docker compose -f docker-compose.dev.yml exec api python -m app.dev.seed_portal --clear
"""

from __future__ import annotations

import argparse
import asyncio
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlmodel import SQLModel

from app.database import async_session_maker, get_engine
from app.models.unique_event import UniqueEvent
from app.taxonomy import parse_legacy_homicide_type

TYPES = [
    "Homicídio",
    "Homicídio Qualificado",
    "Feminicídio",
    "Latrocínio",
    "Intervenção policial",
]
METHODS = [
    "Arma de fogo",
    "Arma branca",
    "Estrangulamento",
    "Envenenamento",
]
PERIODS = ["madrugada", "manhã", "tarde", "noite"]

CITIES: list[tuple[str, str, float, float]] = [
    ("São Paulo", "SP", -23.5505, -46.6333),
    ("Rio de Janeiro", "RJ", -22.9068, -43.1729),
    ("Belo Horizonte", "MG", -19.9167, -43.9345),
    ("Salvador", "BA", -12.9714, -38.5014),
    ("Fortaleza", "CE", -3.7172, -38.5433),
    ("Recife", "PE", -8.0476, -34.8770),
    ("Curitiba", "PR", -25.4284, -49.2733),
    ("Porto Alegre", "RS", -30.0346, -51.2177),
    ("Brasília", "DF", -15.7939, -47.8828),
    ("Manaus", "AM", -3.1190, -60.0217),
    ("Belém", "PA", -1.4558, -48.4902),
    ("Goiânia", "GO", -16.6869, -49.2648),
]

NEIGHBORHOODS = [
    "Centro",
    "Copacabana",
    "Tijuca",
    "Boa Viagem",
    "Savassi",
    "Barra",
    "Asa Norte",
    "Mooca",
    None,
]


async def ensure_tables() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def clear_seed_events(session) -> int:
    result = await session.execute(
        delete(UniqueEvent).where(UniqueEvent.geocoding_source == "dev_seed")
    )
    await session.commit()
    return result.rowcount or 0


async def seed_events(count: int, seed: int) -> int:
    rng = random.Random(seed)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    events: list[UniqueEvent] = []

    for i in range(count):
        city, state, lat, lng = rng.choice(CITIES)
        jitter_lat = lat + rng.uniform(-0.08, 0.08)
        jitter_lng = lng + rng.uniform(-0.08, 0.08)
        days_ago = rng.randint(1, 300)
        event_date = now - timedelta(days=days_ago, hours=rng.randint(0, 23))

        homicide_type = rng.choice(TYPES)
        family, subtype = parse_legacy_homicide_type(homicide_type)

        events.append(
            UniqueEvent(
                event_family=family,
                event_subtype=subtype,
                homicide_type=homicide_type,
                method_of_death=rng.choice(METHODS),
                content_class="incident",
                event_date=event_date,
                time_of_day=rng.choice(PERIODS),
                country="Brasil",
                state=state,
                city=city,
                neighborhood=rng.choice(NEIGHBORHOODS),
                latitude=Decimal(str(round(jitter_lat, 6))),
                longitude=Decimal(str(round(jitter_lng, 6))),
                victim_count=rng.randint(1, 4),
                security_force_involved=rng.random() < 0.12,
                title=f"Evento de teste {i + 1} — {city}",
                geocoding_source="dev_seed",
                geocoding_confidence=0.9,
                location_precision="city_center",
                confirmed=True,
                needs_enrichment=False,
            )
        )

    async with async_session_maker() as session:
        session.add_all(events)
        await session.commit()

    return len(events)


async def count_map_ready(session) -> int:
    result = await session.execute(
        select(func.count(UniqueEvent.id)).where(
            UniqueEvent.latitude.isnot(None),
            UniqueEvent.longitude.isnot(None),
        )
    )
    return int(result.scalar_one())


async def run_seed(*, count: int, seed: int, clear: bool) -> None:
    await ensure_tables()

    if clear:
        async with async_session_maker() as session:
            removed = await clear_seed_events(session)
        print(f"Removed {removed} dev_seed events")

    inserted = await seed_events(count, seed)

    async with async_session_maker() as session:
        total = await count_map_ready(session)

    print(f"Inserted {inserted} dev_seed events ({total} geocoded total)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed dev portal map data")
    parser.add_argument("--count", type=int, default=48, help="Events to insert")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed")
    parser.add_argument("--clear", action="store_true", help="Remove previous dev_seed rows")
    args = parser.parse_args()
    asyncio.run(run_seed(count=args.count, seed=args.seed, clear=args.clear))


if __name__ == "__main__":
    main()
