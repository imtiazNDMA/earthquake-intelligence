# EqMon AI Product and Agent Roadmap

**Status:** proposed full-stack AI rework plan
**Reviewed:** 2026-08-27
**Inputs:** `ai_implementation.md`, `ai.md`, and the current repository
**Primary objective:** turn the prototype chat into a context-aware, evidence-backed analyst copilot without making inference authoritative or required for core operations.

## 1. Executive Summary

EqMon already has a strong deterministic AI foundation: a bounded inference
broker, typed read-only tools, projection limits, immutable analysis artifacts,
a scalar claim ledger, feature-flagged AI routes, minimal job persistence, and a
four-step conversational tool loop. The current product surface does not expose
that foundation well. It behaves like a generic chatbot, has no knowledge of the
operator's visible map state, offers every tool on every turn, returns one flat
string, and displays internal tool names rather than useful evidence.

The next implementation should not make the agent more autonomous first. It
should make the agent more **situated, explainable, useful, and natural**:

1. Give it a validated snapshot of the operator's current workspace.
2. Route requests into small named workflows with narrow tool allowlists.
3. Return typed response blocks with evidence, limitations, and safe UI actions.
4. Stream useful progress without exposing chain-of-thought.
5. Improve conversational continuity, tone, clarification, and error recovery.
6. Evaluate context use, factual grounding, and conversation quality before
   expanding the agent's capabilities.

The architecture remains additive. Map rendering, event selection, filters,
scientific calculations, and catalog writes continue to work with LM Studio off.

## 2. Findings From the Review

### 2.1 What is implemented now

- `src/eqmon/ai/client.py`: LM Studio transport, response validation, tool-call
  threading, truncation detection, and circuit breaker.
- `src/eqmon/ai/broker.py`: bounded interactive/batch queue, deadlines,
  cancellation, and telemetry.
- `src/eqmon/ai/contracts.py`, `registry.py`, and `tools/`: seven typed,
  read-only tools over deterministic domain services.
- `src/eqmon/ai/workflows/agent_chat.py`: a bounded four-step, six-tool-call
  conversational loop with repeat-call prevention.
- `src/eqmon/ai/routes.py`: feature-flagged `/ai/health`, `/ai/catalog-query`,
  and `/ai/chat` routes with minimal job recording.
- `src/eqmon/analysis_artifacts.py` and `claims.py`: immutable deterministic
  artifacts and validated scalar evidence.
- `web/app.js`: connected assistant UI with health gating, local conversation
  history, plain-text output, and a list of tools used.

### 2.2 Stale statements in the reviewed documents

The two source plans contain valuable safety constraints but no longer describe
the working tree consistently:

- `ai.md` says the panel is inert and AI routes do not exist. Both now exist.
- It lists six tools and exposure as unfinished. Seven tools are registered,
  including exposure with bounded external-service behavior.
- It proposes modules that have since been implemented under different names or
  split across existing files.
- Test counts and migration numbers are historical and should not be used as
  current completion evidence.

The source documents should remain the safety/governance record. This roadmap is
the current product and engineering delivery plan.

### 2.3 Current product gaps

| Area | Current behavior | Consequence |
|---|---|---|
| Workspace awareness | Request contains only message and text history | Agent cannot know selected event, camera, map mode, visible layers, opacity, filters, theme, or active panel |
| Tool routing | Every registered tool is offered on every turn | More false calls, larger prompt, weaker intent control, harder authorization |
| Response contract | One generated `message` string | No citations, confidence/freshness display, follow-ups, cards, or safe actions |
| Conversation style | Prompt only says "briefly and directly" | Generic greetings, repetitive phrasing, abrupt answers, poor clarification |
| Progress | One synthetic "Working..." bubble | Long local-model latency feels frozen and opaque |
| Evidence UI | Raw internal tool names | Operator cannot inspect the supporting event/artifact or understand freshness |
| Continuity | Last 20 messages resent by browser | No conversation identity, summary, context version, or cross-device recovery |
| Safety enforcement | Claims exist but chat prose is not claim-rendered | Numeric chat answers can still be model-composed from tool projections |
| Observability | Job stores final result and token usage | No per-step/tool trace, context-use metrics, corrections, or user feedback |
| Security | Routes use `unauthenticated-local` viewer | No actor attribution, role-specific tool access, quotas, or review authority |

