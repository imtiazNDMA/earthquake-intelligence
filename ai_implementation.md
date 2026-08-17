# Agentic AI Integration Plan - eqMonitoring2

**Status:** Reviewed architecture and delivery plan
**Updated:** 2026-08-17
**Inference target:** Local models through LM Studio's OpenAI-compatible API
**Reference hardware:** NVIDIA RTX 6000 Ada, 48 GB VRAM

## 1. Purpose

Add AI-assisted workflows without allowing a language model to calculate
seismology, mutate the canonical catalog, publish operational messages, or
become a dependency of ingest, intensity, impact, exposure, or analytics.

The model may:

- translate natural language into a validated deterministic query;
- select from authorized read-only tools inside a bounded orchestrator;
- summarize versioned analysis artifacts into a human-reviewed draft; and
- classify staged data-quality records for human review.

The model may not:

- calculate MMI, PGA, exposure, aftershock probability, or statistical metrics;
- generate SQL or invoke arbitrary code;
- invent operational recommendations;
- write to `seismic_event` or approve a rejected source record;
- send, publish, or escalate an artifact; or
- expose raw model reasoning as an answer.

## 2. Current Status

Status labels used throughout this plan:

- **Implemented:** code exists in the repository.
- **Mock-tested:** deterministic tests run without a live model.
- **Live-probed:** manually observed against a named local model.
- **Production-ready:** security, operations, evaluation, and domain acceptance
  gates are complete. Nothing in the AI layer has this status yet.

### 2.1 Implemented and mock-tested

- `src/eqmon/ai/client.py`: synchronous LM Studio HTTP transport, response
  parsing, circuit breaker, complete assistant-tool-tool-result threading,
  offered-tool-name enforcement, truncation detection, and lifecycle cleanup.
- `src/eqmon/ai/broker.py`: bounded queue with interactive/batch lanes, separate
  queue and execution deadlines, cancellation, and queue-health telemetry.
  A timed-out synchronous generation releases its caller but retains the worker
  slot until the underlying thread returns, preserving one-generation-at-a-time.
- `src/eqmon/ai/config.py`: environment-configurable endpoint and model roster.
- `src/eqmon/ai/places.py`: duplicate-safe, spatial-first place resolver with
  orthographic fallback and explicit ambiguity/conflict states.
- `src/eqmon/analytics_service.py` and `src/eqmon/aftershock_service.py`:
  deterministic orchestration extracted from the API handlers, callable with an
  explicit connection and no request in flight. `AftershockForecastInput`
  enforces exclusive request modes, finite values, magnitude 0–10, and WGS84
  coordinate bounds before database or forecast work.
- `src/eqmon/ai/contracts.py`, `src/eqmon/ai/registry.py`, and
  `src/eqmon/ai/tools/`: versioned output projections, authorization checks, and
  six registered read-only adapters. The aftershock tool schema is generated
  from the same validated service input contract used at runtime. Every current
  adapter enforces the projection byte ceiling, and aftershock event evidence
  preserves its canonical PMD/USGS/MANUAL source. `get_event_analysis` reuses the
  immutable impact artifact and exposes a bounded projection with no geometry or
  full administrative rollups.
- `src/eqmon/analysis_artifacts.py` and
  `migrations/008_analysis_artifacts.sql`: model-independent immutable artifact
  records, canonical input/data hashes, calculation versions, and PostgreSQL
  advisory-lock compute-once semantics. Event impact is the first producer and
  fingerprints the exact Vs30 COG and relevant administrative boundaries.
- `src/eqmon/claims.py` and `migrations/009_analysis_claims.sql`: immutable,
  versioned scalar evidence with exact Decimal values, typed MMI units/entities,
  canonical RFC 6901 source paths, artifact/version checks, row-level entity
  binding, and idempotent insertion. Prose rendering is not implemented.
