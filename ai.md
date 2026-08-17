# Agentic AI Integration — Engineering Implementation Plan

**Status:** proposed
**Owner:** AI engineering
**Companion document:** `ai_implementation.md` (principles, safety posture, governance gates)

---

## 0. How to read this document

`ai_implementation.md` answers *may we build this, and under what constraints*.
This document answers *what exactly do we build, in what order, and how do we
know each step is done*.

It deliberately reuses that document's phase numbering (0A, 0B, 0C, then 1–5) so
the two never diverge into competing roadmaps. Where this document adds detail it
elaborates; where the two disagree, `ai_implementation.md` wins on safety and
governance, and this document wins on module layout and sequencing.

Principles inherited verbatim and not re-argued here:

| ID | Principle |
|---|---|
| P1 | Deterministic domain authority — the model never defines seismological semantics |
| P2 | AI remains additive — no existing route may depend on inference |
| P3 | Human authority — operators approve before anything leaves the system |
| P4 | Bounded autonomy — every loop has a step, token, and time budget |
| P5 | Claims require evidence — numbers come from the ledger, not from prose |
| P6 | Local inference is capacity, not free compute |
| P7 | Local inference is not an air gap |

---

## 1. Verified baseline

Confirmed against the working tree, not assumed.

### 1.1 What exists

| Path | State |
|---|---|
| `src/eqmon/ai/client.py` | LM Studio transport, breaker, `reasoning_content` fallback, tool-result threading, offered-name enforcement, truncation guard, lifecycle |
| `src/eqmon/ai/broker.py` | Bounded queue, interactive/batch lanes, queue + execution deadlines, cancellation, telemetry |
| `src/eqmon/ai/config.py` | Env-overridable model roster, timeouts, breaker, sampling |
| `src/eqmon/ai/places.py` | Spatial-first place resolver, orthographic fallback, explicit `ambiguous`/`conflict` states |
| `src/eqmon/ai/tools.py` | `search_events` schema derived from `EventSearchSpec` |
| `src/eqmon/ai/evals/` | Place + search-tool case corpora and runners |
| `src/eqmon/events/search.py` | `EventSearchSpec` v1.0 — validated, model-independent |
| `src/eqmon/analytics_service.py` | `compute_analytics()` — two-pass Mc estimation, zone rollup, typed failures |
| `src/eqmon/aftershock_service.py` | `compute_forecast()` — zone lookup in a savepoint, latitude-band fallback |

**277 tests passing.** The AI modules are mock-only and need no GPU in CI.

Archived evidence: `docs/ai/evals/place_resolution_v1.md`,
`docs/ai/evals/search_tool_gemma_v1.md`,
`docs/ai/evals/raw/search_tool_gemma_2026-08-13_v4_sanitized.json`.

### 1.2 What does not exist

No AI routes in `api.py`, no orchestrator, no claim ledger, no job store, no
audit migration, and no authentication anywhere in the platform. The only
non-AI touch point is a shutdown hook releasing the client's socket pool, which
opens no connection and satisfies P2.

The uncommitted `web/` change is an intentionally inert AI panel shell —
disabled input, "inference not connected". That stays inert until Phase 1 exits.

### 1.3 Constraints the baseline imposes

Four measured facts drive the whole design and must not be re-litigated without
new evidence:

1. **`response_format: json_schema` is unusable** on the primary model — it emits
   schema-valid, semantically destroyed values (`{"min_magnitude": 0, "place": "},{"}`).
   Structured extraction goes through native tool calling plus independent
   semantic validation. `client.chat()` offers no `response_format` parameter by
   design; keep it that way.
2. **Thinking models strand the answer in `reasoning_content`.** Already handled
   in `extract_text`. Raw reasoning is never displayed or persisted as an answer.
3. **One GPU means one generation at a time.** Now bounded by `broker.py`; the
   client's `threading.Lock` remains as a second line of defence.
4. **Truncation is silent.** `finish_reason: "length"` returns 200 with a partial
   body — a truncated tool call has malformed arguments, a truncated sentence
   reads as finished. Now `TruncatedResponseError`.

---

## 2. What "agentic" means in this system

