# Agentic AI Integration Plan — eqMonitoring2

**Status:** Draft for review
**Date:** 2026-08-13
**Inference:** Local models via LM Studio (`http://localhost:1234/v1`, OpenAI-compatible)
**Primary model:** `google/gemma-4-26b-a4b`
**Hardware:** NVIDIA RTX 6000 Ada, 48 GB VRAM

---

## 1. Executive summary

All inference runs locally. Nothing leaves the machine — which resolves the data-sovereignty question outright for a government disaster-management platform, and it is the reason this design is *better* here than a hosted frontier API, not merely cheaper.

The plan is built on **measured behaviour of the actual models on the actual box**, not on assumptions. That measurement produced one finding that inverts standard practice and would have silently shipped garbage into production:

> **Grammar-constrained structured output (`response_format: json_schema`) is catastrophically broken on this Gemma build. Native tool calling on the same model is flawless.**

Every structured extraction in this plan therefore routes through the **tool-calling interface**, never through `response_format`. §2 shows the evidence.

The second consequence of running a ~4B-active MoE rather than a frontier model: **autonomy lives in the harness, not the model.** We do not hand the model an open-ended agent loop and hope. We give it small, well-bounded decisions inside a deterministic orchestrator. That suits disaster response anyway — predictability beats cleverness when an operator is acting on the output.

---

## 2. Measured baseline

Probed 2026-08-13 against the live LM Studio server. **These numbers are the justification for every design decision below; re-run them after any model or LM Studio upgrade.**

### 2.1 Available models

| Model | Role | Measured latency |
|---|---|---|
| `google/gemma-4-26b-a4b` | **Primary** — extraction, briefs, tool selection | 2.7–3.3 s |
| `qwen/qwen3.5-9b` | Secondary / cross-check | 2.9–9.5 s |
| `deepseek/deepseek-v4-flash` | Batch only — too slow interactive | 12–97 s |
| `nvidia/nemotron-3-nano` | Routing / classification (untested — Phase 0 task) | — |
| `zai-org/glm-4.6v-flash` | Vision (unused for now) | — |
| `zai-org/glm-4.7-flash` | Spare | — |
| `text-embedding-nomic-embed-text-v1.5` | Embeddings — **now unused**, see §6.3 | 768 dims |

### 2.2 The structured-output trap

Same model, same prompt, same query — *"M5 and above within 100km of Quetta over the last decade"*. Expected `mag=5, place=Quetta, radius=100, years=10`.

| Method | Result |
|---|---|
| `response_format: json_schema`, weak prompt | `{"min_magnitude": 0.5, "radius_km": 1e-0, "years_back": 60}` — **all wrong** |
| `response_format: json_schema`, explicit prompt | `{"min_magnitude": 4.0, ...}` — magnitude still wrong |
| `response_format: json_schema`, repeat runs | `{"min_magnitude": 0, "place": "},{", "radius_km": 0, "years_back": 6432876487654321}` — **total collapse** |
| **Free text**, 3 runs | `{"min_magnitude": 5, "radius_km": 100, ... 10}` — **3/3 correct, deterministic** |
| **Native tool calling** | `search_events{"min_magnitude":5,"place":"Quetta","radius_km":100,"years_back":10}` — **perfect** |

Read that `place: "},{"` carefully. The grammar is forcing token choices that destroy semantic content while still emitting schema-valid JSON. **A JSON validator would have passed every one of those broken outputs.** This is the single most important operational fact in this document.

### 2.3 Tool calling — the capability the plan rests on

| Model | Correct tool + args | Correctly abstains when no tool needed |
|---|---|---|
| `gemma-4-26b-a4b` | ✅ all 4 args exact, 3.3 s | ✅ answered "Paris" directly, no spurious call |
| `qwen3.5-9b` | ✅ all 4 args exact, 9.5 s | ✅ |

Both selected the right tool, extracted every argument correctly, and — importantly — **did not fire a tool when none was warranted**. Spurious tool calls are the usual small-model failure; these models do not exhibit it on a two-tool surface.

