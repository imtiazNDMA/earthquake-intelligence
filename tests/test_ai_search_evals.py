from eqmon.ai.client import Completion, ToolCall
from eqmon.ai.evals.search_tools import run_search_tool_benchmark
from eqmon.ai.tools import search_events_tool


class FakeClient:
    def __init__(self, completions):
        self.completions = iter(completions)

    def chat(self, *args, **kwargs):
        return next(self.completions)


def completion(*, calls=None, text=""):
    return Completion(text=text, tool_calls=calls or [], model="fake",
                      usage={"total_tokens": 1}, latency_s=1.0)


def test_search_tool_schema_is_strict_event_search_contract():
    tool = search_events_tool()
    parameters = tool["function"]["parameters"]
    assert tool["function"]["name"] == "search_events"
    assert parameters["additionalProperties"] is False
    assert "radius_km" in parameters["properties"]


def test_benchmark_scores_exact_tool_call_and_abstention():
    cases = [
        {"id": "tool", "query": "M5+", "expected": {"min_magnitude": 5.0}},
        {"id": "abstain", "query": "Capital of France?", "expected": None},
    ]
    fake = FakeClient([
        completion(calls=[ToolCall("1", "search_events", {"min_magnitude": 5})]),
        completion(text="Paris"),
    ])
    report = run_search_tool_benchmark(client=fake, model="fake", repeats=1,
                                       cases=cases)
    assert report["summary"]["accuracy"] == 1.0
    assert report["summary"]["tool_accuracy"] == 1.0
    assert report["summary"]["expected_field_accuracy"] == 1.0
    assert report["summary"]["abstention_accuracy"] == 1.0
    assert report["repeatability"]["rate"] == 1.0


def test_benchmark_rejects_extra_or_wrong_arguments():
    cases = [{"id": "tool", "query": "M5+",
              "expected": {"min_magnitude": 5.0}}]
    fake = FakeClient([completion(calls=[ToolCall(
        "1", "search_events", {"min_magnitude": 5, "limit": 50})])])
    report = run_search_tool_benchmark(client=fake, model="fake", repeats=1,
                                       cases=cases)
    assert report["summary"]["accuracy"] == 0.0
    assert report["summary"]["expected_field_accuracy"] == 1.0
    assert report["summary"]["unexpected_fields"] == 1
    assert report["trials"][0]["outcome"] == "argument_mismatch"


def test_benchmark_rejects_explicit_unrequested_defaults():
    cases = [{"id": "tool", "query": "M5+",
              "expected": {"min_magnitude": 5.0}}]
    fake = FakeClient([completion(calls=[ToolCall(
        "1", "search_events", {"min_magnitude": 5, "limit": 20})])])
    report = run_search_tool_benchmark(client=fake, model="fake", repeats=1,
                                       cases=cases)
    assert report["summary"]["accuracy"] == 0.0
    assert report["summary"]["unexpected_fields"] == 1


def test_requested_value_equal_to_default_scores_exact():
    cases = [{"id": "tool", "query": "Return 20 newest events",
              "expected": {"limit": 20, "orderby": "time"}}]
    fake = FakeClient([completion(calls=[ToolCall(
        "1", "search_events", {"limit": 20, "orderby": "time"})])])
    report = run_search_tool_benchmark(client=fake, model="fake", repeats=1,
                                       cases=cases)
    assert report["summary"]["accuracy"] == 1.0


def test_failed_call_counts_expected_fields_as_incorrect():
    cases = [{"id": "tool", "query": "M5+ USGS",
              "expected": {"min_magnitude": 5.0, "source": "USGS"}}]
    fake = FakeClient([completion()])
    report = run_search_tool_benchmark(client=fake, model="fake", repeats=1,
                                       cases=cases)
    assert report["summary"]["expected_field_accuracy"] == 0.0


def test_report_does_not_persist_model_text_or_reasoning():
    cases = [{"id": "abstain", "query": "Capital?", "expected": None}]
    fake = FakeClient([completion(text="private reasoning")])
    report = run_search_tool_benchmark(client=fake, model="fake", repeats=1,
                                       cases=cases)
    assert "text" not in report["trials"][0]
    assert "private reasoning" not in str(report)


def test_numeric_strings_are_not_scored_as_exact_schema_adherence():
    cases = [{"id": "tool", "query": "M5+",
              "expected": {"min_magnitude": 5.0}}]
    fake = FakeClient([completion(calls=[ToolCall(
        "1", "search_events", {"min_magnitude": "5"})])])
    report = run_search_tool_benchmark(client=fake, model="fake", repeats=1,
                                       cases=cases)
    assert report["summary"]["accuracy"] == 0.0
    assert report["trials"][0]["outcome"] == "invalid_arguments"
