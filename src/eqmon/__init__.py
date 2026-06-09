"""Earthquake intensity platform — engine and map service."""

# Pin PROJ to rasterio's bundled DB before any rasterio/pyproj import. Must run
# first so the running service and tests both avoid a stale system proj.db.
from . import _proj as _proj  # noqa: E402,F401
