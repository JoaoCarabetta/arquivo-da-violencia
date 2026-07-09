---
name: extend-extraction-schema
description: >-
  Extends the Arquivo da Violência extraction schema: new Pydantic fields,
  homicide dynamics (criminal group context, police operations), victim/perpetrator
  attributes (political role, security agent), derived flat columns for CSV export
  and portal UI, LLM prompts, tests, and eval fixtures. Use when adding extraction
  fields, changing ViolentDeathEvent, or wiring new facts to export and frontend.
---

# Extend Extraction Schema

## Scope

This skill covers **recording new information about homicide incidents** end-to-end:

| Layer | In scope |
|-------|----------|
| JSON shape | `ViolentDeathEvent` in `extraction_schemas.py` |
| LLM + rules | Prompt in `extraction.py`, `derive_*()` population |
| Persistence | `raw_event.extraction_data`, `unique_event.merged_data` |
| Public surface | Flat columns, API, CSV export, frontend (when user wants portal/export) |

**Wrong skill — tell the user and stop** if the request is unrelated (dedup logic, classification-only, infrastructure, non-homicide content).

---

## Architecture — two layers, one derivation

```
LLM prompt (extraction.py)
    → ViolentDeathEvent (extraction_schemas.py)
    → derive_*() rules (optional, Step 3)
    → derive_public_fields(event)  ← single function for flat surface
    → raw_event.extraction_data (JSON, source of truth)
    → unique_event.merged_data + flat columns (after dedup/enrichment)
    → public API + CSV export + EventDetailView
```

**Rule:** CSV and frontend must read the **same flat columns** produced by `derive_public_fields()`. Never hand-maintain export columns separately from API fields.

