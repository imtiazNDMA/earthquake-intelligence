"""Live capability runner for the `search_events` tool."""
from __future__ import annotations

import hashlib
import json
import math
import platform
from datetime import datetime, timezone
from statistics import median
from typing import Iterable, Mapping

import httpx
from pydantic import ValidationError

from eqmon.ai import config
from eqmon.ai.client import (LMStudio, LMStudioError, Message,
                             UnofferedToolError)
from eqmon.ai.tools import SEARCH_EVENTS_TOOL_NAME, search_events_tool
from eqmon.events.search import EventSearchSpec

from .search_cases import CASESET_VERSION, SEARCH_CASES

EVALUATOR_VERSION = "1.3"
SYSTEM_PROMPT = """You translate earthquake catalog requests into tool calls.
Call search_events only for earthquake catalog searches. Extract only constraints
the user explicitly states. Use ISO 8601 datetimes with a timezone offset. Do
not infer coordinates for place names. Source values are uppercase PMD, USGS,
and MANUAL; "manual" or "manually entered" means MANUAL. For a catalog search,
call the tool immediately without explaining your reasoning. If the request is
not an earthquake catalog search, answer normally and do not call a tool."""


def run_search_tool_benchmark(*, client: LMStudio, model: str,
                              repeats: int = 3,
                              cases: Iterable[Mapping] = SEARCH_CASES,
                              model_metadata: Mapping | None = None) -> dict:
    """Run repeated live trials and return raw results plus exact scores."""
    case_list = list(cases)
    tool = search_events_tool()
    trials = []
    for case in case_list:
        for repeat in range(1, repeats + 1):
            trials.append(_run_trial(client, model, case, repeat, tool))

    passed = sum(trial["passed"] for trial in trials)
    tool_trials = [trial for trial in trials if trial["expected_kind"] == "tool"]
    abstain_trials = [trial for trial in trials
                      if trial["expected_kind"] == "abstain"]
    latencies = [trial["latency_s"] for trial in trials
                 if trial["latency_s"] is not None]
    expected_fields = sum(len(trial["expected"]) for trial in tool_trials)
    correct_fields = sum(
        sum(fields.values()) for fields in
        (trial.get("field_results") or {} for trial in tool_trials)
    )
    return {
        "evaluator_version": EVALUATOR_VERSION,
        "caseset_version": CASESET_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_requested": model,
        "model_metadata": dict(model_metadata or {}),
        "environment": {"python": platform.python_version(),
                        "platform": platform.platform()},
        "repeats": repeats,
        "hashes": {
            "system_prompt_sha256": _hash(SYSTEM_PROMPT),
            "tool_schema_sha256": _hash(tool),
            "cases_sha256": _hash(case_list),
        },
        "snapshots": {
            "system_prompt": SYSTEM_PROMPT,
            "tool_schema": tool,
            "cases": case_list,
        },
        "summary": {
            "passed": passed,
            "total": len(trials),
            "accuracy": _ratio(passed, len(trials)),
            "tool_accuracy": _accuracy(tool_trials),
            "expected_field_accuracy": _ratio(correct_fields, expected_fields),
            "unexpected_fields": sum(len(trial.get("unexpected_fields") or [])
                                     for trial in tool_trials),
            "abstention_accuracy": _accuracy(abstain_trials),
            "malformed_or_invalid": sum(
                trial["outcome"] in {"client_error", "invalid_arguments"}
                for trial in trials
            ),
            "latency_s": _latency_summary(latencies),
        },
        "case_summary": _case_summary(case_list, trials),
        "repeatability": _repeatability(case_list, trials),
        "trials": trials,
    }


def fetch_model_metadata(model: str,
                         base_url: str = config.LMSTUDIO_BASE_URL) -> dict:
    """Metadata LM Studio exposes; unavailable version/checksum stays explicit."""
    root = base_url.removesuffix("/v1")
    metadata: dict = {"lm_studio_version": None, "artifact_checksum": None}
    try:
        response = httpx.get(f"{root}/api/v0/models", timeout=10.0)
        response.raise_for_status()
        models = response.json().get("data", [])
        metadata["model"] = next(
            (item for item in models if item.get("id") == model), None)
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        metadata["metadata_error"] = str(exc)
    return metadata