- `tests/test_ai_client.py`, `tests/test_ai_broker.py`, `tests/test_ai_places.py`,
  `tests/test_analytics_service.py`, `tests/test_aftershock_service.py`, and
  `tests/test_ai_aftershock_contract.py`. Cross-tool guards are covered by
  `tests/test_ai_tool_contract_guards.py`. Artifact identity, immutability,
  failure, reuse, and two-connection concurrency are covered by
  `tests/test_analysis_artifacts.py`; the event-analysis projection and schema
  are covered by `tests/test_ai_tools_event_analysis.py`; claim validation,
  persistence, artifact-trigger checks, and real impact binding are covered by
  `tests/test_claims.py`. The full suite currently passes 354 tests without a GPU.

Four silent local-model failures are now pinned in CI rather than three. The
fourth is truncation: `finish_reason: "length"` returns HTTP 200 with a partial
body, so a truncated tool call carries malformed arguments and a truncated
sentence reads as a finished one. It is a typed failure.

These remain scaffolding, not product integration. There are still no AI routes,
orchestrator, claim rendering/prose guard, job store, audit migration, connected
analyst UI, or ingest review queue. The model-independent claim ledger exists;
the frontend analyst console remains offline and its composer remains disabled.

### 2.2 Preliminary live probe

The following observations were made on 2026-08-13 but are not yet a
reproducible benchmark:

| Model | Preliminary observation |
|---|---|
| `google/gemma-4-26b-a4b` | Tool arguments were correct on a small two-tool probe; observed latency 2.7-3.3 s |
| `qwen/qwen3.5-9b` | Correct on the same small probe; observed latency 2.9-9.5 s |
| `deepseek/deepseek-v4-flash` | Observed latency 12-97 s; unsuitable for interactive use |
| `nvidia/nemotron-3-nano` | Not benchmarked |

On the tested Gemma artifact, grammar-constrained `json_schema` output produced
schema-valid but semantically corrupted values. Native tool calling performed
correctly on the small probe. Until a larger reproducible evaluation says
otherwise, structured extraction will use tool calling followed by independent
semantic validation, not `response_format: json_schema`.

The probe artifact must be archived with the exact model file/checksum,
quantization, context settings, LM Studio version, GPU driver, prompts, tool
schemas, sampling parameters, raw responses, and repeated trials before it may
be called a baseline.

## 3. Safety and Product Principles

### P1 - Deterministic domain authority

All scientific and geographic calculations come from versioned deterministic
domain services. This guarantees traceability, not scientific authority. Every
artifact must distinguish:

- source-reported facts;
- observed facts, when available;
- modeled or derived values;
- unavailable data; and
- limitations and uncertainty.

### P2 - AI remains additive

Stopping LM Studio must leave all existing non-AI behavior available. Source
events are committed before any AI-adjacent enrichment or triage is queued.

### P3 - Human authority

AI produces drafts, interpretations, and review candidates. Authenticated users
approve, export, or discard them. No draft is automatically published or sent.

### P4 - Bounded autonomy

Autonomy lives in deterministic code: named workflows, authorized tools, typed
state transitions, step limits, wall-clock deadlines, and inference budgets.
An open-ended agent loop is not the default architecture.

### P5 - Claims require evidence

Schema-valid output is not necessarily correct. Critical claims require entity,
unit, source, version, and freshness attribution. Numeric membership in a tool
response is not adequate grounding.

### P6 - Local inference is capacity, not free compute

Local calls consume finite GPU time, power, queue capacity, and incident-response
latency. Retries, voting, and cross-model checks require measured reliability
gains and a per-request inference budget.

### P7 - Local inference is not an air gap

The defensible claim is: **LLM inference payloads remain on the configured
inference host.** The wider platform still communicates with PMD, USGS, ARC,
TileServerGL, and currently some frontend CDNs. Data sovereignty requires an
approved data-flow and egress policy, not merely a local model.

## 4. Target Architecture

```text
FastAPI
  |
  +-- Existing deterministic routes -------------------------- unchanged
  |
  +-- AI routes -> authentication/RBAC -> job service
                                      |
                                      +-- deterministic workflow engine
                                      |      +-- versioned tool contracts
                                      |      +-- analysis artifact store
                                      |      +-- claim/evidence ledger
                                      |
                                      +-- inference broker
                                             +-- bounded priority queue
                                             +-- one worker per GPU
                                             +-- deadlines/cancellation
                                             +-- interactive and batch lanes

Domain services -> PostGIS / Vs30 COG / approved external services
```