## 3. Product Vision

The assistant is an **analyst copilot attached to the current operational
workspace**, not a separate general-purpose chatbot.

It should answer questions such as:

- "What am I looking at?"
- "Which hazard layers are currently visible, and what do they mean?"
- "Summarize the selected earthquake and the current MMI footprint."
- "Compare this event with other M6+ events in the current map extent."
- "Why is the Gilgit-Baltistan landslide layer relevant here?"
- "Show only national faults and the 475-year PGA layer."
- "Open the aftershock forecast for this event."

Read questions use current context plus deterministic tools. UI changes are
returned as proposals and executed by validated frontend commands only after an
explicit user action. The model never manipulates Leaflet, MapLibre, DOM nodes,
SQL, or scientific formulas directly.

## 4. Non-Negotiable Architecture

### 4.1 Deterministic authority

- The model does not calculate MMI, PGA, exposure, aftershock probability,
  catalog statistics, distances, or spatial intersections.
- Current UI state is descriptive context, not scientific evidence.
- Quantitative claims come from typed tool projections or validated claims.
- Catalog writes and operational publication remain outside the agent loop.

### 4.2 Three separate contracts

Do not overload the chat request or response with untyped dictionaries.

```text
AnalystContext     what the operator currently sees and has selected
AgentRun           bounded workflow/tool execution and evidence trace
AssistantResponse  operator-facing answer blocks and proposed UI actions
```

### 4.3 Context is untrusted and versioned

Browser context can be stale or tampered with. The backend validates shape and
limits, treats labels as untrusted text, and re-queries canonical facts by ID
when factual answers depend on them.

### 4.4 Commands are not tools

Read-only backend tools retrieve evidence. Frontend commands modify presentation
state. They use separate allowlists and execution paths:

```text
Model proposes action -> backend validates action schema -> UI displays action
chip -> operator activates -> frontend command registry validates and executes
```

No action is hidden inside prose and no arbitrary JavaScript is generated.

## 5. Target Full-Stack Architecture

```text
Browser
  mapModes.getState() + UI state collectors
       |
       v
  AnalystContext v1 ---- POST /ai/chat or SSE session
       |                         |
       |                         v
       |                 Context policy / intent router
       |                         |
       |            +------------+------------+
       |            |                         |
       |      context-only answer       named workflow
       |                                      |
       |                              narrow tool allowlist
       |                                      |
       |                              deterministic tools
       |                                      |
       +--------------------------> evidence ledger
                                              |
                                      response composer
                                              |
                                 AssistantResponse v1
                                              |
                 text + evidence + limitations + follow-ups + proposed actions
```

### 5.1 New backend modules

```text
src/eqmon/ai/
  context.py              AnalystContext contracts, sanitization, limits
  intent.py               deterministic pre-routing + typed model classification
  response.py             response block and UI-action contracts
  conversation.py         conversation state, summary, context reconciliation
  command_policy.py       validates proposed frontend actions
  prompts/
    chat_system_v2.txt
    response_style_v1.txt
    clarification_v1.txt
  workflows/
    workspace_explain.py
    event_brief.py
    catalog_explore.py
    hazard_explain.py
    compare_events.py
```

Keep `client.py`, `broker.py`, `registry.py`, and deterministic domain tools deep
and stable. Do not put UI details into tool handlers.

### 5.2 New frontend modules

The chat code should move out of the final 150 lines of `web/app.js`.

```text
web/ai-chat.js             conversation controller and transport
web/ai-context.js          normalized workspace snapshot collector
web/ai-renderer.js         safe typed-block renderer
web/ai-actions.js          allowlisted UI command registry
web/ai-chat.css            assistant-specific responsive presentation
```

The modules consume public seams such as `eqmonMapModes.getState()` and intent
functions. They must not inspect Leaflet or MapLibre private objects.

## 6. Core Contract: AnalystContext v1

### 6.1 Request shape

