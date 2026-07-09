# Extend Extraction Schema — Reference

Main workflow → [SKILL.md](SKILL.md). Lookup for schema spec, derivation columns, eval paths, and file touchpoints.

## Decision summary

| Step | Question | Outcome |
|------|----------|---------|
| 1 | Recording homicide incidents? | If no → wrong skill |
| 2 | Already in JSON? | If yes → done |
| 3 | Gut checks (placement) | Subtype vs victim vs dynamics |
| 4 | Built from existing extraction? | Preferred — derive, no LLM |
| 5 | Needs LLM extraction? | Schema + prompt |
| 6 | derive_public_fields + eval | Required |
| 7 | CSV / portal / filters? | Alembic + API + frontend |

---

## Pending schema: criminal group + politics

Approved design (implement on feature branch — not yet in production code).

### `CriminalGroupActivity` enum

```python
CriminalGroupActivity = Literal[
    "internal-discipline",
    "internal-dispute",
    "population-discipline",
    "informant-elimination",
    "debt-enforcement",
    "territorial-dispute",
    "economic-dispute",
    "retaliatory",
    "police-ambush",
    "protest",        # includes anti-state / policy violence
    "collateral",
    "unspecified",
]
```

### `CriminalGroupContext` (under `HomicideDynamic`)

```python
class CriminalGroupContext(BaseModel):
    connected: bool | None = None
    groups: list[str] | None = None              # verbatim from text
    activity: CriminalGroupActivity | None = None
    activity_description: str | None = None      # edge cases; must be text-grounded

    group_attacked: str | None = None            # territorial-dispute; some retaliatory
    rival_actor: str | None = None               # economic-dispute
    target_force: str | None = None              # police-ambush
    policy_trigger: str | None = None            # protest
```

**Conditional nulls:** if `connected` is false/null → all other fields in block null. If `activity` set, apply activity-specific null rules (e.g. `group_attacked` only for territorial-dispute).

**Priority when multiple activities fit:** territorial-dispute > economic-dispute > retaliatory > unspecified.

### `PoliceOperationContext` (under `HomicideDynamic`)

```python
class PoliceOperationContext(BaseModel):
    connected: bool | None = None
    responsible_force: str | None = None         # PM, PC, PF, PRF, … verbatim
    targeted_armed_groups: bool | None = None
    operation_name: str | None = None
```

Distinct from `event_subtype=intervencao_policial` (legal classification vs factual circumstance).

### Off-duty police perpetrator (under `HomicideDynamic`)

```python
off_duty_police_perpetrator: bool | None = None
off_duty_police_context: Literal[
    "genuine_reaction", "moonlighting", "criminal_organization"
] | None = None
```

**Perpetrator-side only** — not official operation, not police-as-victim. Link to `perpetrators[].is_security_force` when perpetrator identifiable.

### `PoliticalRole` (on `IdentifiableVictim` only)

```python
PoliticalStatus = Literal["elected", "candidate", "former_elected"]

class PoliticalRole(BaseModel):
    is_politician_or_candidate: bool
    status: PoliticalStatus | None = None
    office: str | None = None          # "vereador" even for ex-vereador (not "ex-vereador")
    party: str | None = None           # verbatim sigla/name; null if not stated
```

- Object present only when text explicitly identifies victim as officeholder or candidate.
- **Per victim** — multi-victim events may have mixed politics.
- Do not guess party from city or ideology.

### Victim security-agent fields (proposed)

On `IdentifiableVictim` / `IdentifiablePerpetrator` when `is_security_force=true`:

| Field | Type |
|-------|------|
| `security_agent_type` | `Literal["PM","PC","PF","PRF","penal","outro"] \| null` |
| `security_agent_on_duty` | `bool \| null` — true=em serviço, false=folga, null=not stated |

---

## Public surface — `derive_public_fields()`

Implement once in `backend/app/services/extraction.py` (or `extraction_derived.py`):

```python
def derive_public_fields(event: ViolentDeathEvent) -> dict[str, object | None]:
    """Flat columns for unique_event, API, and CSV — single source of truth."""
    ...
```

Call from raw_event persist and unique_event enrichment/update.

### Proposed flat columns

| Column | Source |
|--------|--------|
| `criminal_group_connected` | `homicide_dynamic.criminal_group_context.connected` |
| `criminal_group_activity` | `.activity` |
| `criminal_group_activity_description` | `.activity_description` |
| `criminal_groups` | `"; ".join(groups)` or null |
| `criminal_group_attacked` | `.group_attacked` |
| `police_operation_connected` | `police_operation_context.connected` |
| `police_operation_force` | `.responsible_force` |
| `police_operation_targeted_armed_groups` | `.targeted_armed_groups` |
| `off_duty_police_perpetrator` | `homicide_dynamic.off_duty_police_perpetrator` |
| `politician_or_candidate_victim` | any victim `political_role.is_politician_or_candidate` |
| `victim_political_status` | joined statuses from politician victims |
| `victim_political_office` | joined offices |
| `victim_political_party` | joined parties |