"Agentic" here does **not** mean an open-ended ReAct loop with a broad toolbox.
For a system whose output can influence disaster response, that is the wrong
shape. We build a **bounded, auditable agent**: a loop that may choose *which*
deterministic tools to call and in what order, within a fixed budget, over a
per-workflow allowlist, with every numeric claim traced to a tool result.

### 2.1 The agency ladder

Each rung ships and is evaluated before the next is started.

| Rung | Capability | Autonomy | Ships in |
|---|---|---|---|
| L0 | Deterministic tools, no model | none | Phase 0B |
| L1 | Single tool call, arguments extracted from text | choose args | Phase 1 |
| L2 | Multi-step read-only loop over an allowlist | choose tools + order | Phase 2 |
| L3 | Named workflow with a fixed plan skeleton | choose within plan | Phase 3 |
| L4 | Proposes state changes for human approval | propose only | Phase 4 |
| L5 | Scheduled unattended drafting, human release | propose only | Phase 5 |

**There is no rung where the agent writes to the catalog unattended.** L4 and L5
produce *proposals* that a reviewer accepts or rejects; the accept action is an
ordinary authenticated deterministic route.

### 2.2 Non-goals

- No autonomous ingest correction.
- No model-authored magnitude, MMI, PGA, exposure, or probability values.
- No free-text "recommended actions" — those come from stakeholder-owned
  templates keyed to approved thresholds.
- No agent-initiated outbound network calls beyond the approved egress matrix.

---

## 3. Target module layout

```text
src/eqmon/ai/
  client.py          exists — LM Studio protocol adapter
  config.py          exists — roster, timeouts, budgets
  places.py          exists — deterministic place resolution
  broker.py          NEW — bounded queue, lanes, deadlines, cancellation
  contracts.py       NEW — versioned tool input/output Pydantic models
  registry.py        NEW — tool registration, authz class, cost class
  tools/             NEW — one adapter module per capability
    __init__.py
    events.py        search_events, get_event_summary
    analysis.py      get_event_analysis, get_aftershock_summary
    exposure.py      get_exposure_summary
    analytics.py     get_catalog_analytics
    places.py        resolve_place  (wraps ai/places.py)
  loop.py            NEW — the bounded agent loop
  workflows/         NEW — named workflows with plan skeletons
    __init__.py
    catalog_query.py
    situation_brief.py
  claims.py          NEW — claim extraction, validation, deterministic rendering
  jobs.py            NEW — job + artifact state machine
  audit.py           NEW — redacted audit records
  sanitize.py        NEW — untrusted-text handling, projection caps
  prompts/           NEW — versioned prompt templates, one file per version
  evals/             exists — extend
```

`src/eqmon/ai/` contains **no seismological formulas**. Any capability the agent
needs that the platform lacks is built as a domain service in `src/eqmon/` first
and only then wrapped.

### 3.1 Request path

```text
POST /ai/<workflow>   (authenticated, RBAC-checked, quota-checked)
        │
        ▼
   jobs.create()  ──► job row, status=queued, artifact placeholder
        │
        ▼
   loop.run(workflow, actor, input)
        │
        ├─ prompts/  assemble system + context (capped, sanitized)
        ├─ registry  resolve allowlisted tools for this workflow + role
        │
        ├─◄─┐  step budget / token budget / wall deadline
        │   │
        │   ├─ broker.submit(messages, tools, lane, deadline)
        │   ├─ validate tool name against allowlist        → typed failure
        │   ├─ validate args against contracts.py          → repair or fail
        │   ├─ execute adapter over domain service
        │   ├─ project result (compact, scalar, size-capped)
        │   └─ append tool result message ──────────────────┘
        │
        ▼
   claims.validate()   every numeric bound to a tool result
        │
        ▼
   render: deterministic sentences + optional connective prose
        │
        ▼
   jobs.complete()  ──► artifact, audit.record(), SSE final event
```

---

## 4. Component specifications

### 4.1 Inference broker — `broker.py`

Replaces the process-local lock. This is the single most important piece of
infrastructure work; everything above it assumes bounded, cancellable inference.

**Requirements**