```json
{
  "schema_version": "1.0",
  "captured_at": "2026-08-27T12:00:00Z",
  "map": {
    "mode": "2d",
    "center": [73.47, 34.37],
    "zoom": 11,
    "bearing": 0,
    "pitch": 0,
    "bounds": [72.9, 33.9, 74.0, 34.9],
    "basemap": "OpenStreetMap"
  },
  "selection": {
    "event_id": "canonical-id-or-null",
    "mmi_level": 7,
    "sidebar_section": "landslide"
  },
  "layers": {
    "reference": [{"id": "national", "visible": true, "opacity": 1}],
    "landslides": [{"id": "GB", "visible": true, "opacity": 0.62}],
    "pga": {"visible": false, "return_period": 475, "opacity": 0.55},
    "buildings": {"visible": true, "selected_district": null},
    "mmi": {"visible": true, "opacity": 0.45}
  },
  "event_filters": {
    "sources": ["USGS", "PMD"],
    "minimum_magnitude": 4.0,
    "date_from": null,
    "date_to": null,
    "time_window_indices": [0, 24]
  },
  "display": {"theme": "dark", "reduced_motion": false}
}
```

### 6.2 Context rules

- IDs, booleans, enums, finite numbers, and bounded arrays only.
- No GeoJSON, raster data, popup HTML, DOM text dumps, or renderer handles.
- Maximum serialized context size: 16 KiB initially.
- Camera coordinates are orientation context, not proof of administrative
  membership. Use `resolve_place` when place identity matters.
- A selected event ID is re-resolved with `get_event_summary` before factual use.
- Context carries `captured_at`; responses label stale context after an approved
  threshold, initially 30 seconds for rapidly changing UI state.
- Backend records context field presence and hash, not necessarily the full raw
  snapshot, pending audit retention policy.

### 6.3 Context knowledge UX

The assistant should acknowledge context naturally only when relevant:

- Good: "You currently have the GB landslide mask and national faults visible."
- Bad: "According to AnalystContext schema version 1.0..."
- Good: "The selected event is M6.2 near Muzaffarabad."
- Bad: silently treating a stale browser label as canonical evidence.

## 7. Response Contract and Natural Conversation

### 7.1 AssistantResponse v1

```json
{
  "schema_version": "1.0",
  "status": "complete",
  "answer": "The selected event produced the strongest modeled shaking...",
  "blocks": [
    {"type": "fact", "text": "...", "evidence_ids": ["artifact:123"]},
    {"type": "limitation", "text": "Exposure data is currently unavailable."}
  ],
  "evidence": [
    {"id": "artifact:123", "label": "Modeled event impact", "freshness": "current"}
  ],
  "actions": [
    {"type": "set_layer_visibility", "label": "Show GB landslide layer", "layer_id": "GB", "visible": true}
  ],
  "follow_ups": ["Compare with nearby M6+ events", "Open aftershock forecast"],
  "tools_used": ["get_event_analysis"]
}
```

`tools_used` is retained for diagnostics but not shown as a raw "Tools:" line by
default. The UI renders evidence labels and an optional "How this was answered"
disclosure.

### 7.2 Conversation style specification

The current prompt leaves quality to the model. Add a reviewed style policy:

- Answer the actual question in the first sentence.
- Use a warm, calm, professional operational tone.
- Do not repeat "Hello" or "How can I help?" after every short message.
- For a greeting, respond in one natural sentence and mention two contextually
  relevant capabilities, not the entire tool catalog.
- Use the selected event or visible layer context when it clearly helps.
- Ask one concise clarification when the request has multiple plausible targets.
- Avoid headings for one-sentence answers; use short structure for analytical
  answers.
- Distinguish source-reported, modeled, and unavailable information in ordinary
  language.
- Never expose chain-of-thought. Explain evidence and tool outcomes instead.
- Avoid robotic phrases such as "I could not complete that request within the
  tool-call limit." Translate typed failures into actionable language.
- Do not end every answer with a question. Offer follow-up chips separately.

### 7.3 Deterministic conversational layer

Do not spend GPU time on trivial UX:

- Deterministic greeting and capability templates.
- Deterministic error messages by typed failure code.
- Deterministic context summaries for "what is open?" and "what am I viewing?"
  where no canonical data lookup is needed.
