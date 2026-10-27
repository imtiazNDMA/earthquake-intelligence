"""EQ-ARC: MMI exposure analysis toolkit.

Importing this package configures the GDAL/PROJ environment before any
``osgeo`` import happens, so every module can simply ``from osgeo import ogr``.
"""

from .config import configure_gdal

configure_gdal()

__all__ = ["configure_gdal"]
