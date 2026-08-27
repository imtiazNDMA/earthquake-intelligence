"""Deterministic scoring for versioned agent-chat evaluation cases."""
from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path

CASESET_VERSION = "1.0"
EVALUATOR_VERSION = "1.0"
DEFAULT_CASES_PATH = Path(__file__).with_name("chat_cases_v1.json")


def load_chat_cases(path: Path = DEFAULT_CASES_PATH) -> list[dict]:
    """Load the locked case snapshot used by the chat evaluator."""
    with path.open(encoding="utf-8") as handle:
        cases = json.load(handle)
    if not isinstance(cases, list):
        raise ValueError("chat cases must be a JSON array")
    _validate_cases(cases)
    return cases


def score_chat_transcripts(
    transcripts: Iterable[Mapping], *, cases: Iterable[Mapping] | None = None,
) -> dict:
    """Score sanitized outputs without persisting prompts or model reasoning."""
    case_list = list(cases if cases is not None else load_chat_cases())
    _validate_cases(case_list)
    transcript_list = list(transcripts)
    _validate_transcripts(transcript_list, {str(case["id"]) for case in case_list})
    transcripts_by_id: dict[str, list[Mapping]] = {}
    for transcript in transcript_list:
        transcripts_by_id.setdefault(str(transcript["case_id"]), []).append(transcript)
    results = [
        _score_case(case, transcript)
        for case in case_list
        for transcript in transcripts_by_id.get(str(case["id"]), [None])
    ]
    category_totals = Counter(result["category"] for result in results)
    category_passed = Counter(result["category"] for result in results
                              if result["passed"])
    passed = sum(result["passed"] for result in results)
    return {
        "evaluator_version": EVALUATOR_VERSION,
        "caseset_version": CASESET_VERSION,
        "summary": {
            "passed": passed,
            "total": len(results),
            "accuracy": _ratio(passed, len(results)),
            "tool_accuracy": _criterion_accuracy(results, "tool_match"),
            "argument_accuracy": _criterion_accuracy(results, "argument_match"),
            "nonempty_answer_accuracy": _criterion_accuracy(
                results, "nonempty_answer"),
            "required_term_accuracy": _criterion_accuracy(
                results, "required_terms_present"),
            "forbidden_term_accuracy": _criterion_accuracy(
                results, "forbidden_terms_absent"),
        },
        "categories": {
            category: {
                "passed": category_passed[category],
                "total": total,
                "accuracy": _ratio(category_passed[category], total),
            }
            for category, total in sorted(category_totals.items())
        },
        "cases": results,
    }


def _score_case(case: Mapping, transcript: Mapping | None) -> dict:
    expected_tools = list(case.get("expected_tools", []))
    required_terms = [str(term).casefold()
                      for term in case.get("required_terms", [])]
    forbidden_terms = [str(term).casefold()
                       for term in case.get("forbidden_terms", [])]
    expected_arguments = case.get("expected_arguments", {})
    if transcript is None:
        criteria = {
            "tool_match": False,
            "argument_match": False,
            "nonempty_answer": False,
            "required_terms_present": False,
            "forbidden_terms_absent": False,
        }
        outcome = "missing_transcript"
    else:
        answer = str(transcript.get("answer", "")).casefold()
        actual_tools = list(transcript.get("tools_used", []))
        actual_arguments = transcript.get("tool_arguments", {})
        criteria = {
            "tool_match": actual_tools == expected_tools,
            "argument_match": all(
                actual_arguments.get(tool) == arguments
                for tool, arguments in expected_arguments.items()),
            "nonempty_answer": bool(answer.strip()),
            "required_terms_present": all(term in answer
                                          for term in required_terms),
            "forbidden_terms_absent": all(term not in answer
                                         for term in forbidden_terms),
        }
        outcome = "passed" if all(criteria.values()) else "failed"
    return {
        "case_id": str(case["id"]),
        "category": str(case["category"]),
        "passed": all(criteria.values()),
        "outcome": outcome,
        "criteria": criteria,
    }


def _criterion_accuracy(results: list[dict], criterion: str) -> float:
    return _ratio(sum(result["criteria"][criterion] for result in results),
                  len(results))


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _validate_cases(cases: list[Mapping]) -> None:
    ids: set[str] = set()
    for case in cases:
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("each chat case requires a non-empty string id")
        if case_id in ids:
            raise ValueError(f"duplicate chat case id: {case_id}")
        ids.add(case_id)
        if not isinstance(case.get("category"), str):
            raise ValueError(f"case {case_id} requires a category")
        for field in ("expected_tools", "required_terms", "forbidden_terms"):
            value = case.get(field, [])
            if not isinstance(value, list) or not all(isinstance(item, str)
                                                     for item in value):
                raise ValueError(f"case {case_id} has invalid {field}")
        expected_arguments = case.get("expected_arguments", {})
        if not isinstance(expected_arguments, dict):
            raise ValueError(f"case {case_id} has invalid expected_arguments")


def _validate_transcripts(transcripts: list[Mapping], case_ids: set[str]) -> None:
    for transcript in transcripts:
        case_id = transcript.get("case_id")
        if not isinstance(case_id, str) or case_id not in case_ids:
            raise ValueError(f"unknown chat case id: {case_id!r}")
        tools = transcript.get("tools_used", [])
        if not isinstance(tools, list) or not all(isinstance(tool, str)
                                                 for tool in tools):
            raise ValueError(f"transcript {case_id} has invalid tools_used")
        if not isinstance(transcript.get("answer", ""), str):
            raise ValueError(f"transcript {case_id} has invalid answer")
        if not isinstance(transcript.get("tool_arguments", {}), dict):
            raise ValueError(f"transcript {case_id} has invalid tool_arguments")