- Deterministic quantitative sentences from validated claims.
- Model-generated connective prose only where it adds explanatory value.

This improves latency, repeatability, and conversational consistency.

## 8. Safe UI Action Catalog

Version 1 actions are presentation-only and require explicit activation:

| Action | Validated fields | Frontend handler |
|---|---|---|
| `set_layer_visibility` | known layer ID, boolean | Existing overlay/landslide/PGA controls |
| `set_layer_opacity` | known layer ID, 0–1 | Existing opacity control path |
| `select_event` | canonical event ID | Existing event-selection path |
| `set_map_mode` | `2d` or `3d` | `eqmonMapModes.setMode()` |
| `set_camera` | bounded center/zoom, optional bearing/pitch | `eqmonMapModes.setCamera()` |
| `open_sidebar_section` | known section enum | `showSection()` public wrapper |
| `open_aftershock_forecast` | canonical event ID | Existing aftershock selection workflow |
| `apply_event_filters` | validated `EventSearchSpec` subset | Existing deterministic filter controls |

Explicitly excluded: delete/update event, ingest, export, publish, arbitrary URL,
arbitrary layer URL, arbitrary HTML, and arbitrary function invocation.

## 9. Delivery Roadmap

### Phase 0 - Baseline, Reconciliation, and Evaluation Harness

**Goal:** establish a truthful baseline before changing behavior.

**Backend**

- Inventory the current seven tools, schemas, cost classes, and observed latency.
- Archive current `agent_chat` prompt, model settings, and 50 representative
  conversations, including greetings, ambiguous requests, context questions,
  multi-tool questions, failures, and out-of-domain prompts.
- Add deterministic scoring for tool choice, tool arguments, unsupported
  quantities, source/model distinction, and required clarification.
- Add a written conversation rubric: relevance, naturalness, concision,
  continuity, clarification quality, and recovery quality.

**Frontend**

- Capture screenshots and interaction recordings at desktop and mobile sizes.
- Instrument time to first feedback, time to final answer, abandon rate, retry
  rate, and response-copy rate without storing raw sensitive text by default.

**Files**

- `docs/ai/current-state-2026-08.md`
- `src/eqmon/ai/evals/chat_cases_v1.json`
- `src/eqmon/ai/evals/chat_runner.py`
- `tests/test_ai_chat_evals.py`

**Acceptance criteria**

- Current code and documents are reconciled in one baseline report.
- A repeatable eval command produces per-category results with trial counts.
- At least 20 locked cases are authored independently of prompt implementation.
- Existing non-AI and AI tests remain green.

### Phase 1 - Workspace Context Foundation

**Goal:** let the assistant understand what the operator currently sees.

**Backend**

- Add `AnalystContextV1` Pydantic contracts in `ai/context.py` with `extra="forbid"`.
- Add size, enum, range, count, timestamp, and stale-context validation.
- Extend `AgentChatRequest` with optional `context` and `conversation_id`.
- Store a context fingerprint and field-presence summary in the AI job record.
- Add prompt assembly that separates system policy, conversation, context, and
  untrusted tool data.

**Frontend**

- Add `web/ai-context.js` to collect normalized state from public app seams.
- Include map mode, camera, selected event, MMI selection, sidebar section,
  visible layers and opacity, PGA period, landslide regions, building state,
  event filters, basemap, and theme.
- Debounce snapshot creation; capture immediately before submit rather than on
  every map move.
- Add an optional "Using current map context" disclosure showing a human-readable
  subset, not raw JSON.

**Tests**

- Contract rejects renderer objects, unknown fields, NaN/infinity, huge arrays,
  stale timestamps, and oversized payloads.
- Browser test proves visible layer and selected event state reach `/ai/chat`.
- Test that switching Leaflet/MapLibre does not change context semantics.
- Test that canonical event facts are reloaded by ID rather than trusted from UI.

**Acceptance criteria**

- "What layers are open?" answers exactly from current state without a model tool.
- "Summarize this event" resolves the selected event ID through canonical tools.
- Context payload remains below 16 KiB in representative maximal UI state.
- No map API request is triggered merely to assemble AI context.