- One broker per GPU, shared across uvicorn workers. Implementation options:
  (a) single-process uvicorn with an in-process asyncio broker, or (b) a Redis
  or Postgres-advisory-lock queue for multi-worker. **Recommendation: start with
  (a)** — pin uvicorn to one worker, document it, and defer (b) until there is a
  measured throughput need. Multi-worker adds a dependency and a distributed
  failure mode for capacity we have not yet needed.
- Bounded queue with an explicit `queue_full` response → HTTP `429`.
- Two lanes: `interactive` (default) and `batch`. Batch never starves
  interactive; interactive never exceeds its per-role quota.
- Two deadlines: **queue deadline** (how long a request may wait) and
  **execution deadline** (how long a generation may run). Both are separate from
  the httpx timeout.
- Cancellation on client disconnect, propagated to the in-flight request.
- Telemetry per submission: queue depth at arrival, wait time, execution time,
  prompt/completion tokens, model, outcome.

**Explicitly out of scope:** batching, speculative decoding, model hot-swap.

### 4.2 Tool contracts — `contracts.py`

Every tool has a versioned input and output model. Input models mostly already
exist or are trivial; **output models are the new work**, because the current
domain functions return rich dicts that must not reach the model.

Each contract declares:

| Field | Purpose |
|---|---|
| `schema_version` | Bumped on any field change; recorded in audit |
| input model | Units, ranges, enums, nullability, `extra="forbid"` |
| output model | Compact projection only — scalars, short strings, bounded lists |
| `authz` | Minimum role |
| `cost_class` | `cheap` / `db` / `external` / `compute` — drives budgets |
| `freshness` | Max acceptable age; stale results are labelled, not hidden |
| typed errors | `not_found`, `ambiguous`, `upstream_unavailable`, `partial` |

**Hard rule:** no tool returns contour GeoJSON, raw `usgs_detail` product trees,
full ARC payloads, or unbounded lists. `sanitize.py` enforces a byte cap on every
projection and raises rather than truncating silently.

### 4.3 Tool registry — `registry.py`

```python
@dataclass(frozen=True)
class ToolSpec:
    name: str
    schema_version: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Callable
    authz: Role
    cost_class: CostClass
    side_effects: Literal["none"]      # Phases 1–3 admit nothing else
```

The registry resolves the tool list per `(workflow, role)`. A model that names a
tool outside its allowlist produces a typed failure recorded as a
**false-call event** in evals — never a silent no-op.

### 4.4 The agent loop — `loop.py`

```python
@dataclass(frozen=True)
class Budget:
    max_steps: int = 6
    max_tool_calls: int = 8
    max_prompt_tokens: int = 8_000
    wall_deadline_s: float = 60.0
```

Loop invariants, each of which gets a direct unit test:

1. The loop terminates. Every exit path is one of: final answer, budget
   exhausted, typed failure, cancellation.
2. Budget exhaustion is a **result**, not an exception — it returns a partial
   artifact marked `incomplete` with the steps taken.
3. Every tool result appended to the message list has passed its output contract.
4. Repeating an identical `(tool, args)` pair is detected and blocked — small
   models loop on unchanged arguments.
5. No step may mutate state (`side_effects == "none"` enforced at dispatch).
6. Assistant → tool → tool-result message threading is complete and correctly
   ordered — currently unsupported by `client.py` and required before L2.

### 4.5 Claim ledger — `claims.py`

The mechanism that makes generated prose safe. A regex numeric guard is
explicitly rejected as insufficient.

```text
Claim
  id, artifact_id, claim_type
  entity_type, entity_id, display_name
  value, unit
  source_kind, source_artifact_id, source_path
  calculation_version
  observed_at, freshness
  limitation
```

**Rendering rule:** every sentence containing a quantity is rendered
deterministically from a validated claim. The model may generate connective and
summarising prose that introduces **no new quantities, entities, or units**.
Validation checks entity binding, unit correctness, source path resolution, and
artifact version — not merely that a number appears somewhere in a tool result.

An unbound quantity in model output fails the artifact. It is not repaired.

### 4.6 Jobs and artifacts — `jobs.py`

```text
queued → running → (completed | failed | cancelled | timed_out)
completed → under_review → (approved | rejected)
approved → exported
```

Analysis artifacts (intensity, impact, exposure, analytics, aftershock) are
computed **once per input + data + calculation version**, stored as compact
immutable metadata with hashes and provenance, and referenced by ID. Briefs cite
artifact IDs; they never duplicate geometry.

