"""Run the live LM Studio `search_events` capability benchmark."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from eqmon.ai import config
from eqmon.ai.client import LMStudio
from eqmon.ai.evals.search_tools import (fetch_model_metadata,
                                         run_search_tool_benchmark)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=config.MODEL_PRIMARY)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")

    report = run_search_tool_benchmark(
        client=LMStudio(), model=args.model, repeats=args.repeats,
        model_metadata=fetch_model_metadata(args.model),
    )
    rendered = json.dumps(report, indent=2, ensure_ascii=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