### Phase 2 - Intent Routing and Named Workflows

**Goal:** stop exposing all seven tools to every request.

**Backend**

- Add deterministic routing for greetings, help, workspace explanation, and
  typed failures.
- Add a small intent classifier contract for requests requiring inference.
- Route to named workflows with explicit tool allowlists and budgets:
  - `workspace_explain`: no tools unless canonical event/place facts are needed.
  - `catalog_explore`: `search_events`, `resolve_place`.
  - `event_brief`: event summary, event analysis, exposure, aftershock.
  - `hazard_explain`: event analysis plus context; no catalog-wide analytics.
  - `catalog_analytics`: analytics and optional search.
  - `compare_events`: bounded event search plus at most N event summaries.
- Enforce cost budgets, not only call counts. External and compute tools receive
  lower per-run caps than cheap/DB tools.
- Return explicit `clarification_required` with typed options when target event,
  place, period, or comparison set is ambiguous.

**Frontend**

- Render clarification options as buttons that submit a structured answer.
- Show a subtle task label such as "Reviewing selected event" rather than raw
  internal workflow names.

**Tests**

- Every workflow test asserts exact offered tool names.
- False-call tests verify out-of-workflow tools never dispatch.
- Ambiguous current state yields clarification, not a guessed target.
- Greetings and workspace questions produce no broker request where deterministic
  rendering is sufficient.

**Acceptance criteria**

- Prompt tool schema size decreases materially for each workflow.
- Locked-set tool-selection accuracy meets the agreed threshold.
- No workflow can call a tool outside its allowlist, regardless of prompt text.
- Common greetings return in under 100 ms without inference.

### Phase 3 - Typed Responses, Evidence, and Natural Conversation

**Goal:** replace flat chatbot strings with trustworthy, human-quality answers.

**Backend**

- Add `AssistantResponseV1`, response blocks, evidence references, limitations,
  follow-up prompts, and proposed action contracts in `ai/response.py`.
- Move prompt strings into versioned files and record prompt versions in jobs.
- Add deterministic renderers for supported quantitative claim types.
- Add prose validation: no unsupported quantities, entities, units, URLs, or
  claims of observation.
- Add response repair only for presentation schema failures where no tool is
  rerun; do not repeatedly regenerate unsupported factual content.
- Translate typed infrastructure and tool failures into reviewed operator copy.

**Frontend**

- Extract chat from `web/app.js` into `ai-chat.js`.
- Render paragraphs, compact fact rows, limitations, evidence chips, follow-up
  chips, and proposed actions using DOM APIs and `textContent`.
- Replace "Tools: search_events" with "Based on 12 catalog matches" and an
  expandable evidence panel.
- Redesign message hierarchy: remove repetitive ASSISTANT/YOU labels, use
  conversational grouping, timestamps on demand, and clear source/model badges.
- Improve composer: Enter to send, Shift+Enter for newline, auto-growing input,
  stop/cancel control, retry failed message, and preserved draft.
- Replace "Working..." with contextual progress: "Checking the selected event",
  "Reviewing modeled impact", "Preparing a concise answer".

**Conversation UX acceptance examples**

- User: "hi"
  Response: "Hi. I can help interpret the selected event or explain the layers
  currently visible on your map."
- User: "what am I looking at?"
  Response names the actual map mode, selected event, basemap, and active layers.
- User: "is this observed shaking?"
  Response clearly states whether the visible product is modeled or observed.

**Acceptance criteria**

- Numeric statements in supported high-stakes answers resolve to evidence IDs.
- Evidence chips open a real event or analysis-artifact view.
- No raw model HTML is inserted into the page.
- Conversation rubric improves over baseline with no factual regression.
- Errors preserve the user's message and provide a relevant retry path.

### Phase 4 - Streaming, Cancellation, and Perceived Performance

**Goal:** make local inference feel responsive and controllable.

**Backend**

- Introduce `POST /ai/runs` returning `202` and a run ID.
- Add SSE at `/ai/runs/{id}/events` with typed events:
  `queued`, `started`, `tool_started`, `tool_completed`, `composing`, `completed`,
  `partial`, `failed`, and `cancelled`.
