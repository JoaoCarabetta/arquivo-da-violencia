---
name: extend-extraction-schema
description: >-
  Extends the Arquivo da Violência extraction JSON schema for homicide incidents:
  decide if information already exists, add a new field built from existing
  extraction, or add a new LLM-extracted field with correct JSON placement,
  prompts, tests, and eval fixtures. Use when recording new facts about an
  incident in ViolentDeathEvent / extraction_data. Not for portal UI or tasks
  unrelated to recording homicide incidents in extraction.
---

# Extend Extraction Schema

## Scope

This skill covers **recording new information about homicide incidents** in the extraction JSON (`ViolentDeathEvent` → `raw_event.extraction_data`).

**In scope:** JSON shape in `extraction_schemas.py`, LLM prompt rules, population rules, unit tests, eval fixtures.

**Wrong skill — tell the user and stop** if the request is not about recording homicide incidents in extraction (e.g. portal UI, map filters, dedup, classification pipeline, infrastructure, non-homicide content).

**Portal:** ask at the end whether the field should appear on the portal; do **not** change frontend files in this skill.

---

## Workflow — run in order

Copy this checklist and work through it **with the user** before writing code.

```
Task progress:
- [ ] 1. About recording homicide incidents in extraction? (if no → wrong skill)
- [ ] 2. Already captured in extraction JSON?
- [ ] 3. Can add a NEW field built from existing extraction? (preferred)
- [ ] 4. Or needs new LLM extraction → new field + placement
- [ ] 5. Prompt / population rule / eval / tests
- [ ] 6. Ask: should this appear on the portal later? (no frontend work here)
```

### Step 1 — Right skill?

Is the request about **recording new information about homicide incidents** in the extraction schema?

→ **If no:** tell the user this is the **wrong skill** and stop. Common mismatches: portal or admin UI, map filters, export columns, dedup/enrichment, headline classification, database migrations unrelated to extraction JSON, or content outside violent-death homicide incidents.

→ **If yes:** continue. The incident is usually a single case (`content_class = incident`); ask the user if unclear.

### Step 2 — Already captured?

Search the current extraction schema and prompt. Does the information already have a **typed** home?

| Outcome | Action |
|---------|--------|
| Field exists and semantics match | **Done.** Tell the user where it lives (JSON path). Tune prompt/eval only if extraction quality is poor. |
| Only mentioned in `chronological_description` or prose | **Not captured.** Continue — structured storage is still needed. |
| Overlaps an existing field but semantics differ | Clarify with user; avoid duplicating columns/fields with different meanings. |

Key existing areas: `event_subtype`, `victims.*`, `perpetrators.*`, `homicide_dynamic.*`, `location_info.*`, `date_time.*`, root flags on `ViolentDeathEvent`.

### Step 3 — New field built from existing extraction (preferred)

Can the value be determined **after** the LLM runs, from fields already extracted?

→ Add a **new field** to the JSON shape, populated by a **rule** (e.g. `derive_*()` in `extraction.py`, or a Pydantic validator). **Do not** ask the LLM to extract this field directly.

**Prefer this over Step 4** when the fact is logically computable from existing output.

Example pattern: `security_force_involved` — new denormalized flag derived from victim/perp `is_security_force` lists.

Steps:
1. Add field to the correct model in `extraction_schemas.py`
2. Implement population rule; call before persist
3. Unit-test the rule
4. Eval case asserting the field value (dotted path or indirect via full extraction)

### Step 4 — New field needs LLM extraction

The text must be read and interpreted; it cannot be reliably built from existing fields alone.