### 4.7 Prompt and context assembly — `prompts/`, `sanitize.py`

- One file per prompt version; version recorded in every audit row. Prompts are
  reviewed artifacts, not string literals scattered through handlers.
- All PMD, USGS, ARC, and operator text is **untrusted**. It is delimited,
  size-capped, and never concatenated into the system prompt.
- Prompt delimiters are defence in depth, **not** a security boundary. Tool
  authorization, call limits, and the `side_effects == "none"` rule are enforced
  in code and cannot be talked out of.
- Model output is rendered as text or through a strict sanitizer. Never raw HTML.

---

## 5. Tool surface

| Tool | Wraps | Status |
|---|---|---|
| `search_events` | `repo.list_events` | ✅ adapter + registered. Caps at `MAX_EVENTS_IN_CONTEXT`, reports true `total` |
| `get_event_summary` | `repo.get_event` | ✅ adapter + registered. `usgs_detail`, `url`, `detail_url` excluded |
| `resolve_place` | `ai/places.py` | ✅ adapter + registered. Four states passed through; expand eval corpus before Phase 1 |
| `get_aftershock_summary` | `aftershock_service.compute_forecast` | ✅ adapter + registered. Fitted parameters (k, c, p, alpha, Mref) dropped |
| `get_catalog_analytics` | `analytics_service.compute_analytics` | ✅ adapter + registered. Grid, FMD, rate series, depth scatter dropped |
| `get_event_analysis` | `impact.py`, `intensity.py` | ⏳ blocked on the versioned analysis artifact schema |
| `get_exposure_summary` | `exposure.py` | ⏳ async + external; needs deadline, freshness, ARC partial-failure state |

Five of seven are live. Every registered tool declares `side_effects="none"`,
enforced at registration — the registry refuses to hold a writing tool at all.

**Note on `get_exposure_summary`:** ARC keys `cumulative[].mmi_min` on a band's
*upper* bound, and dissolves on `mmi_high` where we say `mmi_upper`. The headline
is summed from bands, never read from `cumulative`. The tool projection must
expose our semantics, not ARC's, or the model will confidently report the wrong
band.

Place candidates are keyed by **boundary ID, never name**. Duplicate names stay
visible and require level, parent, or geographic context to disambiguate.

---

## 6. API surface

All routes are authenticated and RBAC-checked. None ship before Phase 0A exits.

| Route | Method | Purpose |
|---|---|---|
| `/ai/health` | GET | Broker + breaker state; no inference |
| `/ai/catalog-query` | POST | L1 — text → editable `EventSearchSpec` |
| `/ai/jobs/{id}` | GET | Job status + artifact |
| `/ai/jobs/{id}/events` | GET (SSE) | Step-level progress stream |
| `/ai/jobs/{id}/cancel` | POST | Cooperative cancellation |
| `/ai/brief` | POST | L2/L3 — evidence-cited situation brief |
| `/ai/jobs/{id}/review` | POST | Reviewer approve/reject |

`/ai/catalog-query` returns a **spec, not results** — the operator edits it and
submits it to the existing deterministic `POST /events/search`. That is the whole
reason it is the first user-visible feature: its output is a reviewable filter
contract, not a scientific narrative.

---

## 7. Data model

New migrations, continuing from `007_event_search.sql`:

| Migration | Contents |
|---|---|
| `008_ai_jobs.sql` | `ai_job` — id, actor, role, workflow, workflow_version, status, timestamps, budgets, outcome |
| `009_ai_artifacts.sql` | `ai_artifact` — id, job_id, kind, calculation_version, input_hash, payload, provenance |
| `010_ai_claims.sql` | `ai_claim` — full ledger schema from §4.5, FK to artifact |
| `011_ai_audit.sql` | `ai_audit` — request id, actor, prompt version, model checksum, tool schema versions, timings, tokens, status, review/export state |
| `012_ingest_rejects.sql` | Typed parser reject capture (Phase 0B leftover, independent of AI) |

**Do not write `011` until retention, redaction, partitioning, and access policy
are agreed.** An audit table created before its policy is a compliance liability,
not an asset.

Raw reasoning content is never persisted.

