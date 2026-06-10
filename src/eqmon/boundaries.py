"""Pure field-mapping from each boundary shapefile's properties to
admin_boundary columns. No I/O — unit-testable in isolation.

Field names are the shapefile DBF column names confirmed via fiona; the DBF
format truncates names to 10 chars, which is why e.g. the national name column
is ``Admin01_Na``."""
from __future__ import annotations

# level -> {column: source DBF field name (or None if absent for this level)}
_LEVEL_FIELDS: dict[str, dict[str, str | None]] = {
    "national": {"name": "Admin01_Na", "parent": None,       "division": None,       "population": None},
    "province": {"name": "Province",   "parent": None,       "division": None,       "population": None},
    "district": {"name": "Districts",  "parent": "province", "division": "division", "population": "Population"},
    "tehsil":   {"name": "name",       "parent": "district", "division": "division", "population": None},
}


def map_feature(level: str, props: dict) -> dict:
    """Map one shapefile feature's properties to admin_boundary column values."""
    if level not in _LEVEL_FIELDS:
        raise ValueError(f"unknown level: {level!r}")
    fields = _LEVEL_FIELDS[level]

    def src(col: str):
        field = fields[col]
        return props.get(field) if field is not None else None

    name = src("name")
    if name in (None, ""):
        raise ValueError(f"feature missing name field {fields['name']!r} for level {level!r}")
    population = src("population")
    parent = src("parent")
    division = src("division")
    return {
        "level": level,
        "name": str(name),
        "parent": str(parent) if parent is not None else None,
        "division": str(division) if division is not None else None,
        "population": float(population) if population not in (None, "") else None,
    }