### 4.1 Module boundaries

Proposed modules:

```text
src/eqmon/
  analysis_artifacts.py  deterministic artifact identity and persistence
  claims.py              deterministic evidence validation and persistence
  ai/
    client.py       low-level LM Studio protocol adapter
    config.py       validated inference configuration and model roster
    contracts.py    model-facing result schemas and typed failures
    registry.py     tool authorization, allowlists, and cost metadata
    tools/          authorized adapters and schemas over deterministic services
    orchestrator.py named workflows and bounded state transitions
    jobs.py         artifact/job state machine
    audit.py        redacted audit metadata
    evals/          runner, cases, manifests, and reports
```

`src/eqmon/ai/` contains no seismological formulas. Domain capabilities missing
from the current application are implemented as domain services first, not
hidden inside AI wrappers.

### 4.2 Inference broker

The implemented in-process broker makes prototype load explicit and bounded, but
it is still process-local. Production requires one supervised broker per GPU
with:

- a bounded priority queue and queue-full response;
- queue and execution deadlines;
- cancellation when the caller disconnects;
- one global concurrency policy across API workers;
- separate interactive and batch priorities;
- per-user and per-role quotas;
- queue depth, wait time, execution time, tokens, and GPU telemetry; and
- explicit overload behavior using `429` or `503`.

The LM Studio transport is synchronous, so an execution deadline cannot cancel
an HTTP call already running in a worker thread. The caller stops waiting at the
deadline, while the broker deliberately keeps the GPU slot occupied until that
thread returns. A two-request regression test proves the next request is not
dispatched early. Hard interruption still requires an async/cancellable
transport.

Raw `reasoning_content` is never displayed or persisted as an operator answer.
A missing final answer is a typed model failure. Model-specific adapters may use
a follow-up finalization request if a pinned model requires one.

## 5. Cross-Cutting Gates

### 5.1 Identity and authorization

Before a user-visible AI route ships:

- authenticate every operator;
- define viewer, analyst, operator, reviewer, and administrator roles;
- authorize tools and exports by role;
- apply request, concurrency, and artifact quotas;
- attribute every job, review, and export to an authenticated subject; and
- protect administrative ingest and configuration routes as part of the same
  platform security work.

### 5.2 Scientific governance

- Classify outputs as preliminary modeled analysis unless an authoritative
  stakeholder explicitly approves another designation.
- Define an authoritative-source hierarchy and freshness policy.
- Establish approved limitation and uncertainty language.
- Replace free-generated recommended actions with deterministic,
  stakeholder-owned action templates keyed to approved thresholds.
- Require domain review for changes to calculations, thresholds, or templates.

### 5.3 Data governance and security

- Document data classification, deployment boundary, and approved egress.
- Self-host frontend assets for offline/controlled-network deployment.
- Review model provenance, license, checksum, and update policy.
- Treat all PMD, USGS, ARC, and operator text as untrusted data.
- Send only allowlisted, size-limited scalar projections to the model.
- Render model output as text or through a strict sanitizer; never raw HTML.
- Add CSP, outbound host allowlisting, retention, redaction, backup, and access
  policies for AI artifacts and audit records.

Prompt delimiters are defense in depth, not a security boundary. Tool
authorization, call limits, and side-effect policy are enforced in code.

### 5.4 Claim and evidence ledger

Replace the proposed regex numeric guard with structured claims:

```text
Claim
  id
  artifact_id
  claim_type
  entity_type / entity_id / display_name
  value / unit
  source_kind
  source_artifact_id
  source_path
  calculation_version
  observed_at / freshness
  limitation
```

Critical numeric sentences are rendered deterministically from validated
claims. Generated prose may connect and summarize those sentences but may not
introduce uncited quantities. Validation checks entity binding, units, source
paths, and artifact versions, not merely whether a number appears somewhere.

