# AI Current-State Baseline - August 2026

**Date:** 2026-08-27
**Purpose:** Phase 0 baseline for `roadmap.md`
**Sources:** working tree, `ai.md`, and `ai_implementation.md`

## Current Capability

The repository already includes a feature-flagged conversational assistant and
specialized catalog-query route. This corrects older planning text that describes
the assistant panel as inert and AI routes as unimplemented.

### Runtime

- Local inference through LM Studio's OpenAI-compatible endpoint.
- Primary model configured by `EQMON_AI_MODEL_PRIMARY`.
- Interactive and batch scheduling through a bounded broker.
- Queue and execution deadlines, cancellation, circuit breaking, and health
  telemetry are implemented.
- Core non-AI application behavior remains available when AI is disabled.

### Agent Workflow

- Workflow: `agent_chat` version `1.0`.
- Limits: 4 inference steps, 6 tool calls, 20 history messages.
- Request: a message plus user/assistant history.
- Response: status, plain message, tool names, steps, model, and token usage.
- All registered viewer tools are offered on every conversational turn.
- Repeated identical tool calls are not executed twice.
- Tool results are validated and returned to the model as untrusted data.

### Registered Read-Only Tools

| Tool | Cost class | Purpose |
|---|---|---|
| `search_events` | DB | Search the canonical catalog |
| `get_event_summary` | DB | Retrieve a canonical event summary |
| `get_catalog_analytics` | DB | Compute catalog analytics |
| `get_event_analysis` | Compute | Retrieve deterministic modeled impact |
| `get_aftershock_summary` | Compute | Retrieve deterministic aftershock output |
| `resolve_place` | DB | Resolve an administrative place |
| `get_exposure_summary` | External | Retrieve bounded exposure output |

The registry enforces typed inputs and outputs, role checks, workflow allowlists,
and read-only side effects. The current chat workflow uses the entire registry as
its allowlist, so workflow-specific narrowing remains roadmap work.

### Frontend

- The assistant dialog performs an AI health check and posts to `/ai/chat`.
- Conversation history exists only in browser memory and is resent with each
  request.
- The waiting state is a synthetic "Working..." message.
- Answers are rendered as plain text and internal tool names are listed.
- No map, layer, camera, selection, sidebar, filter, or option context is sent.
- No evidence blocks, citations, clarification controls, follow-up actions,
  cancellation, streaming, persistence, or safe map commands exist.

### Audit and Security

- AI jobs record a request hash/length, workflow version, result, model, usage,
  and typed failure.
- Prompts and model reasoning are intentionally not persisted.
- Routes are explicitly local/shadow and use the placeholder actor
  `unauthenticated-local` with viewer role.
- Authentication, actor quotas, production authorization, and retention policy
  remain release blockers.

## Existing Evaluation Evidence

- Search-tool development benchmark with exact argument, abstention,
  repeatability, and sanitized-output scoring.
- Place-resolution evaluator covering resolved, ambiguous, and not-found cases.
- Deterministic agent-loop tests for direct response, tool threading, repeated
  calls, and conversation-history roles.
- Tool contract, route, broker, projection, and claim tests elsewhere in the
  suite.

These are development and regression assets, not an independent release set for
the complete conversational product.

## Phase 0 Chat Evaluation Baseline

Phase 0 starts with a versioned 20-case development snapshot and deterministic
scorer:

- Cases: `src/eqmon/ai/evals/chat_cases_v1.json`
- Scorer: `src/eqmon/ai/evals/chat_runner.py`
- Tests: `tests/test_ai_chat_evals.py`

The initial categories are greeting, general explanation, catalog, event,
analytics, place, clarification, out-of-domain behavior, adversarial behavior,
and safety. The scorer evaluates exact ordered tool use, selected tool arguments,
non-empty answers, and required/forbidden answer terms. It deliberately returns
no answer text or model reasoning.

This snapshot is frozen for development regression use. It is not an independent
locked release set: provenance, independent authorship, and holdout controls have
not yet been established. Prompt changes should add cases separately rather than
silently rewriting failures in this snapshot.

## Known Baseline Limitations

- The Phase 0 scorer measures observable behavior but does not yet execute a live
  model or domain tools end to end.
- Term checks are intentionally simple and cannot replace domain review of
  naturalness, grounding, uncertainty, and source-versus-model distinctions.
- The current request has no workspace context, so context-aware cases begin in
  Phase 1 rather than being scored as current failures.
- Latency and screenshot baselines need an available configured local model and
  browser session; they are operational measurements, not unit-test fixtures.
- The 50 representative conversation archive, independently authored release
  cases, reviewed conversation rubric, screenshots, latency inventory, and
  product instrumentation from the roadmap are not complete yet.

## Next Phase Gate

Phase 0 remains in progress until the remaining operational measurements and
review assets above are complete. Phase 1 implementation should not begin before
that gate is explicitly accepted.
