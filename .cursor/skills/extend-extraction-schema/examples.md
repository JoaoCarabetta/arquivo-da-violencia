# Worked Examples

Illustrative scenarios — see [SKILL.md](SKILL.md) for the main workflow.

---

## Example 1: Victim security agent off duty (Step 5)

**Scenario:** "Policial civil morto em Copacabana; estava de folga."

| Slot | Decision |
|------|----------|
| `IdentifiableVictim` | `is_security_force=true`, `security_agent_type="PC"`, `security_agent_on_duty=false` |
| `homicide_dynamic` | No — job/on-duty is not event dynamics |
| `event_subtype` | Not `police_victim` subtype — use victim fields |

```json
"scoring": {
  "required_fields": [
    "victims.identifiable_victims.0.is_security_force",
    "victims.identifiable_victims.0.security_agent_type",
    "victims.identifiable_victims.0.security_agent_on_duty"
  ]
}
```

---

## Example 2: Politician victim (Step 5 + 7)

**Scenario:** "Vereador João Silva (PT) foi executado na noite de ontem."

**JSON (per victim):**

```python
political_role=PoliticalRole(
    is_politician_or_candidate=True,
    status="elected",
    office="vereador",
    party="PT",
)
```

**Ex-officeholder:** "Ex-vereador Maria Costa (PL)" → `status="former_elected"`, `office="vereador"` (not `"ex-vereador"`).

**derive_public_fields:**

```python
politician_or_candidate_victim=True
victim_political_status="elected"
victim_political_office="vereador"
victim_political_party="PT"
```

**Step 7:** add columns to export + `EventDetailView` (summary from flat fields; per-victim detail from `merged_data`).

Multi-victim: only the politician victim gets `political_role`; event flag true if any victim has it.

---

## Example 3: Criminal group territorial dispute (Step 5 + 7)

**Scenario:** "Homem morto em confronto entre Comando Vermelho e milícia pelo controle do Morro X."

```python
criminal_group_context=CriminalGroupContext(
    connected=True,
    groups=["Comando Vermelho", "milícia"],
    activity="territorial-dispute",
    group_attacked="milícia",  # only if text explicitly says who was attacked
    activity_description=None,
)
```

**Do not extract** if article only says "área dominada pelo tráfico" without linking this death.

**Vague but connected:** "Suspeita de ligação com facção" without activity type → `connected=True`, `activity="unspecified"`.

**derive_public_fields:**

```python
criminal_group_connected=True
criminal_group_activity="territorial-dispute"
criminal_groups="Comando Vermelho; milícia"
criminal_group_attacked="milícia"  # or null if unclear
```

Activity priority example: text mentions both territory and revenge → choose `territorial-dispute`.

---

## Example 4: Police operation + OCG (parallel dimensions)

**Scenario:** "Dois suspeitos do CV morreram durante Operação Verão da PM."

```python
police_operation_context=PoliceOperationContext(
    connected=True,
    responsible_force="PM",
    targeted_armed_groups=True,
    operation_name="Operação Verão",
)
criminal_group_context=CriminalGroupContext(
    connected=True,
    groups=["Comando Vermelho"],
    activity=None,  # death during op, not faction dispute
)
```

`event_subtype` may be `intervencao_policial` — separate from operation context fields.

---

## Example 5: Off-duty police perpetrator (Step 5)

**Scenario:** "Policial militar, fora de serviço, atirou e matou vizinho após briga."

```python
# perpetrator side
identifiable_perpetrators=[IdentifiablePerpetrator(
    is_security_force=True,
    security_agent_type="PM",
    security_agent_on_duty=False,
    ...
)]
homicide_dynamic.off_duty_police_perpetrator=True
homicide_dynamic.off_duty_police_context="genuine_reaction"  # if text supports
```

Distinct from `police_operation_context.connected` (no official operation).

Moonlighting as bouncer → `off_duty_police_context="moonlighting"`.
Acting for facção → `"criminal_organization"`.

---

## Example 6: Built field (Step 4)

**Scenario:** `politician_or_candidate_victim` on unique_event.

**Step 4 (preferred):** derive from `victims.identifiable_victims[].political_role` — no separate LLM field.

```python
def _any_politician_victim(event: ViolentDeathEvent) -> bool | None:
    flags = [
        v.political_role.is_politician_or_candidate
        for v in event.victims.identifiable_victims
        if v.political_role is not None
    ]
    if not flags:
        return None
    return any(flags)
```

---

## Example 7: Activity types quick reference

| Activity | Text cue | Extra field |
|----------|----------|-------------|
| `informant-elimination` | delator, X9, informante | — |
| `debt-enforcement` | narco-débito, dívida de drogas | — |
| `retaliatory` | represália, vingança | optional `group_attacked` |
| `collateral` | fogo cruzado, bala perdida in faction fight | explicit wording only |
| `protest` | bloqueio, reação a política, violência anti-estado | `policy_trigger` |
| `unspecified` | connected but mechanism unclear | `activity_description` optional |

---

## Example 8: Already captured (Step 2 — done)

**Ask:** "Record firearm as method."

**Answer:** `homicide_dynamic.method = "Arma de fogo"`. No new field.

---

## Anti-patterns ✗

| Bad | Good |
|-----|------|
| Subtype `police_victim` | Victim `is_security_force` + agent fields |
| Infer PCC from neighborhood | `connected=null` or omit |
| CSV column hand-coded in frontend only | `derive_public_fields()` + API |
| `group_attacked` from shootout chronology alone | null unless explicit |
| `office="ex-vereador"` | `status="former_elected"`, `office="vereador"` |