The model-independent ledger is implemented before AI jobs. Version 1 supports
direct scalar evidence from impact artifacts only: event maximum MMI class and
administrative maximum/representative MMI. Values are exact decimals and paths
are canonical RFC 6901 pointers into immutable artifact fields. Claims pin the
artifact kind, schema, and calculation version and bind administrative claims to
the exact rollup row, not merely to a matching number. Database triggers enforce
artifact metadata agreement and immutability. Deterministic sentence rendering,
brief membership, and unbound-quantity rejection remain Phase 2 work.

### 5.5 Analysis artifacts

Compute event intensity, impact, exposure, analytics, and aftershock products
once per input/data/calculation version. Store compact immutable metadata,
hashes, provenance, and references rather than duplicating contour geometry in
the audit table. Briefs and citations reuse these artifacts.

The model-independent artifact store is now implemented before AI jobs by
design. `analysis_artifact` has no `ai_job` dependency. Canonical JSON identity
combines scientific input and data fingerprints; schema and calculation versions
complete the unique key. A transaction-scoped advisory lock plus a second lookup
guarantees same-key concurrent callers compute once. Failed callbacks insert
nothing, and database triggers reject updates and deletes. Event impact is the
first integrated producer, with Vs30 COG and administrative-boundary SHA-256
fingerprints. Exposure remains excluded until ARC revision/freshness semantics
are defined.

### 5.6 Audit policy

Record request ID, actor, role, workflow version, prompt version, model artifact
checksum, tool schema versions, analysis artifact IDs, timing, token usage,
status, review state, and export state. Do not persist raw reasoning. Define
redaction, retention, partitioning, role-restricted access, and deletion policy
before creating the audit migration.

## 6. Tool Contracts

Each tool has versioned Pydantic input and output models defining:

- units, ranges, enums, and nullability;
- result and pagination limits;
- authorization and cost class;
- timeout and freshness behavior;
- compact model-context projection;
- provenance and calculation version; and
- typed errors and partial-result semantics.

No tool returns full contour GeoJSON, raw USGS product trees, or unrestricted
external-service payloads to the model.

Initial deterministic capabilities:

| Capability | Required domain work |
|---|---|
| `search_events` | Add explicit dates, point/radius, mainshock state, canonical/source semantics, result caps, and catalog completeness |
| `get_event_summary` | Implemented: allowlisted event fields, raw `usgs_detail` omitted, projection byte ceiling enforced |
| `get_event_analysis` | Implemented: reuses versioned impact artifact; bounded modeled-impact projection excludes geometry and full rollups |
| `get_exposure_summary` | Deadline-bound ARC summary with freshness and partial-failure state |
| `get_aftershock_summary` | Implemented: deterministic zone lookup/fallback service, shared exclusive-mode finite/range validation, and canonical source provenance |
| `get_catalog_analytics` | Extract API orchestration into a deterministic service with a compact result |
| `resolve_place` | Implemented: spatial resolution first when coordinates exist; orthographic matching only as fallback/corroboration. Full-gazetteer evaluation remains pending |

Place candidates must be keyed by boundary ID, not name. Duplicate names remain
visible and require level, parent, or geographic context to disambiguate.

## 7. Evaluation Strategy

No AI feature ships based on a demonstration or a small hand-picked golden set.

Maintain four sets:

- development cases for prompt iteration;
- locked release cases not used during prompt development;
- adversarial cases including indirect prompt injection and malformed tools;
- production regressions created from every confirmed failure.

Report repeated-trial results with sample counts and confidence intervals for:

- tool-selection accuracy;
- per-field argument accuracy;
- false-call and false-abstention rates;
- semantic-validation rejection and repair rates;
- unsupported-claim and citation-attribution rates;
- entity and unit correctness;
- performance by language, region, spelling noise, and query complexity;
- queue latency, cancellation, overload, and dependency failures; and
- end-to-end operator correction and approval rates.

Factual scoring is deterministic. An LLM judge may be used only for secondary
prose-quality analysis. Critical claims require a near-zero false-accept target;
the exact threshold is agreed with domain and operational stakeholders. Briefs
use a written rubric and at least two independent domain reviewers before
release.

