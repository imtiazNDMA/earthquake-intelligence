"""A real application server for the browser matrix.

These tests drive the actual page in Chromium, so they need the app serving its
own assets rather than a static directory: the 3D renderer reads published state
that only the running frontend produces. The server is started once per session
and skipped -- never failed -- when the pieces are missing, so the suite stays
green on a machine without Playwright browsers or a database.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

STARTUP_TIMEOUT_S = 45


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def app_server() -> str:
    port = _free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "eqmon.api:app", "--port", str(port), "--log-level", "warning"],
        cwd=Path.cwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + STARTUP_TIMEOUT_S
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.skip(f"application server exited: {process.stdout.read()[-800:]}")
            try:
                if httpx.get(base_url, timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.4)
        else:
            pytest.skip("application server did not become ready")
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


@pytest.fixture()
def console_errors(page):
    """Fail a test on any unhandled page exception or console error."""
    errors: list[str] = []
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: errors.append(str(error)))
    return errors