def _run_trial(client: LMStudio, model: str, case: Mapping, repeat: int,
               tool: dict) -> dict:
    expected = case.get("expected")
    base = {
        "case_id": case["id"], "repeat": repeat, "query": case["query"],
        "expected_kind": "abstain" if expected is None else "tool",
        "expected": expected,
    }
    try:
        completion = client.chat(
            [Message.system(SYSTEM_PROMPT), Message.user(str(case["query"]))],
            model=model, tools=[tool], temperature=0, max_tokens=1024,
        )
    except UnofferedToolError as exc:
        # A hallucinated tool name is a model failure, not a transport one. The
        # client refuses it before it can be dispatched, so the harness scores
        # it here rather than in the wrong_tool branch below.
        return {**base, "passed": False, "outcome": "wrong_tool",
                "error_code": type(exc).__name__, "latency_s": None, "actual": None,
                "actual_raw": str(exc), "field_results": (
                    {key: False for key in expected} if expected is not None else None),
                "unexpected_fields": [] if expected is not None else None,
                "usage": {}}
    except LMStudioError as exc:
        return {**base, "passed": False, "outcome": "client_error",
                "error_code": type(exc).__name__, "latency_s": None, "actual": None,
                "actual_raw": None, "field_results": (
                    {key: False for key in expected} if expected is not None else None),
                "unexpected_fields": [] if expected is not None else None,
                "usage": {}}

    actual = None
    actual_raw = None
    field_results = ({key: False for key in expected} if expected is not None
                     else None)
    unexpected_fields = [] if expected is not None else None
    outcome = "abstained" if not completion.tool_calls else "called_tool"
    error_code = None
    if expected is None:
        passed = not completion.tool_calls
    elif len(completion.tool_calls) != 1:
        passed = False
        outcome = "wrong_tool_count"
        actual_raw = [{"name": call.name, "arguments": call.arguments}
                      for call in completion.tool_calls]
    else:
        call = completion.tool_calls[0]
        if call.name != SEARCH_EVENTS_TOOL_NAME:
            passed = False
            outcome = "wrong_tool"
            actual_raw = {"name": call.name, "arguments": call.arguments}
        else:
            actual_raw = call.arguments
            unexpected_fields = sorted(set(call.arguments) - set(expected))
            try:
                spec = EventSearchSpec.model_validate_json(
                    json.dumps(call.arguments), strict=True)
                actual_all = spec.model_dump(mode="json")
                actual = {key: actual_all[key] for key in call.arguments}
                field_results = {
                    key: actual.get(key) == value for key, value in expected.items()
                }
                passed = all(field_results.values()) and not unexpected_fields
                outcome = "exact" if passed else "argument_mismatch"
            except ValidationError:
                passed = False
                outcome = "invalid_arguments"
                actual = call.arguments
                error_code = "validation_error"
    return {
        **base, "passed": passed, "outcome": outcome, "actual": actual,
        "actual_raw": actual_raw,
        "field_results": field_results, "unexpected_fields": unexpected_fields,
        "error_code": error_code, "latency_s": completion.latency_s,
        "model_returned": completion.model,
        "usage": completion.usage,
    }


def _case_summary(cases: list[Mapping], trials: list[dict]) -> list[dict]:
    return [{
        "case_id": case["id"],
        "passed": sum(t["passed"] for t in trials if t["case_id"] == case["id"]),
        "total": sum(1 for t in trials if t["case_id"] == case["id"]),
        "outcomes": sorted({t["outcome"] for t in trials
                            if t["case_id"] == case["id"]}),
    } for case in cases]


def _repeatability(cases: list[Mapping], trials: list[dict]) -> dict:
    stable = 0
    details = []
    for case in cases:
        case_trials = [trial for trial in trials if trial["case_id"] == case["id"]]
        signatures = {
            json.dumps({"outcome": trial["outcome"],
                        "actual_raw": trial.get("actual_raw"),
                        "error_code": trial.get("error_code")},
                       sort_keys=True, default=str)
            for trial in case_trials
        }
        is_stable = len(signatures) == 1
        stable += is_stable
        details.append({"case_id": case["id"], "stable": is_stable,
                        "distinct_outputs": len(signatures)})
    return {"stable_cases": stable, "total_cases": len(cases),
            "rate": _ratio(stable, len(cases)), "cases": details}


def _accuracy(trials: list[dict]) -> float:
    return _ratio(sum(trial["passed"] for trial in trials), len(trials))


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _latency_summary(values: list[float]) -> dict:
    if not values:
        return {"min": None, "median": None, "p95": None, "max": None}
    ordered = sorted(values)
    p95_index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1))
    return {"min": ordered[0], "median": round(median(ordered), 3),
            "p95": ordered[p95_index], "max": ordered[-1]}


def _hash(value) -> str:
    payload = value if isinstance(value, str) else json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
