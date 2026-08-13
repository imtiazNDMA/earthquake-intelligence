"""Deterministic resolution of dirty place text and coordinates.

Coordinates are authoritative for event-to-boundary lookup. Orthographic text
matching corroborates that result or provides a fallback when coordinates are
unavailable. Duplicate administrative names are preserved as separate boundary
candidates and are never resolved by database row order.
"""
from __future__ import annotations

import re
import math
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal, Sequence

import psycopg
from psycopg.rows import dict_row

_SUFFIXES = (
    "sub division", "subdivision", "district", "division", "province",
    "region", "tehsil", "taluka", "agency", "city", "town", "dist", "div",
)
_SUFFIX_RE = re.compile(
    r"(?:\s+|^)(?:" + "|".join(re.escape(value) for value in _SUFFIXES)
    + r")\.?\s*$",
    re.IGNORECASE,
)

DEFAULT_THRESHOLD = 0.62
DEFAULT_MARGIN = 0.05
DEFAULT_AMBIGUITY_THRESHOLD = 0.8
_LEVEL_RANK = {"national": 0, "province": 1, "district": 2, "tehsil": 3}


@dataclass(frozen=True)
class BoundaryCandidate:
    unit_id: int
    name: str
    level: str
    parent: str | None = None
    division: str | None = None
    score: float | None = None


@dataclass(frozen=True)
class PlaceResolution:
    status: Literal["resolved", "ambiguous", "conflict", "not_found"]
    method: Literal["spatial", "text", "spatial+text"] | None
    match: BoundaryCandidate | None = None
    candidates: tuple[BoundaryCandidate, ...] = ()
    margin: float | None = None


def normalise(name: str) -> str:
    """Normalize spelling while removing only trailing admin decorations."""
    if not name:
        return ""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    without_suffix = _SUFFIX_RE.sub("", ascii_only.strip())
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", without_suffix.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def similarity(a: str, b: str) -> float:
    """Orthographic similarity of two normalized names, from 0.0 to 1.0."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def edit_distance(a: str, b: str) -> int:
    """Levenshtein distance, used to reject semantically unrelated names."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for row, char_a in enumerate(a, start=1):
        current = [row]
        for column, char_b in enumerate(b, start=1):
            current.append(min(
                current[-1] + 1,
                previous[column] + 1,
                previous[column - 1] + (char_a != char_b),
            ))
        previous = current
    return previous[-1]


def _max_typo_edits(name: str) -> int:
    length = len(name.replace(" ", ""))
    if length <= 4:
        return 1
    if length <= 12:
        return 2
    return 3


def _with_score(candidate: BoundaryCandidate, score: float) -> BoundaryCandidate:
    return BoundaryCandidate(
        unit_id=candidate.unit_id,
        name=candidate.name,
        level=candidate.level,
        parent=candidate.parent,
        division=candidate.division,
        score=round(score, 4),
    )


def match_name(probe: str, candidates: Sequence[BoundaryCandidate], *,
               parent: str | None = None,
               threshold: float = DEFAULT_THRESHOLD,
               margin: float = DEFAULT_MARGIN,
               ambiguity_threshold: float = DEFAULT_AMBIGUITY_THRESHOLD,
               ) -> PlaceResolution:
    """Resolve text only when one boundary candidate is clearly best."""
    probe_n = normalise(probe)
    if not probe_n or not candidates:
        return PlaceResolution("not_found", None)

    parent_n = normalise(parent or "")
    eligible = [
        candidate for candidate in candidates
        if not parent_n or normalise(candidate.parent or "") == parent_n
    ]
    if not eligible:
        return PlaceResolution("not_found", "text")

    scored = sorted(
        ((_with_score(candidate, similarity(probe_n, normalise(candidate.name))))
         for candidate in eligible),
        key=lambda candidate: (-float(candidate.score), candidate.unit_id),
    )
    best_score = float(scored[0].score)
    best_edit_distance = edit_distance(probe_n, normalise(scored[0].name))
    if best_score < threshold or best_edit_distance > _max_typo_edits(scored[0].name):
        return PlaceResolution("not_found", "text", candidates=tuple(scored[:3]))

    tied = tuple(candidate for candidate in scored
                 if abs(float(candidate.score) - best_score) < margin)
    runner_up = float(scored[1].score) if len(scored) > 1 else 0.0
    gap = round(best_score - runner_up, 4)
    if len(tied) > 1:
        if best_score < ambiguity_threshold:
            return PlaceResolution(
                "not_found", "text", candidates=tied, margin=gap,
            )
        return PlaceResolution(
            "ambiguous", "text", candidates=tied, margin=gap,
        )
    return PlaceResolution(
        "resolved", "text", match=scored[0], candidates=(scored[0],), margin=gap,
    )