- Add cooperative cancellation and disconnect propagation.
- Persist step metadata without prompts, reasoning, or unbounded tool payloads.
- Emit queue position/range only when meaningful; do not expose fake precision.

**Frontend**

- Render progress as one evolving assistant turn rather than many chat bubbles.
- Show tool outcomes as evidence timeline entries, never chain-of-thought.
- Add Stop while queued/running and Retry after typed transient failures.
- Reconnect to an active run after panel close/reopen or brief network loss.

**Acceptance criteria**

- First visible feedback occurs within 200 ms of submission.
- Cancellation stops queued work and releases UI state predictably.
- Browser reconnect receives the final result exactly once.
- Batch work cannot starve interactive conversations.

### Phase 5 - Safe Map and UI Actions

**Goal:** turn answers into useful, reviewable operational assistance.

**Backend**

- Add typed action contracts and `command_policy.py`.
- Validate action IDs against a server-side catalog shared by version, not raw
  names invented by the model.
- Require canonical event IDs for event actions and valid layer IDs for map
  actions.
- Keep action proposal separate from execution and audit both proposal and user
  activation.

**Frontend**

- Add `ai-actions.js` with one handler per allowed action.
- Display actions as explicit buttons: "Show GB landslide layer", "Open MMI VII",
  "Frame selected event", "Apply these filters".
- Preview multi-field filter changes before applying.
- Provide Undo for reversible presentation actions by storing the prior normalized
  UI state, not renderer objects.

**Tests**

- Unknown action, layer, section, event, or out-of-range camera is rejected.
- Prompt injection cannot create arbitrary function calls or URLs.
- Each action works in both 2D and 3D through shared coordinator seams.
- Actions never trigger scientific recalculation unless the operator explicitly
  invokes an existing deterministic workflow.

**Acceptance criteria**

- Operator activation is required for every action.
- All version 1 actions are reversible or visibly disclose consequences.
- No action path can write, delete, ingest, publish, or export data.

### Phase 6 - Conversation Persistence and Personalization

**Goal:** provide continuity without uncontrolled prompt growth or privacy risk.

**Backend**

- Add conversation and message tables only after retention/redaction policy.
- Store structured response/evidence/action metadata; never raw reasoning.
- Add deterministic conversation summaries when history exceeds token budget.
- Reconcile old references: if selected event or context changes, explicitly state
  the new target rather than silently carrying old assumptions.
- Add user preferences for verbosity, units, and default response language after
  authentication exists.

**Frontend**

- Conversation list, new conversation, rename, clear, and export transcript with
  evidence metadata.
- Visible context reset when the user changes selected event during a thread.
- Optional concise/detailed response control.

**Acceptance criteria**

- Conversation can resume without resending unbounded history.
- Switching selected event cannot cause an answer about the previous event
  without an explicit reference.
- Delete/retention behavior is tested and documented.

### Phase 7 - Proactive and Advanced AI Features

Start only after Phases 0-6 meet evaluation and governance gates.

Candidate features:

- **Situation brief drafts:** evidence-cited, asynchronous, review-required.
- **Event comparison workspace:** deterministic comparison table plus narrative
  interpretation of differences.
- **Layer explainer:** contextual explanation of visible PGA, landslide, fault,
  administrative, building, and MMI layers with provenance and limitations.
- **Data quality review:** classify typed ingest rejects and propose parser-rule
  changes for reviewer approval.
- **Watchlists:** user-defined deterministic conditions that queue drafts, never
  publish alerts automatically.
- **Multilingual analyst support:** English and Urdu prompt/eval sets with domain
  terminology review; do not rely on ad hoc translation.
- **Voice input/readback:** optional, local, push-to-talk, and disabled by default
  in operations rooms; transcript review before submission.
- **Retrieval over approved documentation:** versioned local knowledge base for
  operator manuals, data dictionaries, model limitations, and SOPs. Retrieval
  documents remain untrusted and citations are mandatory.

Each candidate requires its own named workflow, allowlist, evaluation set,
capacity budget, and operator sign-off.

## 10. API Plan

### Transitional v1

```text
POST /ai/chat
  request:  message, history, context?, conversation_id?
  response: AssistantResponseV1 + run metadata
```

