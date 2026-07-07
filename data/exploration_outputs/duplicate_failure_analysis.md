# Duplicate failure analysis (since 2026-07-04)

Scan source: public API pagination (200 most recent events) + [`find_near_duplicate_events.py`](../../backend/scripts/find_near_duplicate_events.py) for full Postgres scan on prod.

**65 near-duplicate pairs** found in the partial API scan (90 events since 2026-07-04).

## Confirmed regression pairs

| Pair | City | Signal | Tags |
|------|------|--------|------|
| 9843 / 9851 | São José | victim_name (summary overlap) | cross_wave, victim_name_match |
| 9744 / 9784 | Confresa | victim_name (Daiany Rodrigues de Souza) | cross_wave, victim_name_match, title_drift |

Confresa has **4** split UniqueEvents (9744, 9756, 9767, 9784, 9811) for the same feminicídio.

## Failure tag counts (partial scan)

| Tag | Approx. pairs | Root cause |
|-----|---------------|------------|
| cross_wave | ~60 | Batch dedup created new UniqueEvent without matching existing (Phase 1 skipped) |
| victim_name_match | ~55 | Same victim in summaries; pipeline still split across waves |
| title_drift | ~5 | Titles differ enough to miss old 0.85 fuzzy threshold |

## Largest duplicate clusters

- **Palmas** (9873, 9884, 9889, 9894, 9867, 9883): police intervention, same location labels
- **João Pessoa** (9806, 9823, 9868, 9835, 9818): Mercadinho Valentina
- **Horizonte** (9793, 9771, 9773, 9808, 9749, 9830): influenciadora feminicídio
- **Confresa** (9744, 9756, 9767, 9784, 9811): Daiany Rodrigues de Souza
- **Paraty** (9845, 9852, 9897, 9885): child shooting in praça

## Algorithm fixes applied

1. Phase 1 matching inside `process_pending_deduplication` (cross-wave prevention)
2. `FUZZY_TITLE_THRESHOLD` 0.85 → 0.80
3. Victim name fallback from description/title when `identifiable_victims` empty
4. Fuzzy victim pre-clustering in batch dedup
5. Post-hoc `merge_near_duplicate_unique_events` maintenance task
6. Eval fixtures for São José + Confresa regression cases

## Recommended prod merges (survivor = highest source_count)

Run after deploy:

```bash
docker exec arquivo-api python scripts/merge_duplicate_events.py --execute --survivor 9851 --losers 9843
docker exec arquivo-api python scripts/merge_duplicate_events.py --execute --survivor 9784 --losers 9744 9756 9767 9811
# See duplicate_groups_since_2026-07-04.csv for full list
```