### 2.4 Other measured facts

- **Prompt quality dominates.** Weak → explicit system prompt moved Gemma from 1/4 to 3/4 fields correct. Prompt engineering is not polish here; it is the main lever.
- **`temperature: 0` is not deterministic** under grammar constraint (MoE routing varies). Free-text generation *was* deterministic across 3 runs. Never assume reproducibility — assert it in evals.
- **Thinking models strand their answer.** `qwen3.5-9b` and `deepseek-v4-flash` returned **empty `content`** with the real answer in `reasoning_content`. Any client that reads only `content` gets an empty string and no error.

---

## 3. Core principles

**P1 — The model never computes seismology.** Every number an operator sees traces to a deterministic function in `src/eqmon/`. The model selects tools, sequences them, and writes prose. It does no arithmetic. A hallucinated casualty figure misdirects a response; it does not degrade gracefully.

**P2 — AI is additive, never load-bearing.** Stop LM Studio and every existing endpoint works exactly as today. No AI call sits on the critical path of ingest, intensity, or impact.

**P3 — Tool calling is the structured-output mechanism.** Never `response_format: json_schema`. Measured, §2.2.

**P4 — Schema-valid ≠ correct.** Validation must be semantic (range checks, source-text cross-reference), never merely structural.

**P5 — Autonomy lives in the harness.** Deterministic orchestration with the model making bounded decisions at named points. No open-ended loops.

**P6 — Local inference is free at the margin.** No per-token cost changes the economics: retry aggressively, sample multiple times and vote, cross-check with a second model. Techniques that are prohibitive on a metered API are routine here. **Spend compute to buy reliability.**

---

## 4. Architecture

```
┌──────────────────────────────────────────────────────────┐
│  FastAPI  src/eqmon/api.py — existing 18 endpoints       │
│  UNCHANGED. New AI routes added alongside.               │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│  src/eqmon/ai/                                           │
│                                                          │
│   client.py    LM Studio client, retries, content-or-    │
│                reasoning_content extraction, queue       │
│   registry.py  model roster + capability routing         │
│   tools.py     tool schemas ↔ domain functions           │
│   orchestr.py  deterministic DAGs, bounded model steps   │
│   validate.py  semantic validation + repair loop         │
│   ground.py    numeric grounding guard                   │
│   audit.py     every call persisted                      │
│   evals/       golden set + runner                       │
└────────────────────────┬─────────────────────────────────┘
                         │ calls, never bypasses
┌────────────────────────▼─────────────────────────────────┐
│  Pure domain modules (unchanged)                         │
│  analytics · aftershock · impact · intensity · contours  │
│  · exposure · events/repo                                │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│  PostGIS: seismic_event · admin_boundary · tectonic_zone │
└──────────────────────────────────────────────────────────┘
```

`src/eqmon/ai/` contains **zero seismology**. If a reviewer finds a formula there, the review fails.

### 4.1 Why the existing code is ready

The domain modules are already the right shape for tools — this is not luck, it is the existing design discipline paying off:

| Module | Docstring says | Why it matters |
|---|---|---|
| `analytics.py` | *"No DB or HTTP dependencies so each is unit-testable"* | Pure functions = trivially wrappable, trivially testable |
| `aftershock.py` | *"Pure NumPy — no DB dependency"* | Same |
| `impact.py` | one entry point `compute_event_impact(conn, event, grid)` | One tool, one call |
| `exposure.py` | documents the ARC vocabulary boundary at its edge | The pattern to copy for tool schemas |

23 test files already cover these. The tool layer is a wrapper, not a rewrite.

### 4.2 The client contract

`client.py` must handle three measured realities:

```python
def extract_text(choice: dict) -> str:
    """content, or reasoning_content when a thinking model leaves content empty.

    Measured: qwen3.5-9b and deepseek-v4-flash return an empty `content`
    with the real answer in `reasoning_content`. Reading only `content`
    yields an empty string and no error — a silent failure.
    """
    msg = choice["message"]
    return (msg.get("content") or "").strip() or (msg.get("reasoning_content") or "").strip()
```

