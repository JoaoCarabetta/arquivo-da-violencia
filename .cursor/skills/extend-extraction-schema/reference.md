# Extend Extraction Schema — Reference

Main workflow → [SKILL.md](SKILL.md). This file is lookup detail for JSON placement, eval paths, and file touchpoints.

## Decision summary

| Step | Question | Outcome |
|------|----------|---------|
| 1 | Recording homicide incidents in extraction? | If no → **wrong skill**, stop |
| 2 | Already in JSON schema? | If yes → done (document path) |
| 3 | New field **built** from existing extraction? | **Preferred** — new field + population rule, no LLM prompt for it |
| 4 | Needs **LLM extraction**? | New field + prompt + placement |
| 5 | Tests + eval fixtures | Required |
| 6 | Portal exposure? | Ask only — separate workflow |

**Built field vs LLM field:** both add a new campo to the JSON shape. A built field is filled by a rule after extraction; an LLM field is read from the article text.

## Identifiable vs unidentified (victim / perpetrator)

When adding or changing **any** victim or perpetrator field, prompt the user through **all four model slots**:

| Model | When to use |
|-------|-------------|
| `IdentifiableVictim` | Each individually described victim |
| `UnidentifiedVictimGroup` | Count + collective description only |
| `IdentifiablePerpetrator` | Each individually described author |
| `UnidentifiedPerpetratorGroup` | Unnamed author group |

**Mirror** across victim and perpetrator sides when the attribute applies to both. **Group models** usually carry booleans (`is_security_force`, `is_civilian`) and `description`/`context` — not full per-person enums unless the text describes the whole group.

**Eval:** at least one identifiable case; add an unidentified-group case if group fields changed.

**Population rules:** scan `identifiable_*` lists **and** `unidentified_groups` on both victims and perpetrators.

### `homicide_dynamic` — ask on every placement review

| Field | Role |
|-------|------|
| `title` | Formatted technical headline — not for arbitrary new attributes |
| `method` | `MethodOfDeath` enum — means of killing |
| `chronological_description` | Required narrative — may repeat facts; **not** sole storage for typed data |
| *new fields* | Event-level **how** (commission mode, context) — one value per incident |

**Not for:** victim/perp identity, occupation, on-duty (use victim/perp models).

**Ask:** "Should this live in `homicide_dynamic`?" — default **no** for person attributes; **yes** for incident-level dynamics.

### Victim security-agent fields (example — proposed standard)

On `IdentifiableVictim` and `IdentifiablePerpetrator` (when party is security force):

| Field | Type | When to set |
|-------|------|-------------|
| `is_security_force` | `bool \| null` | **Exists.** True if PM/PC/PF/PRF/penal/guarda |
| `security_agent_type` | `Literal["PM","PC","PF","PRF","penal","outro"] \| null` | Only when `is_security_force=true` |
| `security_agent_on_duty` | `bool \| null` | Only when `is_security_force=true`; `true`=em serviço, `false`=folga, `null`=texto não diz |

Mirror `is_security_force` on group models; type/on_duty only when individuals are identifiable.

## Wrong skill (Step 1)

Tell the user and stop if the request is **not** about recording homicide incidents in the extraction JSON — e.g. portal UI, dedup, enrichment, classification-only work, or non-homicide scope.

Person attributes belong on victim/perp models, not as a substitute for unrelated tasks.

## Portal / frontend — deferred

Do not edit frontend in the extraction-schema skill. After Step 6, portal work may include (separate workflow):

| Concern | Typical files |
|---------|---------------|
| Event detail | `EventDetailView.tsx`, `eventDetail.ts`, `public.py` |
| Export | `exportColumns.ts` |
| Map + filter + stats | `types.ts`, `RightPanel.tsx`, `public.py` `/map-points`, denormalized SQL columns |

See git history or a future portal skill for tier patterns. SQL denormalization is only needed when the portal must filter or aggregate in SQL.

## Data layers

| Layer | Location | When to change |
|-------|----------|----------------|
| JSON shape | `extraction_schemas.py` | Any new field (built or LLM) |
| LLM instructions | `extraction.py` system prompt | LLM-extracted fields only (Step 4) |
| Population rules | `extraction.py` | Built fields (Step 3) |
| Full extraction JSON | `raw_event.extraction_data` | Automatic via `model_dump()` |
| Queryable SQL columns | `raw_event`, `unique_event` | **Out of scope** unless user requests separately |
| Eval spec | `tests/fixtures/eval/*.json` | Regression cases |

## Nested models in `extraction_schemas.py`

| Model | Use for |
|-------|---------|
| `IdentifiableVictim` | name, age, gender, occupation, `is_security_force`, proposed `security_agent_*`, relationship |
| `UnidentifiedVictimGroup` | count, description, `is_security_force`, `is_civilian`, context |
| `IdentifiablePerpetrator` | same pattern as identifiable victim |
| `UnidentifiedPerpetratorGroup` | same pattern as unidentified victim group |
| `Location` | neighborhood, street, city, state, establishment |
| `DateTime` / `DateVerification` | date extraction with verification |
| `HomicideDynamic` | `title`, `method`, `chronological_description`; event-level **how** |
| `ViolentDeathEvent` | root: `event_family`, `event_subtype`, victims, perpetrators, content_class |

## File checklist — built field (Step 3)

| File | Changes |
|------|---------|
| `backend/app/services/extraction_schemas.py` | New field on correct nested model |
| `backend/app/services/extraction.py` | `derive_*()` or post-extraction population — **no** LLM prompt for this field |
| `backend/tests/test_extraction_*.py` | Unit tests for rule |
| `backend/tests/fixtures/eval/*.json` | Case asserting field value |

## File checklist — LLM field (Step 4)

| File | Changes |
|------|---------|
| `backend/app/services/extraction_schemas.py` | New `Field` with LLM-facing description |
| `backend/app/services/extraction.py` | Prompt rules (identifiable vs group for victim/perp) |
| `backend/tests/fixtures/eval/*.json` | `scoring.required_fields` with dotted paths |

## Eval scoring paths

Dotted paths used by `eval/stages/extraction/score.py`:

```
event_family
event_subtype
content_class
date_time.date
location_info.city
location_info.state
victims.number_of_victims
victims.identifiable_victims.0.is_security_force
victims.identifiable_victims.0.<new_field>
victims.unidentified_groups.0.is_security_force
homicide_dynamic.method
homicide_dynamic.<new_field>
```

Update `eval/schemas_extraction.py` `DEFAULT_REQUIRED_FIELDS` only if the field should be scored on **all** cases by default.

## Eval fixtures

| Fixture | When |
|---------|------|
| `extraction_hard.json` | Full extraction with custom `required_fields` |
| `extraction_seed.json` | Bootstrap from DB (hand-review labels) |

## Validation commands

```bash
cd backend && export $(grep -v '^#' ../.env | xargs)

pytest tests/test_extraction_*.py tests/test_eval_extraction.py -v
python -m eval extraction validate --fixture tests/fixtures/eval/extraction_hard.json
python -m eval extraction run --fixture tests/fixtures/eval/extraction_hard.json --ids <case-id> --output eval/results/test.json
python -m eval extraction report --run eval/results/test.json
```