---

## 8. Frontend integration

The existing inert panel (`#ai-chat` in `web/index.html`) is the target surface.
Wiring proceeds in the same rungs as the backend.

1. **Phase 1** — enable the composer. Submit to `/ai/catalog-query`. Render the
   returned spec as an **editable filter form**, pre-filled, with every field the
   model set visually marked as model-derived. Operator edits and presses Search;
   the existing deterministic path runs.
2. **Phase 2** — SSE step stream. Show each tool call as it happens: tool name,
   duration, result summary. Transparency is a safety feature, not decoration.
3. **Phase 3** — brief rendering with inline citation chips. Clicking a chip
   opens the underlying artifact. Uncited prose is visually distinct from
   claim-rendered sentences.
4. Self-host all AI-related frontend assets — the deployment target may be an
   offline or controlled network. The current panel pulls
   `dotlottie-wc` from unpkg; that must be vendored before this ships.
5. Add CSP headers covering the AI surface as part of Phase 0A.

---

## 9. Evaluation strategy

No feature ships on a demo or a hand-picked golden set.

**Four case sets, kept separate:**

| Set | Use |
|---|---|
| Development | Prompt iteration. May be overfit; never quoted as a result. |
| Locked release | Never seen during prompt development. Gates deployment. |
| Adversarial | Indirect prompt injection, malformed tool output, contradictory context, ambiguous places, out-of-domain requests. |
| Production regression | One case created from every confirmed field failure. |

**Metrics, reported with sample counts and confidence intervals over repeated trials:**

- tool-selection accuracy; per-field argument accuracy
- false-call rate and false-abstention rate
- semantic-validation rejection and repair rates
- unsupported-claim rate and citation-attribution accuracy
- entity and unit correctness
- performance sliced by language, region, spelling noise, query complexity
- queue latency, cancellation correctness, overload behaviour, dependency failure

Factual scoring is **deterministic**. An LLM judge is permitted only for
secondary prose-quality analysis, never for factual correctness.

**Reproducibility caveat, already measured:** the primary model is a
mixture-of-experts and its routing varies run to run. Free-text generation
repeated identically 3/3; grammar-constrained generation did not. Evals must
*assert* reproducibility across trials, never assume it.

Every model, prompt, LM Studio, GPU driver, or tool-schema change produces a
signed evaluation report and deployment manifest. A change does not deploy if
the locked release set regresses beyond its approved tolerance.

---

## 10. Observability

| Signal | Detail |
|---|---|
| Broker | queue depth, wait time, execution time, rejections, lane utilisation |
| Loop | steps per run, budget-exhaustion rate, repeat-call blocks, typed failures |
| Tools | call counts, latency, error rate by type, projection size distribution |
| Claims | validation pass rate, unbound-quantity rate |
| Review | operator correction rate, approval rate, time-to-review |
| Cost | tokens per run by workflow — local inference is capacity, not free (P6) |

**Operator correction rate is the primary product health metric.** If operators
routinely rewrite the model's filter spec, the feature is not working regardless
of what offline evals report.

---

## 11. Phased delivery

Each phase lists steps and an exit checklist. Work is TDD per `CLAUDE.md`:
failing test first, minimal implementation, then commit.

---

### Phase 0A — Platform and governance gates

**Blocking. No AI route may ship before this exits.** This is currently the
critical path, and most of it is not AI work — it is platform work the AI feature
happens to require. The whole platform is unauthenticated today.

- [ ] Authentication for all operators
- [ ] Role model: viewer, analyst, operator, reviewer, administrator
- [ ] Route, tool, review, and export authorization
- [ ] Request, concurrency, and artifact quotas
- [ ] Protect existing administrative routes (`/events/ingest*`, `PUT`/`DELETE /events/{id}`) — currently open
- [ ] Threat model, data-flow inventory, approved egress matrix
- [ ] Scientific product classification + approved uncertainty language
- [ ] Deterministic, stakeholder-owned action templates (replacing free-generated advice)
- [ ] Audit retention, redaction, partitioning, and access policy
- [ ] Model license, checksum, deployment, rollback, and recovery policy
- [ ] CSP + outbound host allowlist; vendor all third-party frontend assets