Plus: a **single-flight queue** (one GPU — concurrent requests thrash), per-call timeout by model tier, and a circuit breaker that disables AI routes cleanly if LM Studio is down.

### 4.3 VRAM budget — 48 GB

Rough Q4 footprints; measure and pin during Phase 0:

| Resident | ~VRAM |
|---|---|
| `gemma-4-26b-a4b` (primary) | ~15 GB |
| `qwen3.5-9b` (cross-check) | ~6 GB |
| `nemotron-3-nano` (routing) | ~2 GB |
| `nomic-embed-text-v1.5` | ~0.5 GB |
| KV cache + headroom | remainder |

All four co-resident with room to spare. **Disable LM Studio's JIT auto-unload TTL for these** — an idle-unload mid-incident means a 30-second model load exactly when latency matters most.

---

## 5. Model routing

| Task | Model | Why |
|---|---|---|
| Intent routing, yes/no classification | `nemotron-3-nano` | Smallest, fastest; verify in Phase 0 |
| Argument extraction, tool selection | `gemma-4-26b-a4b` | Measured perfect tool calling at 3 s |
| Brief and narrative generation | `gemma-4-26b-a4b` | Primary |
| Critical-path cross-check (§7.2) | `qwen3.5-9b` | Independent architecture, ~3 s |
| Overnight batch analysis | `deepseek-v4-flash` | 90 s is fine unattended |
| Place-name matching | **none** | stdlib `difflib` beat embeddings 7/7 vs 6/7 — §6.3 |

Routing lives in `registry.py` as config, not scattered constants, so a model swap is one edit.

---

## 6. Phases

Ordered by increasing autonomy — which is the same as increasing blast radius. **Do not reorder.** Each phase is independently useful; stopping after Phase 2 still leaves real value.

---

### Phase 0 — Foundation, and prove the model can do the job

*No user-visible AI. This is the phase that de-risks everything after it.*

- [ ] Add `openai` to `pyproject.toml` (LM Studio is OpenAI-compatible; use the SDK with `base_url="http://localhost:1234/v1"`, `api_key="lm-studio"`)
- [ ] `LMSTUDIO_BASE_URL` + model ids via `_env.py`, following the existing `PMD_API_URL` pattern
- [ ] `src/eqmon/ai/` package skeleton
- [ ] `client.py` — content-or-`reasoning_content` extraction, single-flight queue, timeouts, circuit breaker
- [ ] `registry.py` — model roster and routing table
- [ ] `tools.py` — 8 tool schemas wrapping the domain functions (§6.1)
- [ ] `tests/test_ai_tools.py` — each tool returns identical values to the function it wraps
- [ ] **Capability benchmark harness** — the deliverable that decides Phases 2–3 (§6.2)
- [ ] `audit.py` + migration `007_ai_audit.sql`
- [ ] `validate.py` semantic validation + repair loop
- [ ] `ground.py` numeric grounding guard
- [ ] 20 golden eval cases minimum
- [ ] Benchmark `nemotron-3-nano` for routing; confirm or drop it
- [ ] Pin models resident in LM Studio; disable idle TTL; document the config

**Exit criteria:** every tool callable from a REPL returning correct values; benchmark report published; eval harness green. **Zero AI in the product.**

#### 6.1 Tool surface

Thin wrappers over what exists. All extraction goes through these, never `response_format`.

| Tool | Wraps | Notes |
|---|---|---|
| `search_events` | `events/repo.py` | Cap 50 results — context and latency control |
| `get_event` | `GET /events/{id}` logic | One event + USGS detail |
| `compute_intensity` | `intensity` + `contours` | MMI bands |
| `compute_impact` | `impact.compute_event_impact` | Bands + admin rollups |
| `get_exposure` | `exposure.py` ARC proxy | Elements at risk |
| `compute_aftershock` | `aftershock.py` | Regional Omori-Utsu + G-R |
| `compute_analytics` | `analytics.py` | b-value, Mc, rate series |
| `resolve_place` | `admin_boundary` + embeddings | Fuzzy name → admin unit (§6.3) |

