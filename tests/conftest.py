"""pytest configuration: fix PROJ_DATA to use rasterio's bundled database,
preventing conflicts with system-installed PROJ (e.g., PostgreSQL/PostGIS)."""
import os
from importlib.resources import files


def pytest_configure(config):
    """Set PROJ_DATA before any rasterio/pyproj import can pick up a stale DB."""
    try:
        import rasterio  # noqa: F401 — ensure the package is importable first
        proj_data = str(files("rasterio").joinpath("proj_data"))
        os.environ.setdefault("PROJ_DATA", proj_data)
        os.environ.setdefault("PROJ_LIB", proj_data)
    except Exception:
        pass  # if rasterio isn't installed yet, let the test fail naturally