Every model, prompt, LM Studio, driver, or tool-schema change produces a signed
evaluation report and deployment manifest. A change does not deploy if the
locked release set regresses beyond its approved tolerance.

## 8. Delivery Phases

### Phase 0A - Platform and governance gates

- [ ] Authentication and role model.
- [ ] Authorization for routes, tools, reviews, and exports.
- [ ] Rate, concurrency, and artifact quotas.
- [ ] Threat model, data-flow inventory, and approved egress matrix.
- [ ] Scientific product classification and approved uncertainty language.
- [ ] Audit retention/redaction/access policy.
- [ ] Model license, checksum, deployment, rollback, and recovery policy.

**Exit:** security and domain owners approve the boundary for a shadow-mode AI
feature.

### Phase 0B - Deterministic capabilities

- [x] Implement a versioned `EventSearchSpec` independent of AI.
- [x] Add point/radius and mainshock filtering with spatial indexes/tests.
- [x] Define point-distance semantics and catalog coverage metadata.
- [x] Extract reusable aftershock and analytics services from API handlers.
- [x] Validate aftershock request modes and numeric ranges independently of the
  model, and derive the offered tool schema from that shared contract.
- [x] Enforce the projection byte ceiling on single-event summaries and preserve
  canonical source provenance in aftershock event evidence.
- [x] Define versioned analysis artifacts and compute-once semantics.
- [x] Define the model-independent claim ledger schema and validation: immutable
  exact scalar values, typed units/entities, canonical source paths, artifact
  version checks, and row-level entity binding.
- [x] Preserve duplicate place names and resolve coordinates spatially before
  using text as fallback or corroboration.
- [x] Add a versioned place-resolution evaluator and development calibration over
  all 757 loaded boundaries plus a labeled spelling/ambiguity/negative corpus.
- [ ] Expand place evaluation with held-out feed/operator cases and systematic
  boundary-edge/gap cases before ingest or AI-tool integration.
- [ ] Capture parser rejects with typed reason codes before records are dropped.

**Exit:** every intended tool can be called and tested without a model.

### Phase 0C - Inference foundation

- [x] Basic `httpx` LM Studio transport and mock tests.
- [x] Initial model configuration.
- [x] Duplicate-safe, spatial-first place resolver with orthographic fallback.
- [x] Replace process-local single-flight with a bounded inference broker;
  retain the worker slot while a timed-out synchronous generation finishes.
- [x] Add complete assistant-tool-tool-result message support.
- [x] Validate all response shapes and offered tool names.
- [x] Add wall-clock deadlines, cancellation, and lifecycle cleanup.
- [ ] Add a safe retry policy. Deliberately deferred: retries are only free
  locally when the failure is transient, and retrying a truncation or an
  invalid-argument failure without changing the request repeats it.
- [x] Build tool adapters over Phase 0B contracts. Six of seven registered:
  `search_events`, `get_event_summary`, `get_catalog_analytics`,
  `get_aftershock_summary`, `get_event_analysis`, `resolve_place`.
  `get_exposure_summary` awaits async
  external-service handling with freshness and partial-failure state.
- [x] Build and archive deterministic place-resolution development calibration.
- [x] Build a live `search_events` tool benchmark and archive sanitized
  development trial records, prompt/schema/case snapshots, and observable model
  metadata without model text or reasoning.
- [ ] Build a locked release set and broader multi-tool/adversarial capability
  benchmark before any user-visible AI route.
- [ ] Benchmark all tools together, abstention, repeatability, and multi-step
  behavior.

**Exit:** live benchmark and failure/load reports meet the shadow-mode gate.

### Phase 1 - Natural-language catalog query, shadow mode

This is the first user-visible AI feature because its output is an editable
deterministic filter contract, not a scientific narrative.

- [ ] Translate text into exactly one `EventSearchSpec` tool call.
- [ ] Validate all fields independently of the model.
- [ ] Resolve ambiguous locations explicitly; never silently choose.
- [ ] Display editable filter chips, distance semantics, date anchoring,
  mainshock semantics, and catalog-coverage limitations.