Rules: structured data out, never prose. Every result carries provenance (function, params, event id) so the grounding guard can verify citations. Tool `description` states **when to call**, not just what it does — measured to matter.

#### 6.2 The capability benchmark — Phase 0's most important artifact

Before committing to an architecture, measure this model on *our* schemas:

- [ ] Tool-selection accuracy across all 8 tools (does it pick right with 8 options, not 2?)
- [ ] Argument extraction accuracy on 50 realistic queries
- [ ] **Abstention rate** — does it correctly refuse to call a tool when none applies?
- [ ] **Multi-step chaining** — can it sequence 2, 3, 4 tools? *This determines whether Phase 3 is an agent loop or a fixed pipeline.*
- [ ] Determinism across repeat runs
- [ ] Latency distribution (p50/p95) per tool count
- [ ] Degradation as tool count grows 2 → 8

**Decision gate:** if multi-step chaining accuracy is below the agreed bar, Phase 3 ships as a **fixed pipeline with model-selected parameters** rather than an agent loop. That is a perfectly good product; it is not a failure. Decide with data.

#### 6.3 Fuzzy place-name resolution — ✅ IMPLEMENTED

`CLAUDE.md` records the PMD feed as *"dirty"*, with `parse_met()` already defensively parsing malformed coordinates. Place names carry the same noise, and exact matching against `admin_boundary` silently misses them.

**This was planned as an embeddings task. The measurement killed that idea**, which is exactly why it was measured first. Against a 12-name Pakistani gazetteer with 7 realistic variants:

| Method | Accuracy | Margin range |
|---|---|---|
| `nomic-embed-text-v1.5` cosine | 6/7 | +0.007 – +0.383 |
| **stdlib `difflib`** | **7/7** | **+0.292 – +0.484** |

The embedding failure is the instructive one: it matched **"Peshwar" → "Khuzdar"** — a city 700 km away — on a margin of +0.007, essentially a coin flip. The reason is structural. Embeddings encode *semantic* similarity, and every Pakistani city name is semantically similar to every other; a misspelling is *orthographic* variation. Wrong tool.

Shipped as `src/eqmon/ai/places.py`: normalise (accents, admin suffixes, punctuation) → `SequenceMatcher` ratio → threshold + ambiguity margin. **No GPU, no network, no LM Studio, no new dependency**, and microseconds rather than a ~100 ms round trip — so it can sit in the ingest path without putting inference on the critical path.

Threshold set from a measured separation (true matches bottom out at 0.667, false matches top out at 0.545 → midpoint 0.62). **Caveat recorded in the code:** tuned on 12 names; the real gazetteer is ~161 districts plus tehsils, and denser name spaces raise the false-match ceiling. Re-tune before trusting it in ingest.

The embedding model stays in the roster but is now unused. Do not add it back without a measured reason.

---

### Phase 1 — Situation brief

*Fixed tool sequence. One generation. A human reads it.*

**Problem:** after an event, an operator manually assembles magnitude, depth, peak MMI, affected districts and exposure into a written brief — 10–20 minutes of transcription in exactly the window where minutes matter, and it is the same work every time.

**Shape:** the orchestrator (not the model) calls `get_event` → `compute_impact` → `get_exposure` → `compute_aftershock`, then makes **one** generation call to render the results as prose. The model chooses nothing. This is the lowest-risk useful thing we can ship.

- [ ] `POST /events/{id}/brief`
- [ ] Deterministic DAG in `orchestr.py`
- [ ] Versioned prompt; version recorded in audit
- [ ] Brief sections rendered individually (headline, what happened, who is affected, uncertainties, recommended actions) — short focused generations beat one long one on a small model
- [ ] Grounding guard on every section (§7.1)
- [ ] Frontend panel labelled **AI-generated — verify before distribution**
- [ ] Copy / export actions
- [ ] 10 golden briefs with required numeric content
- [ ] Latency budget: full brief under 30 s