Full column list and file checklist → [reference.md](reference.md#public-surface--derive_public_fields)

---

## Workflow — run in order

```
Task progress:
- [ ] 1. Recording homicide incidents in extraction? (if no → wrong skill)
- [ ] 2. Already captured in extraction JSON?
- [ ] 3. Gut checks — subtype vs victim/perp vs homicide_dynamic?
- [ ] 4. Built field from existing extraction? (preferred)
- [ ] 5. Or LLM-extracted field → placement + prompt
- [ ] 6. derive_public_fields() + tests + eval
- [ ] 7. Public surface (if user wants CSV / portal / filters)
```

### Step 1 — Right skill?

Is the request about **recording new facts about homicide incidents**?

→ **If no:** wrong skill — stop.

→ **If yes:** continue (`content_class = incident` unless user says otherwise).

### Step 2 — Already captured?

| Outcome | Action |
|---------|--------|
| Typed field exists and semantics match | **Done.** Document JSON path. Tune prompt/eval if quality is poor. |
| Only in `chronological_description` | **Not captured.** Continue. |
| Overlaps existing field with different meaning | Clarify with user before adding. |

Key areas: `event_subtype`, `victims.*`, `perpetrators.*`, `homicide_dynamic.*`, `location_info.*`, `date_time.*`.

### Step 3 — Gut checks (placement)

Run with the user before writing code.

#### A. Person attribute vs incident dynamic vs taxonomy

| Question | If yes → | If no → |
|----------|----------|---------|
| Describes **who** someone is (police, politician, occupation)? | `IdentifiableVictim` / `IdentifiablePerpetrator` | Continue |
| Describes **how/why** at event level (faction dispute, police op)? | `homicide_dynamic` nested context | Continue |
| Legal **classification** of the death type? | `event_subtype` (rare — prefer attributes) | Continue |

**Do not** add subtypes for person attributes (e.g. `police_victim` → use victim fields).

#### B. Criminal group: broad vs specific

| Field | Meaning |
|-------|---------|
| `criminal_group_context.connected` | Broad — homicide linked to armed/organized group activity |
| `criminal_group_context.activity` | Specific mechanism (enum) |
| `criminal_group_context.groups` | Verbatim group names from text |

Activity `territorial-dispute` implies organized-crime context; do not require `connected=true` separately when activity is set.

#### C. Parallel dimensions (can all be true)

One incident may simultaneously have:

- `criminal_group_context` (OCG/facção dynamics)
- `police_operation_context` (official operation)
- `off_duty_police_perpetrator` (perpetrator-side, not an official op)

These are **not** mutually exclusive.

#### D. Extraction discipline (criminal group + politics)

| Tier | Rule |
|------|------|
| Extract | Explicit statements ("integrante do PCC", "Operação Verão") |
| `unspecified` | Connected to group activity but mechanism not classifiable |
| Do not extract | Neighborhood dominance, prior arrests, "possível acerto de contas" without group link |

Activity tie-break when multiple fit: **territorial-dispute > economic-dispute > retaliatory > unspecified**.

Attacker/defender (`group_attacked`, etc.): **null when unclear** — do not infer from chronology alone.

→ Canonical pending schema: [reference.md](reference.md#pending-schema-criminal-group--politics)

### Step 4 — Built field (preferred)

Can the value be computed **after** LLM extraction from existing fields?

→ Add field + `derive_*()` in `extraction.py`. **Do not** ask LLM to extract it.

Examples: `security_force_involved`, event-level flags derived from nested victim/perp lists.

### Step 5 — LLM-extracted field

1. Place field (see [JSON placement](#json-placement))
2. Add to `extraction_schemas.py` with clear `Field(description=...)`
3. Add prompt rules in `extraction.py`
4. For victim/perp: walk [identifiable vs unidentified](#identifiable-vs-unidentified)
5. Conditional nulls: detail fields null when parent flag is false/null

### Step 6 — Derive, test, eval

1. Implement or extend `derive_public_fields(event) -> dict` for any flat column
2. Call from `extraction.py` (raw_event) and `enrichment.py` (unique_event)
3. Unit-test derivation rules
4. Add eval cases with dotted `scoring.required_fields`

```bash
cd backend && export $(grep -v '^#' ../.env | xargs)
pytest tests/test_extraction_*.py -v
python -m eval extraction validate --fixture tests/fixtures/eval/extraction_hard.json
python -m eval extraction run --fixture tests/fixtures/eval/extraction_hard.json --ids <case-id> --output eval/results/test.json
python -m eval extraction report --run eval/results/test.json
```

### Step 7 — Public surface (CSV + frontend)

When the user wants data in **export and/or portal** (default for research fields):

| Piece | File |
|-------|------|
| DB columns | Alembic migration on `unique_event` (+ optional `raw_event`) |
| Derivation | `derive_public_fields()` in `extraction.py` (or `extraction_derived.py`) |
| Persist | `extraction.py`, `enrichment.py` |
| API + CSV | `backend/app/routers/public.py` — `PUBLIC_EXPORT_FIELD_NAMES`, `_event_to_export_row`, `_format_public_event_detail` |
| Export UI | `frontend/src/lib/exportColumns.ts` |
| Labels | `frontend/src/lib/i18n.ts` `dictionaryRows` |
| Types | `frontend/src/lib/api.ts` |
| Detail UI | `frontend/src/components/portal/EventDetailView.tsx` |
| Per-victim detail | Expose `merged_data` (or `victims` slice) on detail API when nested data needed |

**Per-victim fields** (e.g. `political_role`): store nested in JSON; derive **event-level summary columns** for CSV; show full detail from `merged_data` on event detail page.

Skip Step 7 only when user explicitly wants JSON-only (pipeline storage, no portal yet).

---

## JSON placement

```
ViolentDeathEvent
├── event_family / event_subtype
├── content_class
├── location_info / date_time
├── victims
│   └── identifiable_victims[]
│       ├── is_security_force, security_agent_type, security_agent_on_duty  (proposed)
│       └── political_role  (proposed — per victim)
├── perpetrators (optional)
│   └── identifiable_perpetrators[]
├── homicide_dynamic
│   ├── title, method, chronological_description
│   ├── criminal_group_context      (proposed — event-level HOW)
│   ├── police_operation_context    (proposed)
│   └── off_duty_police_perpetrator (+ context enum)  (proposed)
└── additional_context
```

| Question | Place field |
|----------|-------------|
| Who (politician, police type, on-duty)? | `IdentifiableVictim` / `IdentifiablePerpetrator` |
| Perpetrator off duty (not official op)? | `homicide_dynamic.off_duty_police_*` or perpetrator when identifiable |
| OCG activity, police operation context? | `homicide_dynamic.*_context` |
| Filterable event summary for CSV? | `derive_public_fields()` → SQL columns |

### Placement checklist

```
- [ ] Step 2: already exists?
- [ ] Step 3 gut checks passed
- [ ] IdentifiableVictim / UnidentifiedVictimGroup
- [ ] IdentifiablePerpetrator / UnidentifiedPerpetratorGroup
- [ ] homicide_dynamic (event-level HOW)
- [ ] derive_public_fields() + column list (if portal/export)
- [ ] Prompt + conditional null rules
- [ ] Eval dotted path(s)
```

---

## Identifiable vs unidentified

When the field is on **victims or perpetrators**, review all four slots:

| Model | When |
|-------|------|
| `IdentifiableVictim` | Each individually described victim |
| `UnidentifiedVictimGroup` | Count + collective description only |
| `IdentifiablePerpetrator` | Each individually described author |
| `UnidentifiedPerpetratorGroup` | Unnamed author group |

**Political role:** per identifiable victim only — no group-level political block.

Population rules and eval must scan identifiable lists **and** unidentified groups where applicable.

→ Examples: [examples.md](examples.md)

---

## Implementation checklist

### Path A — Built field (Step 4)

- [ ] `extraction_schemas.py`
- [ ] `derive_*()` in `extraction.py`
- [ ] Unit test
- [ ] Eval case

### Path B — LLM field (Step 5)

- [ ] `extraction_schemas.py` + `Field(description=...)`
- [ ] Prompt in `extraction.py`
- [ ] Eval fixture with dotted paths

### Path C — Public surface (Step 7)

- [ ] Alembic migration
- [ ] `derive_public_fields()` — single source for flat values
- [ ] `extraction.py` + `enrichment.py` persist
- [ ] `public.py` export + detail API
- [ ] `exportColumns.ts`, `i18n.ts`, `api.ts`, `EventDetailView.tsx`
- [ ] Tests: `test_export_columns.py`, derivation unit tests

---

## What NOT to do

| Mistake | Instead |
|---------|---------|
| Subtype for person attribute | Victim/perp field |
| LLM extracts computable field | Built field + derive |
| CSV column without `derive_public_fields()` | One derivation function |
| Different values in API vs CSV | Same flat columns |
| Infer OCG from neighborhood | Explicit text only; use `unspecified` when vague |
| Force attacker/defender when unclear | null |
| Store typed facts only in prose | Typed JSON field |

---

## Additional resources

- Pending schema spec, column list, eval paths → [reference.md](reference.md)
- Worked examples → [examples.md](examples.md)
- Full pipeline eval gate → `.cursor/skills/eval-improvement-loop/SKILL.md`
- Eval CLI → `backend/eval/README.md`