- [ ] Require explicit execution during shadow mode.
- [ ] Record operator corrections as evaluation data.
- [ ] Reject unsupported questions without guessing.

**Exit:** approved per-field, false-accept, and correction-rate thresholds are
met on locked tests and a monitored shadow run.

### Phase 2 - Evidence-cited situation brief

Generate an asynchronous review artifact, not a synchronous response.

- [ ] Return `202` and a job ID.
- [ ] Reuse one versioned event analysis artifact.
- [ ] Make external exposure optional and deadline-bound.
- [ ] Build critical numeric statements from the claim ledger.
- [ ] Generate only neutral transitions, summary, and approved limitation text.
- [ ] Use deterministic stakeholder action templates, if approved.
- [ ] Support queued, running, partial, failed, draft, reviewed, approved,
  exported, and superseded states.
- [ ] Support cancellation, reconnect, citations, freshness indicators, operator
  edits, regeneration diffs, and export watermark/metadata.

**Exit:** dual expert review meets the factual and attribution threshold; no
uncited critical claim reaches a draft.

### Phase 3 - Named analyst workflows

Implement fixed, domain-approved workflows before considering an agent loop.
Examples must correspond to existing deterministic services and data. Do not
claim fault-system association or cumulative historical exposure until those
domain products exist and are validated.

- [ ] Select from a small set of named workflows.
- [ ] Extract validated parameters.
- [ ] Show an operator-facing evidence timeline rather than raw chain-of-thought.
- [ ] Enforce workflow-specific tool, time, and inference budgets.

Only consider a bounded read-only agent loop if a locked benchmark proves that
it improves coverage without exceeding the approved error and capacity budget.
The loop has a hard step limit, workflow-specific tool allowlist, typed state,
and no side-effecting tools.

### Phase 4 - Ingest reject review

Parsing first returns accepted records plus typed rejects. Each reject stores a
source payload hash/reference, parser version, retrieval metadata, and reason
code. AI classification runs asynchronously after the successful source sync
and cannot affect its watermark.

- [ ] Define review outcomes and whether acceptance creates a staging record,
  parser-rule proposal, or reviewed catalog write.
- [ ] Require authenticated review and dual control for canonical catalog writes.
- [ ] Run in shadow mode for an approved observation period.
- [ ] Use a statistically defensible, completeness-controlled anomaly detector;
  do not use b-value as a direct event-rate distribution.

### Phase 5 - Draft-only proactive monitoring

- [ ] Thresholds and deterministic action templates owned by stakeholders.
- [ ] Draft-only queue with an unmistakable unsent state.
- [ ] Global kill switch and per-workflow disable controls.
- [ ] Incident runbook, feedback path, and periodic failure drills.

Do not start until earlier phases have sufficient production history and
explicit stakeholder sign-off.

## 9. Operations

- Run inference as a supervised service that starts without an interactive
  desktop session.
- Pin model artifacts, LM Studio/runtime, GPU driver, context, quantization, and
  generation settings.
- Record startup readiness, model-load state, memory high-water mark, queue
  depth, queue latency, tokens per second, execution latency, cancellation,
  error class, and OOM recovery.
- Define SLOs separately for queue, deterministic computation, external
  dependencies, and generation.
- Define backup/restore, model rollback, stuck-generation recovery, degraded
  operation, and single-GPU failure procedures.
- Keep batch analysis from starving interactive incident work.
- Require evaluation and capacity reports as deployment artifacts.

## 10. Immediate Work Order

1. Expand the place corpus with held-out feed/operator examples and spatial
   boundary-edge cases as they become available.
2. Expand the live benchmark with locked release, adversarial, and multi-tool
   cases; compare the primary and cross-check models.
3. Specify identity, authorization, governance, and audit policies with the
   relevant stakeholders.
4. Capture parser rejects with typed reason codes before records are dropped.

The deterministic place calibration and initial live search-tool development
runs are archived under `docs/ai/evals/`. The next engineering milestone is an
independent locked release set and broader multi-tool benchmark; the model still
does not define query or place semantics.