**Exit criteria:** 20 briefs expert-reviewed, zero numeric errors, grounding guard demonstrably catches a corrupted tool result.

**Non-goal:** never auto-published, auto-emailed, or auto-posted. A human sends it or it does not go out.

---

### Phase 2 — Natural-language catalog query

*Single tool call. Trivially verifiable by construction.*

**Problem:** the filter UI supports search, magnitude, source and date. It does not answer *"M5+ within 100km of Quetta in the last decade, excluding aftershocks"* — a routine analyst question needing SQL or a fiddly manual multi-filter.

**Shape:** exactly the interaction already measured working end to end (§2.3). One `search_events` tool call, arguments validated, executed against existing repo functions.

- [ ] `POST /events/query/nl`
- [ ] Extraction via **tool calling** (never `response_format`)
- [ ] Pydantic validation with **range checks**: magnitude 0–10, radius 0–5000 km, years 0–200 — the `6432876487654321` in §2.2 is exactly what these catch
- [ ] Repair loop: on validation failure, re-prompt with the specific error, max 2 retries (free locally — use them)
- [ ] `resolve_place` for the location argument
- [ ] **Round-trip confirmation**: render the interpreted query back in plain language plus editable filter chips. This is the real safety mechanism — a mistranslation becomes visible before anyone trusts the results
- [ ] Never generate SQL. The tool schema is the entire surface
- [ ] 15 golden cases including ambiguous ones
- [ ] Clear rejection path for out-of-scope questions

**Exit criteria:** ≥90% correct translation on the golden set; every mistranslation visible in the confirmation line.

---

### Phase 3 — Analyst assistant

*Shape decided by the Phase 0 benchmark.*

**Problem:** comparative questions needing several tools chained — *"how does this compare to historical events on the same fault system?"*, *"which districts have the highest cumulative MMI exposure this decade?"* Each is a 20-minute manual workflow.

**Two designs. Pick with §6.2 data, not preference.**

**3a — Fixed pipelines** (if chaining accuracy is low): a small set of named analyses, each a hand-written DAG, with the model classifying which analysis is wanted and extracting its parameters. Predictable, debuggable, and it covers the majority of real questions.

**3b — Bounded agent loop** (if chaining accuracy is high): a hand-written loop — *not* a framework — with a hard `max_steps` of 5, a whitelist of tools valid at each step, validation between every step, and a wall-clock budget.

- [ ] Decide 3a vs 3b from the benchmark; record the reasoning
- [ ] Implement in `orchestr.py`
- [ ] **Read-only.** No tool that writes to the database or causes an external side effect
- [ ] Streaming to the frontend — a 30 s answer needs visible progress
- [ ] **Visible tool-call trace panel.** The operator must see what it did, not only what it concluded. On a small model this is not a nice-to-have; it is how errors get caught
- [ ] Per-request step and time ceilings
- [ ] 15 multi-step golden cases

**Exit criteria:** all 15 golden questions answered with correct tool sequences and correct numbers; the trace panel is legible to a non-technical operator.

---

### Phase 4 — Ingest triage and data quality

*First scheduled run. Output is a queue, not a write.*

**Problem:** `parse_met()` currently skips *"unparseable/out-of-range rows"* and they vanish. Some are real events with recoverable formatting problems — a genuine data-loss path today, and one that local inference can address without sending anything anywhere.

- [ ] Persist rejected rows rather than dropping them — migration `008_ingest_rejects.sql`
- [ ] Triage classification per reject: recoverable / genuinely bad / unclear
- [ ] `resolve_place` on rejects whose only defect is a place name
- [ ] Statistical anomaly check against `analytics.py` — is today's rate consistent with the historical b-value distribution?
- [ ] Runs on the existing scheduler after ingest
- [ ] Output is a **human review queue**. Never a write to `seismic_event`
- [ ] Admin UI: accept/reject per row
- [ ] Alerting when triage itself fails — a silently broken agent is worse than none
- [ ] Two-week shadow run before the queue is trusted