**Exit:** security and domain owners sign off on the boundary for a shadow-mode
AI feature.

---

### Phase 0B — Deterministic capabilities

Every intended tool must be callable and testable **without a model**.

- [x] Versioned `EventSearchSpec` independent of AI
- [x] Point/radius and mainshock filtering with spatial indexes and tests
- [x] Point-distance semantics and catalog coverage metadata
- [x] Duplicate-preserving, spatially-first place resolution
- [x] Versioned place-resolution evaluator over all 757 boundaries
- [x] **Implement `analytics_service.py`** — extracted from the `/analytics` handler; two-pass Mc sequencing named and tested
- [x] **Extract aftershock service** — zone lookup + lat-band fallback out of the `/aftershock` handler, lookup contained in a savepoint
- [ ] Define versioned analysis artifact schema + compute-once semantics
- [ ] Define claim ledger schema
- [ ] Expand place evaluation with held-out feed/operator cases and boundary-edge/gap cases
- [ ] Capture parser rejects with typed reason codes before records are dropped (`012`)

**Exit:** all seven tools in §5 are callable, contract-tested, and model-free.

---

### Phase 0C — Inference foundation

- [x] `httpx` LM Studio transport with mock tests
- [x] Model roster configuration
- [x] Deterministic place resolver with orthographic fallback
- [x] Archived place-resolution calibration
- [x] Live `search_events` tool benchmark, sanitized records archived
- [x] **`broker.py`** — bounded queue, lanes, dual deadlines, cancellation, telemetry
- [x] **Complete assistant → tool → tool-result message threading** in `client.py`
- [x] Validate every response shape and reject unoffered tool names
- [x] Wall-clock deadlines, cancellation, lifecycle cleanup
- [ ] Safe retry policy — deferred; retrying truncation or invalid arguments
      without changing the request just repeats the failure
- [x] `contracts.py` + `registry.py` + `tools/` adapters over Phase 0B services
      (5 of 7 tools; the remaining two are blocked on the artifact schema and on
      async external-service handling)
- [ ] Locked release case set, built by someone who did not write the prompts
- [ ] Adversarial case set including indirect prompt injection
- [ ] Multi-tool, abstention, and repeatability benchmark
- [ ] Load and failure report: queue saturation, LM Studio down, GPU OOM, slow tool

**Exit:** live benchmark plus failure/load reports meet the shadow-mode gate.

---

### Phase 1 — Natural-language catalog query (shadow, then visible)

First user-visible feature, because its output is an **editable deterministic
filter contract**, not a narrative.

**Steps**

1. `workflows/catalog_query.py` — L1, single tool, `search_events` only
2. `jobs.py` + migrations `008`/`009`
3. `POST /ai/catalog-query`, authenticated, quota-checked
4. **Shadow mode:** run on real operator queries, persist, show nothing. Compare
   the model's spec against what the operator actually submitted.
5. Frontend: enable the composer, render the editable pre-filled spec form
6. Promote to visible only after the shadow comparison meets its threshold

**Checklist**

- [ ] Exactly one `search_events` call per run, enforced
- [ ] Every emitted spec passes `EventSearchSpec` validation
- [ ] Abstention on non-catalog questions ≥ agreed threshold
- [ ] Ambiguous places surface candidates instead of guessing
- [ ] Operator sees and can edit every model-set field before execution
- [ ] Shadow-mode agreement rate reported with CIs on the locked set
- [ ] Breaker-open path degrades to the plain search form with no error dialog
- [ ] `/ai/health` reflects broker and breaker state

**Exit:** operator correction rate below the agreed threshold over a defined
shadow period.

---

### Phase 2 — Evidence-cited situation brief

First **multi-step** feature (L2). Read-only allowlist, claim ledger mandatory.

**Steps**

1. `loop.py` with the §4.4 invariants and their tests
2. `claims.py` + migration `010`
3. `workflows/situation_brief.py` — allowlist: `get_event_summary`,
   `get_event_analysis`, `get_exposure_summary`, `get_aftershock_summary`
4. Deterministic sentence renderers per claim type
5. SSE step stream + frontend step display
6. Review queue: `under_review → approved | rejected`

**Checklist**

