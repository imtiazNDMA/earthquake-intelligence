"""Evaluation runner for deterministic place-name resolution."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from typing import Iterable, Mapping, Sequence

from eqmon.ai.places import (DEFAULT_AMBIGUITY_THRESHOLD, DEFAULT_MARGIN,
                             DEFAULT_THRESHOLD, BoundaryCandidate, match_name,
                             normalise)

from .place_cases import CORPUS_VERSION, PLACE_CASES

EVALUATOR_VERSION = "1.0"


def evaluate_places(candidates: Sequence[BoundaryCandidate], *,
                    cases: Iterable[Mapping] = PLACE_CASES) -> dict:
    """Score structural exact-name behavior and a labeled noise corpus."""
    by_level: dict[str, list[BoundaryCandidate]] = defaultdict(list)
    normalized_groups: dict[tuple[str, str], list[BoundaryCandidate]] = defaultdict(list)
    global_names: Counter[str] = Counter()
    for candidate in candidates:
        by_level[candidate.level].append(candidate)
        normalized = normalise(candidate.name)
        normalized_groups[(candidate.level, normalized)].append(candidate)
        global_names[normalized] += 1

    exact_results = []
    for (level, normalized), group in sorted(normalized_groups.items()):
        result = match_name(group[0].name, by_level[level])
        expected = "resolved" if len(group) == 1 else "ambiguous"
        passed = result.status == expected
        if expected == "resolved" and result.match is not None:
            passed = passed and result.match.unit_id == group[0].unit_id
        exact_results.append({
            "level": level,
            "normalized_name": normalized,
            "candidate_ids": [candidate.unit_id for candidate in group],
            "expected": expected,
            "actual": result.status,
            "passed": passed,
        })

    labeled_results = []
    for index, case in enumerate(cases, start=1):
        level = str(case["level"])
        result = match_name(
            str(case["probe"]), by_level.get(level, []),
            parent=case.get("parent"),
        )
        expected = str(case["expected"])
        passed = result.status == expected
        if expected == "resolved" and result.match is not None:
            passed = passed and result.match.name == case.get("name")
            if case.get("parent"):
                passed = passed and normalise(result.match.parent or "") == normalise(
                    str(case["parent"]))
        labeled_results.append({
            "case": index,
            "probe": case["probe"],
            "level": level,
            "expected": expected,
            "actual": result.status,
            "matched_id": result.match.unit_id if result.match else None,
            "matched_name": result.match.name if result.match else None,
            "passed": passed,
        })

    exact_passed = sum(result["passed"] for result in exact_results)
    labeled_passed = sum(result["passed"] for result in labeled_results)
    duplicate_names = {name: count for name, count in global_names.items() if count > 1}
    return {
        "evaluator_version": EVALUATOR_VERSION,
        "corpus_version": CORPUS_VERSION,
        "gazetteer_sha256": _gazetteer_hash(candidates),
        "parameters": {
            "similarity_threshold": DEFAULT_THRESHOLD,
            "ambiguity_margin": DEFAULT_MARGIN,
            "ambiguity_threshold": DEFAULT_AMBIGUITY_THRESHOLD,
            "max_typo_edits": {"length_1_4": 1, "length_5_12": 2,
                               "length_13_plus": 3},
        },
        "gazetteer": {
            "rows": len(candidates),
            "levels": dict(sorted(Counter(c.level for c in candidates).items())),
            "duplicate_normalized_names": len(duplicate_names),
            "rows_with_duplicate_names": sum(duplicate_names.values()),
            "max_name_multiplicity": max(duplicate_names.values(), default=0),
        },
        "exact_name": {
            "passed": exact_passed,
            "total": len(exact_results),
            "accuracy": _ratio(exact_passed, len(exact_results)),
            "failures": [result for result in exact_results if not result["passed"]],
        },
        "labeled": {
            "passed": labeled_passed,
            "total": len(labeled_results),
            "accuracy": _ratio(labeled_passed, len(labeled_results)),
            "failures": [result for result in labeled_results if not result["passed"]],
            "results": labeled_results,
        },
    }


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _gazetteer_hash(candidates: Sequence[BoundaryCandidate]) -> str:
    rows = [
        [candidate.unit_id, candidate.name, candidate.level,
         candidate.parent, candidate.division]
        for candidate in sorted(candidates, key=lambda item: item.unit_id)
    ]
    payload = json.dumps(rows, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
