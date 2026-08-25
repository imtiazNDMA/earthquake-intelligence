"""Behavioural tests for the map-mode coordinator (web/map-modes.js).

The coordinator is the seam that keeps camera and analysis state renderer-neutral,
so it is exercised as code rather than matched as text: tests/js/map_modes_harness.js
loads it in a Node VM against stub 2D and 3D renderers and asserts the Phase 2
invariants (no camera drift, one renderer instance, no refetch, JSON-only state).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

HARNESS = Path("tests/js/map_modes_harness.js")


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for the map-mode coordinator harness")
    return node


def test_coordinator_preserves_camera_and_state_across_modes():
    result = subprocess.run(
        [_node(), str(HARNESS)],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "map-modes runtime checks passed" in result.stdout


@pytest.mark.parametrize("module", ["web/map-modes.js", "web/maplibre-3d.js", "web/app.js"])
def test_map_modules_parse(module: str):
    result = subprocess.run(
        [_node(), "--check", module],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
    )
    assert result.returncode == 0, result.stderr