def load_gazetteer(conn: psycopg.Connection,
                   level: str | None = None) -> list[BoundaryCandidate]:
    """Load boundaries as records so duplicate names remain distinct."""
    sql = "SELECT id, name, level, parent, division FROM admin_boundary"
    params: tuple = ()
    if level:
        sql += " WHERE level = %s"
        params = (level,)
    sql += " ORDER BY id"
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return [BoundaryCandidate(
            unit_id=row["id"], name=row["name"], level=row["level"],
            parent=row["parent"], division=row["division"],
        ) for row in cur.fetchall()]


def boundaries_at(conn: psycopg.Connection, lon: float, lat: float, *,
                  level: str | None = None) -> list[BoundaryCandidate]:
    """All boundaries covering a WGS84 point, including shared polygon edges."""
    sql = (
        "SELECT id, name, level, parent, division FROM admin_boundary "
        "WHERE ST_Covers(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))"
    )
    params: list = [lon, lat]
    if level:
        sql += " AND level = %s"
        params.append(level)
    sql += " ORDER BY id"
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return [BoundaryCandidate(
            unit_id=row["id"], name=row["name"], level=row["level"],
            parent=row["parent"], division=row["division"],
        ) for row in cur.fetchall()]


def resolve_place(conn: psycopg.Connection, probe: str = "", *,
                  lon: float | None = None, lat: float | None = None,
                  level: str | None = None, parent: str | None = None,
                  threshold: float = DEFAULT_THRESHOLD) -> PlaceResolution:
    """Resolve coordinates first, using place text as corroboration or fallback."""
    if (lon is None) != (lat is None):
        raise ValueError("lon and lat must be provided together")
    if lon is not None and (not math.isfinite(lon) or not -180 <= lon <= 180):
        raise ValueError("lon must be finite and between -180 and 180")
    if lat is not None and (not math.isfinite(lat) or not -90 <= lat <= 90):
        raise ValueError("lat must be finite and between -90 and 90")

    gazetteer = load_gazetteer(conn, level)
    text = match_name(probe, gazetteer, parent=parent, threshold=threshold)
    if lon is None:
        return text

    spatial = boundaries_at(conn, lon, lat, level=level)
    if not spatial:
        candidates = text.candidates if text.status in {"resolved", "ambiguous"} else ()
        return PlaceResolution("conflict" if candidates else "not_found",
                               "spatial+text" if candidates else "spatial",
                               candidates=candidates, margin=text.margin)
    if level is None:
        most_specific = max(_LEVEL_RANK.get(candidate.level, -1)
                            for candidate in spatial)
        spatial = [candidate for candidate in spatial
                   if _LEVEL_RANK.get(candidate.level, -1) == most_specific]
    if len(spatial) > 1:
        if text.status == "resolved":
            matching = [candidate for candidate in spatial
                        if candidate.unit_id == text.match.unit_id]
            if matching:
                match = _with_score(matching[0], float(text.match.score))
                return PlaceResolution(
                    "resolved", "spatial+text", match=match,
                    candidates=(match,), margin=text.margin,
                )
        return PlaceResolution("ambiguous", "spatial", candidates=tuple(spatial))

    spatial_match = spatial[0]
    if text.status == "ambiguous":
        corroborating = [candidate for candidate in text.candidates
                         if candidate.unit_id == spatial_match.unit_id]
        if corroborating:
            match = corroborating[0]
            return PlaceResolution(
                "resolved", "spatial+text", match=match,
                candidates=(match,), margin=text.margin,
            )
        return PlaceResolution(
            "conflict", "spatial+text",
            candidates=(spatial_match, *text.candidates), margin=text.margin,
        )
    if text.status != "resolved":
        return PlaceResolution(
            "resolved", "spatial", match=spatial_match,
            candidates=(spatial_match,),
        )
    if text.match.unit_id == spatial_match.unit_id:
        corroborated = _with_score(spatial_match, float(text.match.score))
        return PlaceResolution(
            "resolved", "spatial+text", match=corroborated,
            candidates=(corroborated,), margin=text.margin,
        )
    return PlaceResolution(
        "conflict", "spatial+text",
        candidates=(spatial_match, text.match), margin=text.margin,
    )