**Hard rule:** proposes, never disposes.

---

### Phase 5 — Proactive monitoring

*Highest autonomy. Requires explicit stakeholder sign-off and prior operational history.*

Watches ingest and drafts an escalation brief when thresholds are crossed. **It drafts. It does not send.**

- [ ] Thresholds defined by NDMA stakeholders, not engineering
- [ ] Draft-only queue with a prominent unsent state
- [ ] Kill switch — one config flag disables all autonomous behaviour
- [ ] Escalation runbook: what an operator does when it is wrong, and how that feeds back into evals

**Do not start until Phases 1–4 have a quarter of production history.** Autonomy is earned with evidence.

---

## 7. Cross-cutting engineering

### 7.1 Grounding guard

The highest-value safeguard, in `ground.py`:

1. Extract every numeric literal from the generated text.
2. Extract every numeric value from that turn's tool results.
3. Any output number absent from tool results (within rounding tolerance) → **fail the response**, log it, return an error rather than the text.

Crude, and it will occasionally false-positive on incidental numbers ("the first of three districts"). That trade is correct: a false positive costs a regeneration — free locally — while a false negative costs a misdirected response. Tune the tolerance; never disable the guard.

### 7.2 Validation, repair, and cross-check

Because inference is free at the margin (P6), reliability is bought with compute:

- **Semantic validation** — range checks on every extracted number. §2.2 is the proof this is mandatory.
- **Repair loop** — on failure, re-prompt with the specific validation error. Max 2 retries.
- **Self-consistency** — for critical extractions, sample 3× and take the majority. Measured non-determinism (§2.4) makes this genuinely informative: 3/3 agreement is a confidence signal.
- **Cross-model check** — for the highest-stakes outputs, run `qwen3.5-9b` on the same input and diverge-flag any disagreement. ~3 s and zero marginal cost.

### 7.3 Prompt injection

`CLAUDE.md` documents the PMD feed as externally controlled and dirty. Place names flow from that feed into event records and then into prompts. **That is an injection vector.**

- Wrap all external text (place names, USGS descriptions, ARC responses) in delimited blocks with an explicit instruction that the content is data, never instructions
- Tool outputs are structured JSON, not concatenated prose, limiting what injected text can reach
- Read-only tool surface through Phase 3 means a successful injection cannot cause a write
- Include injection attempts in the eval set — small models are more susceptible, so test rather than assume

### 7.4 Evaluation

**No AI feature ships without evals.** The repo runs TDD (`CLAUDE.md`); this is the same discipline applied to a non-deterministic component.

- Golden cases in `src/eqmon/ai/evals/cases/`, version-controlled
- Each case: input, required tool calls, required numeric facts, forbidden claims
- Assertion-based scoring wherever possible; LLM-judge only for prose quality, never for factual correctness
- Run before every prompt change **and every model or LM Studio upgrade** — a local model update is a silent behaviour change with no release notes
- **Every production bug becomes a golden case.** This is how the set stays honest

### 7.5 Failure modes

| Failure | Behaviour |
|---|---|
| LM Studio down | AI routes 503 with a clear message; **all non-AI endpoints unaffected** |
| Model unloaded / JIT reload | Timeout, retry once, then 503 |
| Empty `content` | Fall back to `reasoning_content` (§4.2) |
| Validation fails after retries | Return error with the parse failure; never show unvalidated output |
| Grounding guard fails | Return error, log full context, suppress output |
| GPU OOM | Circuit-break AI routes, alert, keep the platform running |
| Tool raises | Return the error to the model so it can adapt; record it |

### 7.6 Operations

- Log token counts and wall-clock per call — the local equivalent of a cost dashboard is a **latency and GPU-utilisation dashboard**
- Alert on p95 latency regression: the usual cause is an unexpected model reload or VRAM pressure
- Pin model versions. Record the exact model id and LM Studio version in every audit row
- Re-run the §2 probe suite after any upgrade and diff the results