1. **Place** the field (see [JSON placement](#json-placement) below)
2. Add to `extraction_schemas.py` with a clear `Field(description=...)` — the description guides the LLM
3. Add prompt rules in `extraction.py` (when to set true/false/null; disambiguation)
4. For victim/perp fields: complete [identifiable vs unidentified](#identifiable-vs-unidentified) checklist with the user
5. Always ask: should this live in `homicide_dynamic`? (default **no** for person attributes)

Nested fields appear in `extraction_data` automatically via `model_dump()`. SQL columns are **not** part of this skill unless the user explicitly asks later.

### Step 5 — Eval and tests

| Action | Command / file |
|--------|----------------|
| Unit tests | `pytest tests/test_extraction_*.py tests/test_taxonomy.py -v` (as relevant) |
| Validate fixture | `python -m eval extraction validate --fixture tests/fixtures/eval/<fixture>.json` |
| Run case(s) | `python -m eval extraction run --fixture ... --ids <case-id> --output eval/results/<name>.json` |
| Report | `python -m eval extraction report --run eval/results/<name>.json` |

Export env before LLM eval runs:

```bash
cd backend && export $(grep -v '^#' ../.env | xargs)
```

Add eval cases with `scoring.required_fields` using dotted paths (e.g. `victims.identifiable_victims.0.<field>`, `homicide_dynamic.<field>`).

→ Path examples: [reference.md](reference.md#eval-scoring-paths)

### Step 6 — Portal (ask only)

After schema and eval are settled, ask:

> "Should this new field appear on the public portal (detail, export, filters)?"

Note the answer for a **follow-up workflow**. Do **not** edit frontend or portal API files in this skill.

---

## Architecture (brief)

```
LLM prompt (extraction.py)
    → ViolentDeathEvent (extraction_schemas.py)
    → population rules (optional — Step 3)
    → raw_event.extraction_data (JSON, always)
```

Full layer table → [reference.md](reference.md#data-layers)

---

## JSON placement

```
ViolentDeathEvent
├── event_family / event_subtype     ← incident classification (existing)
├── content_class
├── location_info                    ← where
├── date_time                        ← when
├── victims
│   ├── identifiable_victims[]
│   ├── unidentified_groups[]
│   └── number_of_* / number_of_victims
├── perpetrators (optional)
│   ├── identifiable_perpetrators[]
│   ├── unidentified_groups[]
│   └── number_of_* / number_of_perpetrators
├── homicide_dynamic
│   ├── title
│   ├── method
│   └── chronological_description    ← narrative only — not sole storage for typed facts
└── additional_context               ← last resort prose
```

| Question | Place field |
|----------|-------------|
| Who (identity, role, employer, on-duty)? | `IdentifiableVictim` / `IdentifiablePerpetrator` or group models — **not** `homicide_dynamic` |
| Event-level how (means, commission context, one value per incident)? | `homicide_dynamic` |
| Where / when? | `location_info` / `date_time` |
| Whole-event flag not covered above? | `ViolentDeathEvent` root |

→ `homicide_dynamic` detail: [reference.md](reference.md#homicide_dynamic--ask-on-every-placement-review)

### Placement checklist

Copy with the user when adding any field:

```
- [ ] Already exists? (Step 2)
- [ ] Built from existing extraction? (Step 3) vs LLM extraction? (Step 4)
- [ ] IdentifiableVictim
- [ ] UnidentifiedVictimGroup
- [ ] IdentifiablePerpetrator
- [ ] UnidentifiedPerpetratorGroup
- [ ] homicide_dynamic — event-level HOW (not who)?
- [ ] location_info / date_time
- [ ] ViolentDeathEvent root
- [ ] additional_context only (reject if a typed home exists above)
- [ ] Prompt and/or population rule
- [ ] Eval path(s) for each slot marked yes
```

---

## Identifiable vs unidentified

When the field is on **victims or perpetrators**, walk through all four slots with the user:

| Model | When |
|-------|------|
| `IdentifiableVictim` | Each individually described victim |
| `UnidentifiedVictimGroup` | Count + collective description only |
| `IdentifiablePerpetrator` | Each individually described author |
| `UnidentifiedPerpetratorGroup` | Unnamed author group |

| Field kind | Identifiable* | Unidentified*Group |
|------------|---------------|---------------------|
| Name, age, gender, occupation | Yes | No — use `description` |
| Booleans (`is_security_force`, `is_civilian`) | Yes | Yes |
| Enums / detailed status | Yes, per person | Usually **no** — unless text describes whole group |

Mirror across victim and perpetrator sides when the attribute applies to both.

Population rules and eval must scan **identifiable lists and unidentified groups** on both sides.

→ Worked examples: [examples.md](examples.md)

---

## Implementation checklist (Steps 3–5)

### Path A — Built field (Step 3)

- [ ] `extraction_schemas.py` — new field on correct model
- [ ] `extraction.py` — `derive_*()` or post-extraction population; **no** LLM prompt for this field
- [ ] Unit test for the rule
- [ ] Eval fixture — assert field value

### Path B — LLM-extracted field (Step 4)

- [ ] `extraction_schemas.py` — `Field(description=...)`
- [ ] `extraction.py` — prompt section (identifiable vs group wording for victim/perp fields)
- [ ] Eval fixture — `scoring.required_fields` with dotted path(s)
- [ ] Optional: smoke test on a real article

### Common files

| File | Path A | Path B |
|------|--------|--------|
| `backend/app/services/extraction_schemas.py` | ✓ | ✓ |
| `backend/app/services/extraction.py` | population rule | prompt + rule if also derived |
| `backend/tests/fixtures/eval/*.json` | ✓ | ✓ |
| `backend/tests/test_extraction_*.py` | ✓ rule tests | as needed |

**Do not change:** `frontend/**`, DB models/alembic (unless user explicitly requests SQL promotion outside this skill).

---

## What NOT to do

| Mistake | Instead |
|---------|---------|
| New subtype for a person attribute | Victim/perp field (Step 4) or built field (Step 3) |
| LLM extracts a field computable from existing data | Step 3 — new field + population rule |
| Store typed facts only in `chronological_description` | Typed field in correct JSON slot |
| Edit portal/frontend in this skill | Ask in Step 6; separate workflow |
| Task not about recording homicide incidents | Tell user — wrong skill (Step 1) |

---

## Additional resources

- File checklist, eval paths, model map → [reference.md](reference.md)
- Worked examples → [examples.md](examples.md)
- Eval CLI details → `backend/eval/README.md`
