# Gemma Search Tool Development Benchmark v1

**Date:** 2026-08-13
**Model:** `google/gemma-4-26b-a4b`
**Quantization:** `Q4_K_M`
**Loaded context:** 262,144 tokens
**Trials:** 10 development cases x 3 repeats = 30
The original raw artifact was deleted because evaluator `1.0` persisted model
text that could contain `reasoning_content`. The aggregate development results
below are retained to document why the prompt/schema changed.

LM Studio did not expose its application version or model artifact checksum via
the queried APIs. The report records those values as `null`; model ID and
quantization alone are not sufficient for bit-for-bit reproduction.

## Initial Results

| Metric | Result |
|---|---:|
| Overall exact trial accuracy | 24/30 (80.0%) |
| Tool-call exact accuracy | 15/21 (71.43%) |
| Abstention accuracy | 9/9 (100%) |
| Malformed or invalid calls | 2 |
| Median latency | 1.320 s |
| Observed p95 latency | Not retained after correcting the estimator |
| Maximum latency | 3.765 s |

This is development-set performance, not held-out release evidence.

## Failures

- `magnitude-range-source` failed 3/3 because the model omitted `source=USGS`.
- `oldest-manual` failed 3/3: two calls emitted lower-case `manual`, which the
  deterministic contract correctly rejected, and one exhausted the 512-token
  budget while reasoning before producing a tool call.

The failures are systematic rather than random. They disprove the earlier claim
that tool calling was already flawless on the production-relevant schema.

## Follow-up

Schema descriptions and the development prompt were revised to make source enum
semantics explicit, require immediate tool invocation, and permit a 1,024-token
generation ceiling. A second development run must be archived separately; the
initial report remains unchanged.

## Revised Development Run

The evaluator `1.1` artifact was also deleted during sanitization. Its aggregate
result was 30/30, but it hid explicit default arguments and used an incomplete
per-field denominator. It is superseded by evaluator `1.2`.

| Metric | Result |
|---|---:|
| Overall exact trial accuracy | 30/30 (100%) |
| Tool-call exact accuracy | 21/21 (100%) |
| Expected-field accuracy | 100% |
| Unexpected fields | 0 |
| Abstention accuracy | 9/9 (100%) |
| Malformed or invalid calls | 0 |
| Stable tool outcomes | 10/10 cases |
| Median latency | 1.047 s |
| Observed p95 latency | Superseded |
| Maximum latency | Superseded |

The revised run confirms that explicit enum semantics and prompt instructions
correct the two observed development failures. It is not independent evidence:
the same ten cases identified the failures and measured the fix. A larger locked
release set, adversarial cases, named-place workflow, and degradation tests with
multiple simultaneous tools remain required before a user-visible route.

## Sanitized Development Run

Evaluator `1.2` does not persist model text or reasoning, counts all expected
fields on failed calls, rejects explicit unrequested defaults, uses strict JSON
schema validation, archives prompt/schema/case snapshots, minimizes model
inventory metadata, and uses nearest-rank p95.

**Evaluator:** `1.2`
**Cases:** `1.0`
**Model schema:** `1.2`
**Raw report:** `raw/search_tool_gemma_2026-08-13_v4_sanitized.json`

| Metric | Result |
|---|---:|
| Overall exact trial accuracy | 30/30 (100%) |
| Tool-call exact accuracy | 21/21 (100%) |
| Expected-field accuracy | 100% |
| Unexpected fields | 0 |
| Abstention accuracy | 9/9 (100%) |
| Malformed or invalid calls | 0 |
| Stable scored outputs | 10/10 cases |
| Median latency | 1.046 s |
| Nearest-rank p95 latency | 1.938 s |
| Maximum latency | 3.390 s |

This remains development-set performance. It supports regression testing of the
current prompt and schema but does not establish release accuracy.
