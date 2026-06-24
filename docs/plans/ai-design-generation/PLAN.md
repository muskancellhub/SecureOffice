# AI-Augmented Network Design Generation — Implementation Plan

> **Handoff doc for Claude Code.** Audience: an engineer (or Claude Code) implementing the feature. Author it assumes familiarity with the existing deterministic design pipeline documented in `docs/design-flow-architecture.md`.

---

## 0. TL;DR

Today the network design is produced by a **deterministic engine** (RF + capacity formulas → product scoring → BOM → topology → cost). It is correct but **context-blind**: two businesses with similar square footage / headcount / customer counts get an **identical design**, even when they are nothing alike.

> **The motivating bug:** a Restaurant/QSR (POS terminals, kitchen display systems, drive-thru, self-order kiosks, signage, heavy guest Wi-Fi) and a Convenience store (few endpoints, no guest Wi-Fi, light IoT) of **similar square footage** (~2,500–2,800 sqft per the dataset) currently receive the **same** AP count, the same switch, the same flat topology. They should not.

> **Input model:** `businessType` is a **closed pick-list of 8 types** — `Restaurant / QSR`, `Grocery store`, `Retail store`, `Office`, `Gym`, `Hotel`, `Convenience store`, `Warehouse`. The user always selects one of these (validated as an enum). Differentiation therefore operates on two axes: **across types** (driven by the seed defaults, Section 2.5) and **within a type** (driven by the user's specific field values overriding the seed). The AI never has to invent or map an unknown type.

**Goal:** add an **AI design layer** that makes the output **business-context-aware**, while keeping the deterministic engine as the **non-negotiable physics/capacity floor and validator**. The AI is *grounded in* the formulas (it is given them and must respect their outputs); it does **not** replace them.

**Chosen architecture (per product decision):**

- **Pattern:** Deterministic engine runs **first** to produce a baseline + hard floor. AI proposes a **context-aware design** on top. Deterministic engine then **re-validates** the AI output. AI can go *above* the floor with justification; it can never go *below* it.
- **Stack:** Backend, Python/FastAPI, **CrewAI** (reuse the existing `crew/` infra, `gpt-4.1-mini`, and `llm_guardrails`).
- **AI scope:** product/vendor selection, sizing & assumptions, topology & segmentation, and narrative/rationale.

---

## 1. Why deterministic-floor + AI-on-top (and not full AI)

| Property | Why it matters here |
|---|---|
| **Safety** | A hallucinated AP count that under-provisions a real deployment is a costly field failure. The calculator's coverage+capacity result is a physics floor that AI output is clamped to. |
| **Differentiation** | The thing customers actually need: a QSR ≠ a convenience store. The calculator can't express this from `sqft/employees/customers`; the seed defaults + an LLM reasoning over *business semantics* can. |
| **Explainability** | Sales/ops need a rationale. The deterministic numbers are auditable; the AI adds the "why this design for this business" narrative. |
| **Cost & latency** | Running the calculator first is free and instant; the LLM call is the only paid/slow step, and it's bounded by `max_tokens`. |
| **Backwards compatibility** | Output lands in the **same** JSONB shape (`calculator_result`, `bom`, `topology`, `drawio_xml`). Downstream (quotes/orders/workflow sync in `network_design_service.py`) is untouched. |

**"Trained on formulae" — engineering note.** The product ask was that the AI "be trained on the formulae but also reason from business requirements." Do **not** fine-tune a model for v1. Instead **ground** the model:

1. Run the deterministic calculator and **pass its full result into the prompt** (the floor + the intermediate RF/capacity numbers).
2. Give the agent a **`CalculatorTool`** so it can re-run the deterministic math with adjusted inputs and *see* the effect, rather than guessing.
3. Put the formula definitions + constants into a **knowledge block** (`FormulaKnowledgeTool`) so the model's reasoning is anchored to the real model, not its priors.

Fine-tuning is a possible **Phase 3** optimization once we have a labeled eval set; it is explicitly out of scope for v1.

---

## 2. Current-state anchors (read these first)

| Concern | File |
|---|---|
| Deterministic RF + capacity + cost engine | `frontend/src/calculator/calculator.ts`, `frontend/src/calculator/constants.ts`, `frontend/src/calculator/types.ts` |
| Rule-based product scorer | `frontend/src/suggestions/suggestionEngine.ts` |
| BOM + totals | `frontend/src/suggestions/bomBuilder.ts`, `frontend/src/suggestions/pipeline.ts` |
| Topology + diagram | `frontend/src/suggestions/topologyGenerator.ts`, `frontend/src/suggestions/drawioGenerator.ts` |
| Conversational intake (existing AI) | `backend/app/services/intake_chat_service.py`, `backend/app/routes/intake_chat.py` |
| CrewAI agents / tools / tasks | `backend/app/services/crew/agents.py`, `crew/tools.py`, `crew/tasks.py` |
| Guardrails (reuse) | `backend/app/services/llm_guardrails.py`, `backend/app/core/guardrail_policy.py` |
| Persistence (DO NOT break the JSONB contract) | `backend/app/services/network_design_service.py`, `backend/app/models/network_design.py`, `backend/app/schemas/designs.py` |
| Intake form → calculator mapping | `frontend/src/pages/BusinessIntakePage.tsx` (`onSubmitIntake`, `inferEnvironmentType`, `inferObstructionType`, `inferWifiStandard`) |

> **Decision point for the implementer — where does the deterministic calc run during AI generation?** It currently lives in **frontend TS**. Two options:
> - **(A) Port the calculator to Python** (`backend/app/services/network_calculator.py`) so the backend AI flow is self-contained. *Recommended* — keeps generation server-side, testable, and removes a frontend round-trip.
> - **(B) Have the frontend run the TS calculator and POST `calculator_result` into the AI endpoint.** Faster to ship, but the backend can't re-validate independently and the floor lives client-side.
>
> **This plan assumes (A).** If (B) is chosen, the `CalculatorTool` becomes a pass-through validator over the posted result and the "port" task is skipped — note the trade-off in the PR description.

---

## 2.5 The Business Requirements dataset (seed data — already in the repo)

A real, human-authored requirements matrix was provided and committed:

```
backend/app/data/business_profiles/business_requirements.xlsx   # source of truth (provenance)
backend/app/data/business_profiles/business_profiles.json       # generated runtime seed
backend/scripts/build_business_profiles.py                      # xlsx -> json converter (re-runnable)
```

**Shape:** 8 business types (columns) × **54 requirement attributes** (rows). For each business type it defines a full device/IoT inventory and operational posture — e.g. for `Restaurant / QSR`: `POS terminals: 4`, `Kitchen display systems: 4`, `Drive-thru systems: 2`, `Number of IP cameras: 8`, `Guest Wi-Fi users: 60`, `Need backup internet?: true`, `Downtime tolerance: Critical`, `Network ownership: Managed network services`, `Other SaaS tools: [Toast, QuickBooks]`. The attribute groups are: location/size, headcount, customers, connectivity (internet type/speed/backup/guest), endpoint inventory (laptops, desktops, tablets, phones), commerce/IoT inventory (POS, self-checkout, scanners, printers, KDS, kiosks, signage, sensors, cameras, robots, smart appliances, RFID), security infra (NVR, door access, alarm), SaaS stack, and ops posture (downtime tolerance, redundancy, managed-vs-self, install support).

**Why this matters: it makes differentiation largely deterministic.** This is the missing input that the old engine never had. The device inventory **sums into an actual device load** per business type, which feeds the capacity model — so two of the 8 types at the same sqft (e.g. a QSR vs a Convenience store) now diverge *before the AI even runs*, because their device profiles differ. The matrix also directly supplies segmentation and posture signals (cameras → camera VLAN, POS/payment → payment VLAN, `Need redundancy/backup` → cellular failover, `Network ownership` → managed-services BOM lines).

**Role split with the AI:**
- **Deterministic layer** consumes the matrix as **per-business-type defaults**: when a user leaves a field blank, fall back to the seed value for their `businessType`; aggregate the device inventory into `totalDevices`; derive `needsCellularBackup`, `redundancyEnabled`, `needsManagedServices`, guest-VLAN need directly from the seed.
- **AI layer** is grounded by the matrix (via `BusinessProfileKnowledgeTool`) and uses it to: (a) reason when the user's stated specifics **deviate** from the seed template for their chosen type (e.g. a QSR that reports 3× the typical POS count), (b) resolve ambiguity / fill gaps when the user leaves the free-text `specialNotes` with details the structured fields don't capture, (c) propose segmentation/topology, (d) select products, (e) write the rationale citing which seed assumptions were used vs overridden. `businessType` is always one of the 8 — no off-list mapping needed.

### Storage decision — *answering "should I save the Excel in the codebase?"*

**Yes — but the binary `.xlsx` is provenance, not the runtime dependency.** Best practice here:

| | Keep in repo? | Role |
|---|---|---|
| `business_requirements.xlsx` | **Yes**, under `backend/app/data/business_profiles/` | Human-editable source of truth; reviewers can open it; documents where the numbers came from. |
| `business_profiles.json` | **Yes** (generated, committed) | The actual runtime source of truth — diffable in PRs, no `openpyxl` needed at request time, loaded by the deterministic mapper + AI knowledge tool. |
| `build_business_profiles.py` | **Yes** | Re-runnable converter so the JSON is reproducible from the workbook. |

Do **not** load the `.xlsx` at runtime (binary parsing on a hot path, opaque diffs, an extra prod dependency). Add a CI test (`tests/test_business_profiles_seed.py`) that re-runs the converter and asserts the committed JSON is byte-identical, so the workbook and seed can never silently drift. If business users will edit these defaults frequently, a follow-up can promote the seed into an admin-editable DB table; the JSON seed is the right v1.

---

## 3. Target architecture

```
                     ┌─────────────────────────────────────────────────────────┐
                     │  POST /designs/ai-generate   (authenticated)            │
                     └───────────────────────────┬─────────────────────────────┘
                                                 │ BusinessProfile (enriched form)
                                                 ▼
        ┌────────────────────────────────────────────────────────────────────────┐
        │ AiDesignService.generate()                                             │
        │                                                                        │
        │  1. Enrich + validate profile (Pydantic)                               │
        │  2. DETERMINISTIC BASELINE  ── network_calculator.calculate(input) ──┐  │
        │       → floor: coverageAPs, capacityAPs, indoorAPsFinal, switchCount  │  │
        │  3. AI DESIGN CREW (CrewAI, gpt-4.1-mini)                            │  │
        │       tools: CalculatorTool, CatalogRetrievalTool,                   │  │
        │              FormulaKnowledgeTool, BusinessProfileKnowledgeTool       │  │
        │       → proposed: sizing deltas + product picks + topology + notes    │  │
        │  4. VALIDATION / CLAMP  ── re-run calculator on AI inputs ────────────┘  │
        │       enforce: APs ≥ floor, catalog items exist, schema valid,         │
        │       budget sane; else clamp to deterministic + flag                  │
        │  5. ASSEMBLE  → calculator_result, bom, topology, drawio_xml,          │
        │                 ai_rationale, assumptions                              │
        └───────────────────────────┬────────────────────────────────────────────┘
                                    │  same JSONB shape as today
                                    ▼
                     network_design_service.save_design()  (UNCHANGED contract)
```

**Core invariant:** `final.counts.indoorAPsFinal >= deterministic_floor.indoorAPsFinal` and `final.counts.switchCount >= deterministic_floor.switchCount`. The validator enforces this unconditionally.

---

## 4. How differentiation actually happens

The old engine couldn't tell a QSR from a Convenience store because its inputs collapsed the business into `sqft / users / devicesPerUser / throughputPerUser`. Now the **seed defaults already differentiate across the 8 types**, and the AI differentiates further by reasoning about **business semantics → engineering levers**. Concretely, the AI is allowed to move these (each clamped/validated):

| Business signal | Engineering lever the AI may adjust | Example: QSR vs Convenience store |
|---|---|---|
| Transaction/device density (POS, KDS, tablets, handhelds) | `devicesPerUser`, `throughputPerUserMbps`, `concurrencyFactor` → drives **capacityAPs** | QSR: POS+KDS+kiosks+signage → higher capacity APs. Convenience: few endpoints. |
| Payment-uptime criticality (PCI, drive-thru) | `needsCellularBackup`, redundancy, network segmentation | QSR: `Downtime tolerance: Critical` → cellular failover + isolated payment VLAN. Convenience: `Medium`. |
| Guest Wi-Fi intensity | guest VLAN, captive portal node in topology, extra capacity headroom | QSR: 60 guest users. Convenience: `Guest Wi-Fi required?: No`. |
| Environment / obstruction nuance | `environmentType`, `obstructionType` (beyond the crude `businessType` lookup) | Kitchen + freezer walls → denser obstruction in part of the floor. |
| Operational IoT (kitchen sensors, cameras) | extra BOM categories, topology nodes/VLAN | QSR: KDS + kitchen sensors segment. Convenience: 8 cameras, light IoT. |
| Vendor / budget posture | product scoring weights, `preferCheapest`, preferred vendor | unchanged mechanism, AI-justified picks |

The AI must **justify each deviation from the deterministic baseline** in `ai_rationale`, and every numeric change is re-validated by re-running the calculator.

---

## 5. Data-model changes

### 5.1 Enriched business profile (input)

The current form (`ALLOWED_EXTRACT_KEYS` in `guardrail_policy.py`) captures only: `businessType, locations, squareFootage, employees, peakCustomers, avgDailyCustomers`. **The new field set is defined by the dataset (Section 2.5)** — the 54 attributes in `business_profiles.json` are the canonical list. Do not invent fields; mirror the seed.

Implementation rules:
- **Every dataset attribute becomes an optional, nullable profile field** (so existing flows keep working). The user only types what they know; **unfilled fields fall back to the seed value for their `businessType`**. This default-from-seed behavior is what makes the design business-aware even with sparse input.
- Extend `ALLOWED_EXTRACT_KEYS` in `core/guardrail_policy.py` to cover the new keys, keeping the whitelist + sanitize discipline. Keep `ALLOWED_BUSINESS_TYPES` aligned with `business_profiles.json["businessTypes"]` (the 8 types). Add a CI test that asserts these stay in sync with the seed.
- Surface the high-signal fields in `BusinessIntakePage.tsx` with **progressive disclosure keyed to `businessType`** (e.g. show kitchen/drive-thru/KDS only for `Restaurant / QSR`, self-checkout/smart-shelves for `Grocery store`) — use the seed to decide which fields are relevant (non-zero for that type). Let the intake LLM extract them too (update `build_intake_agent` + `_sanitize_extracted`).
- Add a free-text `specialNotes` field (sanitized via `llm_guardrails`, fed to the AI as untrusted context) for anything the structured fields don't capture.

### 5.2 New persisted artifacts (output)

`network_designs` already has 14 JSONB columns. **Reuse, don't migrate** where possible:

- `metadata_json` → add `aiGenerated: true`, `aiModel`, `aiPromptVersion`, `floorSnapshot` (the deterministic floor counts), `clampApplied: bool`.
- **New column** `ai_rationale_json` (JSONB, nullable) — the structured rationale + per-decision notes. Add via the project's runtime-migration mechanism (`backend/app/core/runtime_migrations.py`) consistent with how other JSONB columns were added.
- `assumptions_json` continues to hold human-readable assumption strings (now AI-authored + deterministic).

> Keep `calculator_input_json`, `calculator_result_json`, `bom_json`, `topology_json`, `drawio_xml` **exactly** as today so `save_design`, quote/order sync, and the frontend detail page need no changes.

---

## 6. Backend components to build

All under `backend/app/`. Follow existing patterns (service + schema + route + crew tool).

### 6.1 `services/network_calculator.py` *(if Option A)*
Faithful Python port of `frontend/src/calculator/calculator.ts` + `constants.ts`. Pure functions, no I/O. **Must be numerically identical** to the TS version — add a parity test (Section 9).

### 6.2 `services/ai_design_service.py`
Orchestrator (`AiDesignService.generate(profile, *, current_user, catalog) -> GeneratedDesign`). Implements the 5-step flow in Section 3. Owns the **validation/clamp** logic and the **deterministic floor** invariant. Reuses `llm_guardrails` for input sanitization and the `audit` logger.

### 6.3 `services/crew/design_generation_agent.py` (or extend `crew/agents.py`)
A new CrewAI agent `build_generative_design_agent()`:
- **role:** "Generative Network Design Architect"
- **backstory:** grounded in the SecureOffice2 formulas; must respect the deterministic floor; must differentiate by business type; must output strict JSON (same discipline as `build_intake_agent`).
- **tools:** the four below.
- **llm:** reuse `_build_llm()` but consider `temperature≈0.2` (some reasoning variance is desirable for context adaptation; still low for stability) and a higher `max_tokens` for the design + rationale.

### 6.4 Crew tools (`crew/tools.py` additions)
- `CalculatorTool` — wraps `network_calculator.calculate()`; lets the agent test "if I raise devicesPerUser to X, how many APs?" Returns the full result.
- `CatalogRetrievalTool` — reuse the existing retriever path (`_retrieve_catalog` / the local retriever) so picks come from the **real catalog**, not invention. Same thread-local DB/tenant context mechanism already in `crew/tools.py` (`set_crew_context`).
- `FormulaKnowledgeTool` — returns the formula + constant reference (the "trained on formulae" grounding).
- `BusinessProfileKnowledgeTool` — returns the per-business-type profile from `business_profiles.json` (Section 2.5): device inventory, segmentation/posture signals, SaaS stack. This **is** the cross-business-type knowledge (QSR vs Convenience store vs Office, etc.); it's already real data, no need to invent heuristics. The tool reads the seed via the loader in 6.0.

### 6.0 `services/business_profiles.py` (seed loader)
Small module that loads `app/data/business_profiles/business_profiles.json` once (module-level cache), exposing `get_profile(business_type) -> dict`, `list_business_types()`, and helpers used by the deterministic mapper:
- `default_field(business_type, attribute)` — seed fallback for a blank user field.
- `aggregate_device_load(profile) -> {totalDevices, byCategory}` — sums the endpoint + IoT inventory rows into the device count that feeds the capacity model (see Section 7, step 1).
- `derive_posture(profile) -> {needsCellularBackup, redundancyEnabled, needsManagedServices, needsGuestVlan, needsCameraVlan, needsPaymentVlan}` — maps seed attributes to engineering flags.

### 6.5 `schemas/ai_design.py`
Pydantic request/response:
- `AiDesignRequest` — the enriched `BusinessProfile`.
- `GeneratedDesignResponse` — `calculatorResult`, `bom`, `topology`, `drawioXml`, `assumptions`, `aiRationale`, `floorSnapshot`, `clampApplied`, `warnings`. Mirror the alias/camelCase conventions in `schemas/designs.py`.
- A **strict internal schema** for the LLM's raw JSON output (validated/sanitized before use — never trust raw model output).

### 6.6 `routes/designs.py` (new endpoint)
`POST /designs/ai-generate` (authenticated, tenant-scoped like the rest of `designs.py`). Calls `AiDesignService`, returns `GeneratedDesignResponse`. The frontend can then auto-save via the existing `POST /designs` path, unchanged.

### 6.7 Guardrails & limits
- Add `/designs/ai-generate` to `LLM_RATE_LIMITS` in `guardrail_policy.py` (e.g. `(10, 60)`; it's authenticated so can be looser than `/intake/chat`).
- Run `detect_injection` / `sanitize_user_text` on `specialNotes` and any free text before it enters the prompt (reuse `intake_chat_service.py` patterns).
- Treat catalog/profile text as **untrusted reference data** in the prompt (same indirect-injection framing already used in `crew/tasks.py`).

---

## 7. The generation flow, step by step (for `AiDesignService.generate`)

1. **Validate + enrich** the `BusinessProfile` (Pydantic). **Fill blanks from the seed**: for any unset attribute, use `business_profiles.get_profile(businessType)` (Section 6.0). Then derive the base `NetworkCalculatorInput` as `BusinessIntakePage.onSubmitIntake` does today (port `inferEnvironmentType/Obstruction/WifiStandard`), **plus** the new richer inputs the seed unlocks: set `totalDevices`/`devicesPerUser` from `aggregate_device_load()` (this is the differentiation driver — QSR's POS+KDS+kiosks+signage load ≫ a Convenience store's), and set `needsCellularBackup / redundancyEnabled / needsManagedServices / guest+payment+camera VLAN` from `derive_posture()`. This step alone already differentiates business types deterministically; the AI then refines.
2. **Deterministic baseline:** `floor = calculate(baseInput)`. Persist `floor.counts` as the snapshot/invariant.
3. **AI proposal:** kick off the crew with: the profile, `floor` (full result), catalog access (tool), formula reference (tool), business-type heuristics (tool). Instruct it to return strict JSON:
   ```json
   {
     "sizing": { "devicesPerUser": n, "throughputPerUserMbps": n,
                 "concurrencyFactor": n, "redundancyEnabled": bool,
                 "needsGateway": bool, "needsCellularBackup": bool,
                 "indoorAPsFinal": n, "switchCount": n },
     "productSelection": { "apItemId": "...", "switchItemId": "...",
                           "gatewayItemId": "...|null", "cellularItemId": "...|null" },
     "topology": { "segments": [ { "name": "Payment VLAN", "nodes": [...] }, ... ] },
     "rationale": { "summary": "...", "decisions": [ { "lever": "...", "change": "...", "why": "..." } ] },
     "assumptions": [ "..." ]
   }
   ```
4. **Validate + clamp:**
   - Re-run `calculate()` with the AI's sizing inputs → recomputes costs deterministically (AI never sets prices).
   - **Enforce floor:** `indoorAPsFinal = max(ai.indoorAPsFinal, floor.indoorAPsFinal)`; same for switches. Record `clampApplied` if the AI was below floor.
   - **Catalog existence:** every `*ItemId` must resolve in the catalog (`find_product_by_id_or_legacy` lives in `services/catalog_unification.py`); unknown → fall back to the rule-based `suggestProducts` pick for that slot + warning.
   - **Schema/budget sanity:** totals within a configurable band of the deterministic estimate; else flag for human review (not a hard fail).
5. **Assemble** the canonical artifacts: build `bom` (reuse `bomBuilder` logic — port or call), `topology` + `drawio_xml` (reuse `topologyGenerator`/`drawioGenerator`, extended to honor AI segments), `calculator_result` from the final validated `calculate()`, plus `ai_rationale` and `assumptions`. Return in the existing JSONB shape.

**Fallback:** if the crew errors, times out, or returns unparseable JSON (mirror `intake_chat_service` `_parse_json_safely`), return the **pure deterministic design** with `metadata.aiGenerated=false` and a warning. The feature must **degrade to today's behavior**, never block a design.

---

## 8. API contract

```
POST /designs/ai-generate
Auth: required (tenant-scoped, same as /designs)
Body: AiDesignRequest (enriched BusinessProfile)
200:  GeneratedDesignResponse {
        calculatorInput, calculatorResult, bom, topology, drawioXml,
        assumptions[], aiRationale{}, floorSnapshot{}, clampApplied, warnings[]
      }
4xx:  validation errors (Pydantic)
5xx:  never on LLM failure — degrade to deterministic 200 with warnings
```

Frontend: `NetworkDesignBuilderPage.tsx` gets a "Generate with AI" action that calls this, populates the builder, then the existing debounced auto-save (`POST /designs`) persists it unchanged.

---

## 9. Testing & evaluation plan

This is the part that proves the feature works. **Treat differentiation as a testable property.**

### 9.1 Unit / parity
- **Calculator parity** (if Option A): Python `calculate()` matches TS `calculateNetworkEstimate()` on a fixture matrix (golden JSON shared between `frontend/src/calculator/__tests__` and a new `backend/tests/test_network_calculator_parity.py`).
- **Floor invariant:** property test — for random profiles, `final.indoorAPsFinal >= floor.indoorAPsFinal` and switch equivalent. Never violated.
- **Catalog grounding:** every selected item id resolves in the catalog; fabricated ids fall back.

### 9.2 Differentiation eval (the cross-business-type test)
Golden business pairs that share `sqft/employees/customers` but differ in type/context. Assert the **designs differ** on the expected levers:

| Pair | Must differ on |
|---|---|
| Restaurant/QSR vs Convenience store @ similar sqft | AP count, cellular backup present, payment VLAN in topology, guest-Wi-Fi headroom |
| Warehouse vs office @ 12,000 sqft | obstruction/environment, AP spacing, switch count |
| Hotel vs gym @ 20,000 sqft | guest VLAN, per-floor segmentation, capacity sizing |

Implement as `backend/tests/test_ai_design_differentiation.py`. Because LLM output varies, assert on **structural/directional** properties (e.g. "QSR cellular backup == true AND QSR APs ≥ Convenience-store APs"), not exact numbers. Run against a recorded/mocked LLM in CI; nightly against the live model.

### 9.3 Guardrail / red-team
Extend `backend/tests/test_rag_redteam.py` / `test_llm_guardrails.py`: prompt-injection in `specialNotes`, attempts to drive APs below floor, attempts to inject non-catalog products, PII in profile. All must be neutralized.

### 9.4 Cost / latency budget
Log tokens + latency per generation (audit). Target a per-call ceiling; cache by hash of the normalized profile so identical inputs don't re-bill.

---

## 10. Rollout / phasing

- **Phase 1 — Floor + AI sizing & products (behind a flag).** Port calculator (or use Option B), build the service/agent/tools, enforce floor + catalog grounding, return JSON. AI influences `sizing` + `productSelection` only; topology stays deterministic. Ship the differentiation eval. This alone fixes the "same design for different business types" bug.
- **Phase 2 — Topology/segmentation + rationale.** Let AI propose VLAN segments and the narrative; extend `topologyGenerator`/`drawioGenerator` to render AI segments. Add `ai_rationale_json`.
- **Phase 3 (optional) — Specialize the model.** With the eval set + logged generations as data, consider fine-tuning or a distilled smaller model for cost/latency. Only if metrics justify it.

Gate the whole feature behind a tenant/feature flag so it can be A/B'd against the deterministic-only path.

---

## 11. Risks & open questions

- **LLM non-determinism vs reproducible quotes.** Same input → possibly different design. Mitigate with low temperature + input-hash caching; decide whether a saved design is "frozen" on first generation (recommended: yes — store the generation, don't regenerate on reload).
- **Catalog coverage.** AI can only pick what exists; thin catalogs force fallbacks. The rule-based scorer remains the safety net per slot.
- **Cost at scale.** Auto-save fires on a debounce today — do **not** auto-trigger AI generation on every keystroke. AI generation is an explicit user action.
- **Option A vs B** (Section 2) — pick before starting; it changes the task list.
- **Where do business-type heuristics live?** Start as code/JSON (`BusinessProfileKnowledgeTool`); promote to a small retrieval store if they grow.
- **Numeric authority.** AI never sets prices or final counts directly — it proposes inputs; the deterministic engine computes the authoritative outputs. Keep this boundary crisp.

---

## 12. Concrete task checklist for Claude Code

- [x] **Seed data committed:** `business_requirements.xlsx`, generated `business_profiles.json`, and `scripts/build_business_profiles.py` (done in this handoff).
- [x] `tests/test_business_profiles_seed.py`: re-run converter, assert committed JSON matches (no drift); assert `ALLOWED_BUSINESS_TYPES` == seed `businessTypes`.
- [x] `services/business_profiles.py` seed loader: `get_profile`, `default_field`, `aggregate_device_load`, `derive_posture` (Section 6.0).
- [x] Decide **Option A (port calc to Python)** vs **B**: chose **Option A**. Also discovered the BOM + topology/draw.io generators **already exist server-side** (`network_bom_service.py`, `network_topology_service.py`) — so only the calculator needed porting; assembly reuses those (the TS pipeline port in §7.5/checklist is unnecessary).
- [x] *(A)* `services/network_calculator.py` + `backend/tests/test_network_calculator_parity.py` (numerically identical to the TS golden fixtures).
- [x] Extend `core/guardrail_policy.py`: `/designs/ai-generate` rate limit added; `ALLOWED_BUSINESS_TYPES` kept synced to seed (asserted by the seed-drift test). `ALLOWED_EXTRACT_KEYS` left scoped to the intake-chat surface — the AI design profile validates via `schemas/ai_design.py`, so it does not need the 54-key expansion (which is tied to the deferred intake-LLM extraction work).
- [x] `schemas/ai_design.py`: `AiDesignRequest`, `GeneratedDesignResponse`, strict `AiDesignProposal` LLM-output schema.
- [x] `services/crew/` : `build_generative_design_agent()` + `CalculatorTool`, `CatalogRetrievalTool`, `FormulaKnowledgeTool`, `BusinessProfileKnowledgeTool` (in `crew/design_tools.py`).
- [x] `services/ai_design_service.py`: orchestration, floor enforcement, clamp, fallback, audit.
- [x] `routes/designs.py`: `POST /designs/ai-generate` (authenticated, tenant-scoped).
- [x] Assembly reuses `NetworkBomService` (catalog-grounded BOM) + `NetworkTopologyService` (topology + draw.io) — no TS port needed.
- [ ] `BusinessIntakePage.tsx`: new context fields (progressive disclosure) + intake-LLM extraction of them. *(form already collects all 54 fields; intake-LLM extraction deferred)*
- [x] `NetworkDesignBuilderPage.tsx`: "Generate with AI" action → calls `/designs/ai-generate` → fills builder → existing auto-save persists (incl. `aiRationale`).
- [x] *(Phase 2)* `ai_rationale_json` column via `runtime_migrations.py` (+ model + save path); render rationale **and VLAN segments** in `DesignDetailPage.tsx`.
- [x] **(Phase 2) AI VLAN segmentation:** `AiDesignProposal.topology.segments`; deterministic baseline VLANs (payment/camera/guest/IoT/corporate/management) derived from the nodes present, AI renames/justifies; attached to `topology_json.segments` + nodes tagged. (No draw.io re-render — segments are structured data the detail page renders.)
- [x] Tests: parity, floor-invariant property test, **differentiation eval**, red-team extensions, **segmentation + rationale-persistence tests**. *(cost/latency logging: per-call audit emitted; token metering deferred)*
- [ ] Feature-flag the path; verify deterministic fallback on LLM failure. *(fallback verified + tested; tenant/feature flag gating still TODO)*

---

## 13. Acceptance criteria

1. A Restaurant/QSR and a Convenience store (or any two of the 8 types) with identical sqft/headcount/customers produce **materially different** designs (AP count and/or topology and/or cellular backup), and the difference is explained in `ai_rationale`. The differentiation must hold **even with sparse user input**, because blank fields fall back to the per-business-type seed (Section 2.5).
2. No generated design ever falls **below** the deterministic coverage+capacity floor (enforced + tested).
3. Every BOM item resolves to a **real catalog product**; no fabricated SKUs.
4. LLM failure/timeout/garbage output **degrades gracefully** to the current deterministic design — never a 5xx, never a blocked save.
5. Output is stored in the **existing JSONB contract**; quotes/orders/workflow sync and the design detail page work unchanged.
6. Prompt-injection and "drive APs below floor" attempts are neutralized (red-team tests pass).
