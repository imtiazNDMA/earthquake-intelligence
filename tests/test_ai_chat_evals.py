from eqmon.ai.evals.chat_runner import load_chat_cases, score_chat_transcripts


def test_locked_chat_cases_cover_required_phase_zero_categories():
    cases = load_chat_cases()

    assert len(cases) >= 20
    assert len({case["id"] for case in cases}) == len(cases)
    assert {
        "greeting", "general_explanation", "catalog", "event", "analytics",
        "place", "clarification", "out_of_domain", "adversarial", "safety",
    } <= {case["category"] for case in cases}


def test_chat_scorer_reports_tools_terms_and_categories():
    cases = [
        {
            "id": "tool",
            "category": "catalog",
            "expected_tools": ["search_events"],
            "required_terms": ["three events"],
            "forbidden_terms": ["observed"],
        },
        {
            "id": "direct",
            "category": "greeting",
            "expected_tools": [],
            "required_terms": [],
            "forbidden_terms": ["schema"],
        },
    ]
    report = score_chat_transcripts([
        {"case_id": "tool", "tools_used": ["search_events"],
         "answer": "I found three events in the catalog."},
        {"case_id": "direct", "tools_used": [], "answer": "Hello."},
    ], cases=cases)

    assert report["summary"] == {
        "passed": 2,
        "total": 2,
        "accuracy": 1.0,
        "tool_accuracy": 1.0,
        "argument_accuracy": 1.0,
        "nonempty_answer_accuracy": 1.0,
        "required_term_accuracy": 1.0,
        "forbidden_term_accuracy": 1.0,
    }
    assert report["categories"]["catalog"]["accuracy"] == 1.0


def test_chat_scorer_does_not_retain_answer_text():
    cases = [{
        "id": "private", "category": "adversarial", "expected_tools": [],
        "required_terms": [], "forbidden_terms": [],
    }]
    report = score_chat_transcripts([
        {"case_id": "private", "tools_used": [],
         "answer": "private model output"},
    ], cases=cases)

    assert "private model output" not in str(report)
    assert "answer" not in report["cases"][0]


def test_missing_transcript_fails_all_criteria_explicitly():
    cases = [{
        "id": "missing", "category": "event",
        "expected_tools": ["get_event_summary"],
        "required_terms": [], "forbidden_terms": [],
    }]
    report = score_chat_transcripts([], cases=cases)

    assert report["summary"]["accuracy"] == 0.0
    assert report["cases"][0]["outcome"] == "missing_transcript"
    assert not any(report["cases"][0]["criteria"].values())


def test_empty_answer_fails_even_when_tool_use_matches():
    cases = [{
        "id": "empty", "category": "catalog",
        "expected_tools": ["search_events"],
        "required_terms": [], "forbidden_terms": [],
    }]
    report = score_chat_transcripts([
        {"case_id": "empty", "tools_used": ["search_events"], "answer": ""},
    ], cases=cases)

    assert report["cases"][0]["criteria"]["tool_match"] is True
    assert report["cases"][0]["criteria"]["nonempty_answer"] is False
    assert report["summary"]["accuracy"] == 0.0


def test_scorer_preserves_repeated_trials_and_scores_arguments():
    cases = [{
        "id": "search", "category": "catalog",
        "expected_tools": ["search_events"],
        "expected_arguments": {"search_events": {"min_magnitude": 5.0}},
        "required_terms": [], "forbidden_terms": [],
    }]
    report = score_chat_transcripts([
        {"case_id": "search", "tools_used": ["search_events"],
         "tool_arguments": {"search_events": {"min_magnitude": 5.0}},
         "answer": "Three events."},
        {"case_id": "search", "tools_used": ["search_events"],
         "tool_arguments": {"search_events": {"min_magnitude": 4.0}},
         "answer": "Four events."},
    ], cases=cases)

    assert report["summary"]["total"] == 2
    assert report["summary"]["passed"] == 1
    assert report["summary"]["argument_accuracy"] == 0.5


def test_scorer_rejects_duplicate_cases_and_unknown_transcripts():
    duplicate_cases = [
        {"id": "same", "category": "event", "expected_tools": []},
        {"id": "same", "category": "event", "expected_tools": []},
    ]
    try:
        score_chat_transcripts([], cases=duplicate_cases)
    except ValueError as exc:
        assert "duplicate" in str(exc)
    else:
        raise AssertionError("duplicate case IDs should be rejected")

    cases = [{"id": "known", "category": "event", "expected_tools": []}]
    try:
        score_chat_transcripts([
            {"case_id": "unknown", "tools_used": [], "answer": "No."},
        ], cases=cases)
    except ValueError as exc:
        assert "unknown" in str(exc)
    else:
        raise AssertionError("unknown transcript IDs should be rejected")