- [ ] Loop terminates on every path; budget exhaustion returns a partial artifact
- [ ] Repeat `(tool, args)` calls blocked and counted
- [ ] Every quantity in output bound to a validated claim
- [ ] Unbound quantity fails the artifact — no silent repair
- [ ] Citation chips resolve to real artifact IDs
- [ ] Two independent domain reviewers sign off using a written rubric
- [ ] Adversarial set: no injection causes an out-of-allowlist tool call
- [ ] Brief marked *preliminary modeled analysis* unless reclassified by a stakeholder

**Exit:** rubric review passed; unsupported-claim rate at the agreed near-zero
target on the locked set.

---

### Phase 3 — Named analyst workflows

L3 — fixed plan skeletons, model chooses within the plan.

- [ ] Workflow definitions versioned and audited
- [ ] Cross-check model (`qwen3.5-9b`) on high-stakes output; disagreement surfaced, not silently resolved
- [ ] Per-workflow budgets tuned against measured step distributions
- [ ] Batch lane exercised for long-running workflows
- [ ] Production regression set seeded from Phase 1–2 field failures

---

### Phase 4 — Ingest reject review

L4 — the agent **proposes**; a reviewer disposes.

Depends on `012_ingest_rejects.sql`. The PMD feed is dirty by design —
hemisphere-suffixed coordinates, out-of-range magnitudes — and currently drops
unparseable rows silently. Capturing typed rejects is valuable on its own merits
and should not wait on AI.

- [ ] Typed reject reason codes captured at parse time
- [ ] Agent proposes a correction with evidence; never writes
- [ ] Reviewer accept path is an ordinary deterministic authenticated route
- [ ] Accept/reject decisions feed the production regression set

---

### Phase 5 — Draft-only proactive monitoring

L5 — scheduled unattended drafting, human release.

- [ ] Batch lane only; never contends with interactive
- [ ] Drafts expire unreleased rather than auto-publishing
- [ ] Quiet-hours and volume caps
- [ ] Explicit kill switch independent of the breaker

---

## 12. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Phase 0A stalls on stakeholder availability | High | Blocks everything | Start 0A conversations now, in parallel with 0B/0C engineering |
| MoE non-determinism breaks eval reproducibility | Confirmed | High | Repeated trials + CIs; assert, never assume |
| Model semantically corrupts structured output | Confirmed | High | Tool calling only; `response_format` unavailable by construction |
| Single-GPU capacity limits interactive use | Medium | Medium | Broker lanes + quotas; batch lane for non-interactive |
| Prompt injection via PMD/USGS/ARC text | Medium | High | Untrusted-text handling + code-enforced allowlist; delimiters are not the boundary |
| Claim ledger judged too heavy, gets skipped | Medium | Severe | It is the entire safety mechanism for prose — Phase 2 does not ship without it |
| Two plan documents diverge | Medium | Low | This file owns *how*; `ai_implementation.md` owns *whether* |
| Scope creep toward open-ended agent | Medium | High | Agency ladder is explicit; each rung gated by evals |

---

## 13. Immediate work order

Ordered by what unblocks the most downstream work. Items struck through are
done; see §1.1.

1. **Open Phase 0A stakeholder conversations** — identity, authorization,
   governance, audit policy. Longest lead time, blocks every route, and needs
   people rather than code. **Still the critical path.**
2. ~~Implement `analytics_service.py` and extract the aftershock service.~~ done
3. ~~Build `broker.py`.~~ done
4. ~~Complete tool-result message threading in `client.py`.~~ done
5. **Build `contracts.py`, `registry.py`, and the `tools/` adapters.** Next.
   The two domain blockers are cleared, so all seven tools are now reachable.
6. **Build the locked release and adversarial case sets** — by someone who did
   not write the prompts.
7. **Design the claim ledger schema** before writing any brief code.

Items 5–7 carry no governance risk because none of them expose a route, so they
proceed in parallel with item 1.

---

## 14. Definition of done

A phase is done when, and only when:

- every checklist item above is checked with evidence, not assertion;
- the locked release set has been run and its report archived under `docs/ai/evals/`;
- the deterministic test suite passes in full;
- no existing non-AI route has gained a dependency on inference (P2);
- an operator can complete the phase's task with LM Studio switched off, by the
  pre-existing deterministic path.