### Target asynchronous API

```text
POST   /ai/runs
GET    /ai/runs/{id}
GET    /ai/runs/{id}/events
POST   /ai/runs/{id}/cancel
POST   /ai/runs/{id}/feedback
GET    /ai/conversations
POST   /ai/conversations
DELETE /ai/conversations/{id}
```

Keep `/ai/catalog-query` as a specialized deterministic-filter workflow rather
than folding it invisibly into generic chat.

## 11. Data and Migration Plan

Do not create audit/conversation tables before policy decisions. Proposed order:

1. Extend `ai_job` with prompt/workflow/context schema versions, context hash,
   queue timing, execution timing, and typed outcome metadata.
2. Add `ai_run_step` for bounded step telemetry and evidence references.
3. Add `ai_conversation` and `ai_message` after retention/deletion policy.
4. Add `ai_feedback` for helpful/not-helpful, correction category, and optional
   sanitized comment.
5. Add review/export associations for situation briefs only when that workflow
   is implemented.

Raw reasoning, unrestricted prompts, full browser context, contour geometry, and
full external payloads are excluded.

## 12. Evaluation and Release Gates

### 12.1 Required evaluation sets

- Development cases for iteration.
- Locked release cases authored independently.
- Adversarial cases: prompt injection in event/place/source text, malformed
  context, contradictory context/tool facts, tool false calls, and UI-action
  injection.
- Production regression case for every confirmed failure.

### 12.2 Metrics

**Grounding**

- Tool selection and per-field argument accuracy.
- Context field-use accuracy.
- Unsupported claim, quantity, entity, and unit rates.
- Citation correctness and freshness disclosure.
- Source-reported versus modeled classification accuracy.

**Conversation**

- Direct-answer rate.
- Required-clarification precision and recall.
- Repetition and unnecessary-greeting rate.
- Operator-rated naturalness, relevance, and concision.
- Correction, retry, abandonment, and follow-up activation rates.

**Operations**

- Queue wait, generation time, time to first event, and total completion time.
- Tool latency/error by cost class.
- Cancellation correctness and broker saturation behavior.
- Tokens per completed task and GPU memory high-water mark.

### 12.3 Initial release thresholds

Exact high-stakes thresholds require domain approval. Engineering defaults for
shadow mode:

- 100% schema validity after backend validation.
- 0 successful out-of-allowlist tool or UI-action dispatches.
- 0 uncited supported critical quantities in release cases.
- At least 95% correct selected-event and visible-layer context use.
- At least 90% correct clarification behavior on labeled ambiguous cases.
- No regression in deterministic non-AI workflows with inference disabled.

## 13. Security and Governance Workstream

This remains a parallel release blocker even while product work proceeds behind
`EQMON_AI_ENABLED`:

- Authenticate operators and derive roles from server-side identity.
- Apply route, tool, action, review, and export authorization.
- Add per-actor quotas and concurrency limits.
- Protect existing administrative non-AI routes too.
- Approve data classification, egress, retention, redaction, and deletion.
- Pin model artifact, checksum, license, runtime, driver, quantization, and prompt
  deployment manifest.
- Self-host AI frontend dependencies and add CSP/outbound host allowlists.
- Define approved uncertainty and limitation language with domain owners.
- Add an AI kill switch independent of LM Studio health and circuit breaker.

No authentication placeholder should be mistaken for production authorization.

## 14. Testing Strategy

### Backend

- Unit tests for every Pydantic context, response, action, and intent contract.
- Workflow tests with fake broker and exact offered-tool assertions.
- Tool projection and byte-limit tests.
- Claim rendering and unsupported-quantity tests.
- Broker load, cancellation, deadline, and queue-saturation tests.
- Route tests for auth, quotas, typed failures, and feature flags.
- Migration integration tests with `DATABASE_URL_TEST`.

### Frontend

- Node harness for context collection from representative shared state.
- DOM tests for response blocks and action validation without model access.
- Playwright tests for selected event/layer context, streaming, cancellation,
  retries, evidence expansion, mobile composer, keyboard behavior, and screen
  reader names.
- Security tests proving model text is never inserted as HTML.
- Cross-renderer action tests for Leaflet and MapLibre coordinator paths.

