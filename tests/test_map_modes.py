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

HARNESSES = {
    "coordinator": (Path("tests/js/map_modes_harness.js"), "map-modes runtime checks passed"),
    "renderer": (Path("tests/js/maplibre_3d_harness.js"), "maplibre-3d runtime checks passed"),
}


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for the map harnesses")
    return node


@pytest.mark.parametrize("name", sorted(HARNESSES))
def test_map_harness_invariants_hold(name: str):
    harness, banner = HARNESSES[name]
    result = subprocess.run(
        [_node(), str(harness)],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert banner in result.stdout


@pytest.mark.parametrize("module", ["web/map-modes.js", "web/maplibre-3d.js", "web/map-style-config.js", "web/app.js"])
def test_map_modules_parse(module: str):
    result = subprocess.run(
        [_node(), "--check", module],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
    )
    assert result.returncode == 0, result.stderr