---

## 8. Consolidated todos

### Blocking / immediate
- [ ] Re-run the §2 probe suite and archive results as the baseline
- [ ] Add `openai` dependency; wire `LMSTUDIO_BASE_URL` and model ids
- [ ] Pin models resident; disable idle TTL
- [ ] Create `src/eqmon/ai/` skeleton

### Phase 0
- [ ] `client.py` (content-or-reasoning, queue, timeouts, breaker)
- [ ] `registry.py` routing table
- [ ] 8 tool wrappers + parity tests
- [ ] **Capability benchmark** → decides Phase 3 shape
- [ ] `validate.py`, `ground.py`, `audit.py` + migration
- [ ] 20 golden cases
- [ ] Benchmark `nemotron-3-nano`; keep or drop
- [ ] Embed `admin_boundary` names; build `resolve_place`

### Phase 1
- [ ] Brief DAG + `POST /events/{id}/brief`
- [ ] Sectioned generation, grounding guard per section
- [ ] Frontend panel with AI labelling
- [ ] 10 golden briefs; 20 expert-reviewed

### Phase 2
- [ ] `POST /events/query/nl` via tool calling
- [ ] Range validation + repair loop
- [ ] Round-trip confirmation UI with filter chips
- [ ] 15 golden query cases

### Phase 3
- [ ] Choose 3a vs 3b from benchmark data
- [ ] Implement; enforce read-only + step ceiling
- [ ] Streaming + visible trace panel
- [ ] 15 multi-step cases

### Phase 4
- [ ] Reject persistence migration
- [ ] Triage + anomaly checks
- [ ] Review queue UI
- [ ] Two-week shadow run

### Phase 5
- [ ] Stakeholder thresholds
- [ ] Draft-only queue, kill switch, runbook

### Continuous
- [ ] Evals re-run on every prompt/model change
- [ ] Probe suite re-run on every LM Studio upgrade
- [ ] Production bugs → golden cases
- [ ] Latency/VRAM dashboard reviewed weekly

---

## 9. Open decisions

1. **Accuracy bar.** What tool-selection and extraction accuracy makes a feature shippable? A number agreed with stakeholders, not an engineering judgment — the cost of error is theirs to weigh.
2. **Latency budget per route.** A brief during an active response has a different tolerance than an analyst's historical query. Needed before effort/model routing is tuned.
3. **Users.** The plan assumes EOC operators and analysts. Public-facing briefs would need a substantially higher review bar and different tone.
4. **GPU contention.** Does anything else need this card during an incident? If so, VRAM pinning needs a policy.

---

## 10. What this plan deliberately does not do

- **No LLM-computed seismology.** Ever.
- **No `response_format: json_schema`.** Measured broken (§2.2).
- **No auto-published output.** Every artifact is drafted for a human.
- **No AI on the critical path.** The platform works with LM Studio stopped.
- **No agent framework.** LangChain/LlamaIndex-style abstractions hide exactly the control we need over a small model. The loop is 50 lines of our own code.
- **No RAG over documents.** The catalog is structured data with a query interface; vectorising it would be less precise, less auditable, and harder to ground. Embeddings are used for place-name matching only.
- **No fine-tuning yet.** Revisit only if the Phase 0 benchmark shows a specific, measured gap that prompting cannot close.

---

## 11. Recommended first step

Phase 0 in full, and specifically **the capability benchmark before any user-facing work**.

The temptation will be to demo a brief in week one. Resist it. The §2 probe took twenty minutes and overturned the design; the full benchmark will do the same for the multi-step question that decides Phase 3's entire shape. A brief built on an unmeasured model with no eval set is a liability that gets harder to unwind the moment stakeholders see it working.

The tool layer is roughly a week given how clean the domain modules already are. The benchmark and golden set are the longer pole — and the higher-value one.