### Verification commands

```bash
node --check web/ai-context.js
node --check web/ai-chat.js
node --check web/ai-renderer.js
node --check web/ai-actions.js
uv run pytest tests/test_ai_*.py -q
uv run pytest tests/browser -q
uv run pytest -q
```

## 15. Observability and Product Analytics

Record bounded structured signals:

- request/run/conversation IDs;
- actor and role after authentication;
- workflow, prompt, context, response, tool, and action schema versions;
- context fields present and context fingerprint;
- offered/called tools, timings, typed outcomes, and projection sizes;
- evidence and action IDs shown/activated;
- queue and generation telemetry;
- user feedback and correction category;
- model artifact checksum and generation settings.

Do not record raw reasoning. Raw user/model text retention requires an explicit
policy and should default to off or short-lived in early shadow deployments.

## 16. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| UI context is trusted as fact | Incorrect event/place claims | Treat as orientation; re-query canonical facts by ID |
| More context worsens prompt injection | Tool/action misuse | Typed scalar context, size caps, code allowlists, separate action policy |
| Generic agent selects expensive tools | Latency and GPU starvation | Intent routing, named workflows, narrow allowlists, cost budgets |
| Natural prose introduces quantities | Factual error | Deterministic claim sentences and unsupported-quantity rejection |
| Streaming exposes reasoning | Security and trust issue | Stream workflow status/evidence events only |
| Chat actions become hidden automation | Unsafe UI changes | Explicit action chips, operator activation, command registry, undo |
| Conversation history grows indefinitely | Cost and stale assumptions | Conversation summaries, reference reconciliation, token budgets |
| Local model variability | Inconsistent behavior | Repeated eval trials, pinned manifests, deterministic fast paths |
| Documents drift again | Wrong planning decisions | One current roadmap, generated capability inventory, dated baseline |
| AI polish hides missing authorization | Premature production use | Feature flag, visible prototype label, governance release gate |

## 17. Recommended Work Order

### Sprint 1 - Context and baseline

1. Build chat evaluation baseline and conversation rubric.
2. Implement `AnalystContextV1` and backend validation.
3. Extract `web/ai-context.js` and send current map/layer/selection state.
4. Implement deterministic "what is open?" and greeting responses.

### Sprint 2 - Workflow routing

1. Add intent contract and named workflow dispatcher.
2. Restrict tool allowlists and add cost budgets.
3. Add clarification response and frontend option chips.
4. Run locked and adversarial routing evaluations.

### Sprint 3 - Response and conversation UX

1. Implement `AssistantResponseV1` and prompt versioning.
2. Extract chat frontend modules and typed response renderer.
3. Add evidence, limitations, follow-ups, retry, and improved composer behavior.
4. Implement deterministic claim rendering for supported numeric answers.

### Sprint 4 - Streaming and actions

1. Add run/SSE/cancel API and step persistence.
2. Add progress timeline and reconnect behavior.
3. Implement presentation-only action contracts and frontend command registry.
4. Browser-test actions in both map modes.

### Parallel workstream - Production gates

1. Authentication/RBAC and administrative-route protection.
2. Audit/data retention policy and migrations.
3. Model deployment manifest and operations runbook.
4. Locked release, adversarial, load, and failure evaluations.

## 18. Definition of Done for the Reworked Assistant

- The assistant can accurately describe the selected event, active map mode,
  camera area, visible layers, layer options, filters, and active workspace.
- Canonical factual answers use deterministic tools and evidence references.
- Quantitative high-stakes sentences are claim-backed and source/model status is
  clear.
- Answers feel natural under the written rubric and avoid repetitive chatbot
  boilerplate.
- The UI supports clarification, evidence inspection, follow-ups, cancellation,
  retries, and safe action proposals.
- Every workflow has a narrow tool allowlist, step/time/token/cost budget, and
  locked evaluation set.
- Inference failure leaves all existing deterministic workflows available.
- No AI path writes to the catalog, publishes an alert, or executes arbitrary UI
  code.
- Authentication, authorization, quotas, audit policy, model manifest, security
  review, and domain acceptance are complete before production enablement.