Existing: `security_force_involved` from `derive_security_force_involved()` — keep; may fold into `derive_public_fields()` wrapper.

### File checklist — public surface (Step 7)

| File | Changes |
|------|---------|
| `backend/app/services/extraction_schemas.py` | Nested models |
| `backend/app/services/extraction.py` | Prompt + `derive_public_fields()` |
| `backend/app/services/enrichment.py` | Persist flat fields on unique_event |
| `backend/app/models/unique_event.py` | New columns |
| `backend/app/models/raw_event.py` | Optional mirror columns |
| `backend/alembic/versions/*.py` | Migration |
| `backend/app/routers/public.py` | Export allowlist + row builder + detail API |
| `backend/tests/test_export_columns.py` | New columns |
| `backend/tests/test_extraction_derived.py` | Derivation unit tests (create if needed) |
| `frontend/src/lib/exportColumns.ts` | Export groups |
| `frontend/src/lib/i18n.ts` | Dictionary labels PT/EN |
| `frontend/src/lib/api.ts` | TypeScript types |
| `frontend/src/lib/eventDetail.ts` | Label aliases |
| `frontend/src/components/portal/EventDetailView.tsx` | Display sections |
| `backend/tests/fixtures/eval/extraction_hard.json` | Labeled cases |

**Detail API:** add `merged_data` (or structured `victims` / `homicide_dynamic` slice) to `_format_public_event_detail` when UI needs per-victim `political_role`.

---

## Data layers

| Layer | Location | When |
|-------|----------|------|
| JSON shape | `extraction_schemas.py` | Any new field |
| LLM prompt | `extraction.py` | LLM-extracted fields |
| Derivation | `derive_public_fields()` | Flat columns |
| Full JSON | `raw_event.extraction_data`, `unique_event.merged_data` | Automatic via `model_dump()` |
| Flat SQL | `unique_event.*` columns | Portal export/filters |
| Eval | `tests/fixtures/eval/*.json` | Regression |

---

## Identifiable vs unidentified

| Model | When |
|-------|------|
| `IdentifiableVictim` | Individual victim |
| `UnidentifiedVictimGroup` | Group only |
| `IdentifiablePerpetrator` | Individual author |
| `UnidentifiedPerpetratorGroup` | Unnamed group |

| Field kind | Identifiable* | Unidentified*Group |
|------------|---------------|---------------------|
| `political_role` | Yes | No |
| `security_agent_type`, `security_agent_on_duty` | Yes | No (unless whole group described) |
| `is_security_force` | Yes | Yes |

---

## homicide_dynamic placement

| Field | Role |
|-------|------|
| `title`, `method`, `chronological_description` | Existing |
| `criminal_group_context` | OCG/facção/milícia event dynamics |
| `police_operation_context` | Official operation facts |
| `off_duty_police_perpetrator` | Perpetrator off duty (not op) |

**Not for:** victim politician status, victim police on-duty (use victim models).

---

## Eval scoring paths

```
homicide_dynamic.criminal_group_context.connected
homicide_dynamic.criminal_group_context.activity
homicide_dynamic.criminal_group_context.groups
homicide_dynamic.criminal_group_context.group_attacked
homicide_dynamic.police_operation_context.connected
homicide_dynamic.off_duty_police_perpetrator
victims.identifiable_victims.0.political_role.is_politician_or_candidate
victims.identifiable_victims.0.political_role.status
victims.identifiable_victims.0.political_role.office
victims.identifiable_victims.0.political_role.party
victims.identifiable_victims.0.security_agent_on_duty
```

Update `eval/schemas_extraction.py` `DEFAULT_REQUIRED_FIELDS` only for fields required on **all** cases.

## Validation commands

```bash
cd backend && export $(grep -v '^#' ../.env | xargs)

pytest tests/test_extraction_*.py tests/test_export_columns.py -v
python -m eval extraction validate --fixture tests/fixtures/eval/extraction_hard.json
python -m eval extraction run --fixture tests/fixtures/eval/extraction_hard.json --ids <case-id> --output eval/results/test.json
python -m eval extraction report --run eval/results/test.json
```

Docker (repo convention):

```bash
docker compose -f docker-compose.dev.yml exec api \
  pytest tests/test_extraction_*.py -v
```
