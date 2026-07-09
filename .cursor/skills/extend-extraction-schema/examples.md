# Worked Examples

Illustrative scenarios — see [SKILL.md](SKILL.md) for the main workflow (Steps 1–6).

## Example 1: LLM-extracted victim field (Step 4)

**Scenario:** capture that an individually described victim is a civil police officer killed off duty.

**Step 1:** recording homicide incident information — in scope.

**Step 2:** `is_security_force` exists; `security_agent_type` and `security_agent_on_duty` do not.

**Step 3:** cannot build type/on-duty reliably from `is_security_force` alone — needs LLM (Step 4).

### Placement

| Slot | Decision |
|------|----------|
| `IdentifiableVictim` | Yes — `security_agent_type`, `security_agent_on_duty` |
| `UnidentifiedVictimGroup` | N/A (victim individually described) |
| `IdentifiablePerpetrator` | N/A (author unknown) |
| `UnidentifiedPerpetratorGroup` | Optional if text only says "autores fugiram" |
| `homicide_dynamic` | **No** — job/on-duty is not event dynamics |

Use victim fields — not a new `event_subtype` for "police victim."

### Eval snippet

```json
"scoring": {
  "required_fields": [
    "victims.identifiable_victims.0.is_security_force",
    "victims.identifiable_victims.0.security_agent_type",
    "victims.identifiable_victims.0.security_agent_on_duty"
  ]
}
```

**Step 6:** ask if portal should show "policial vitimado" — do not implement here.

---

## Example 1b: Unidentified victim group (Step 4)

**Scenario:** "Dois policiais foram mortos em emboscada" — group only, no names.

Use `unidentified_groups` with `is_security_force: true`. Do not put `security_agent_type` / `security_agent_on_duty` on the group unless the text describes the whole group that way.

---

## Example 2: Built field from existing extraction (Step 3)

**Scenario:** expose `any_security_force_party: bool` on `ViolentDeathEvent` root — true if **any** victim or perpetrator (identifiable or group) has `is_security_force=true`.

**Step 2:** `is_security_force` already extracted per party.

**Step 3:** preferred — new JSON field + population rule; **no** LLM prompt for `any_security_force_party`.

Similar existing pattern: `derive_security_force_involved()` at persist time.

---

## Example 3: Already captured (Step 2 — done)

**User ask:** "Record that the victim was killed by firearm."

**Answer:** `homicide_dynamic.method` = `"Arma de fogo"`. No new field. Improve prompt/eval only if extraction misses it.

---

## Example 4: Wrong skill (Step 1)

**User ask:** "Add a filter on the map for off-duty police victims."

→ **Wrong skill.** That is portal UI, not extraction JSON. Tell the user and stop (or note for a frontend workflow after a field exists).

---

## Example 5: `intervencao_policial` vs police victim

| Article | `event_subtype` (existing field) | Victim fields (this skill) |
|---------|----------------------------------|----------------------------|
| "Suspeito neutralizado em operação da PM" | `intervencao_policial` | victim usually not police |
| "Policial civil morto em Copacabana" | `simples` (or other) | `is_security_force`, `security_agent_type`, … |

Direction matters: police as author vs police as victim.

---

## Anti-pattern: person attribute as subtype ✗

> "Add subtype `police_victim` for homicides where the victim is a police officer"

Use victim fields from Example 1 instead.
