"""Ensure PROJ is pinned to rasterio's bundled DB before any geospatial import.

Importing the package runs eqmon._proj (see src/eqmon/_proj.py), the single
source of truth for this fix — shared by the test suite and the running app.
"""
import eqmon  # noqa: F401 — import side effect: pins PROJ_DATA/PROJ_LIB
