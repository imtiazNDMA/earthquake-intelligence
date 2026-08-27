from eqmon.ai.evals.places import evaluate_places
from eqmon.ai.places import BoundaryCandidate


def test_evaluator_separates_unique_and_ambiguous_exact_names():
    candidates = [
        BoundaryCandidate(1, "Quetta", "district", "Balochistan"),
        BoundaryCandidate(2, "Khanpur", "tehsil", "Haripur"),
        BoundaryCandidate(3, "Khanpur", "tehsil", "Shikarpur"),
    ]
    cases = [
        {"probe": "Kwetta", "level": "district", "expected": "resolved",
         "name": "Quetta", "parent": "Balochistan"},
        {"probe": "Khanpur", "level": "tehsil", "expected": "ambiguous"},
        {"probe": "Atlantis", "level": "district", "expected": "not_found"},
    ]
    report = evaluate_places(candidates, cases=cases)

    assert report["exact_name"]["accuracy"] == 1.0
    assert report["labeled"]["accuracy"] == 1.0
    assert report["gazetteer"]["duplicate_normalized_names"] == 1
    assert len(report["gazetteer_sha256"]) == 64
    assert report["parameters"]["similarity_threshold"] == 0.62


def test_evaluator_reports_failures_instead_of_hiding_them():
    candidates = [BoundaryCandidate(1, "Quetta", "district", "Balochistan")]
    report = evaluate_places(candidates, cases=[
        {"probe": "Quetta", "level": "district", "expected": "not_found"},
    ])
    assert report["labeled"]["accuracy"] == 0.0
    assert report["labeled"]["failures"][0]["actual"] == "resolved"
