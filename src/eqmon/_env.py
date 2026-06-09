"""Load a local `.env` file into os.environ (if present).

Plain KEY=VALUE lines, `#` comments ignored. Uses setdefault so a real
environment variable always wins over the file. Imported by eqmon/__init__ so
both the running service and the test suite pick up DATABASE_URL /
DATABASE_URL_TEST without depending on env-var inheritance across processes.

Dependency-free on purpose (no python-dotenv).
"""
from __future__ import annotations

import os
from pathlib import Path

_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def load_dotenv(path: Path = _ENV_PATH) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


load_dotenv()
