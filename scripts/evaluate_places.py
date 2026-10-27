"""Evaluate place resolution against the loaded boundary gazetteer."""
from __future__ import annotations

import json

from eqmon import db
from eqmon.ai.evals.places import evaluate_places
from eqmon.ai.places import load_gazetteer


def main() -> None:
    with db.get_conn() as conn:
        report = evaluate_places(load_gazetteer(conn))
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
