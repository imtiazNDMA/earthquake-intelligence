"""Resolve a dirty place name to an admin_boundary unit.

The PMD feed is dirty (see CLAUDE.md): `parse_met()` already defensively parses
hemisphere-suffixed coordinates and skips unparseable rows. Place names carry
the same noise — spelling variants, administrative suffixes, punctuation — and
exact matching against `admin_boundary` silently misses them.

**No model is involved.** This started as an embeddings task and the measurement
killed that idea: against a 12-name Pakistani gazetteer with 7 realistic
variants, `nomic-embed-text-v1.5` scored 6/7 while stdlib `difflib` scored 7/7,
with much wider margins (0.29-0.48 vs 0.007-0.38). The embedding failure is the
instructive one — it matched "Peshwar" to "Khuzdar", 700 km away, on a margin of
+0.007. Embeddings encode *semantic* similarity and every Pakistani city name is
semantically similar to every other; a misspelling is *orthographic* variation.
Wrong tool.

So this module needs no GPU, no network, and no LM Studio. It is deterministic
and microseconds-fast, which also means it can sit in the ingest path without
putting inference on the critical path.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

import psycopg
from psycopg.rows import dict_row

# Administrative decorations that carry no identifying information. Stripped
# before comparison so "Rawalpindi Dist." and "Rawalpindi" are the same string
# rather than a 0.48-ratio near-miss.
_SUFFIXES = (
    "district", "dist", "division", "div", "tehsil", "taluka", "city",
    "town", "agency", "sub division", "subdivision", "province", "region",
)
_SUFFIX_RE = re.compile(r"\b(" + "|".join(_SUFFIXES) + r")\b\.?", re.IGNORECASE)

# Confidence floor for an automatic match. Below this the name goes to a human
# rather than being guessed at — this module feeds a review queue, and a
# confident wrong answer is worse for that queue than an admitted unknown.
#
# Set at the midpoint of a measured separation: across 8 realistic variants and
# 7 unrelated names, true matches bottomed out at 0.667 ("Kwetta"/"Quetta", a
# first-character substitution — the hardest case for any string metric) while
# false matches topped out at 0.545 ("Kabul"/"Skardu").
#
# CAVEAT: tuned against a 12-name sample. The full gazetteer is ~161 districts
# plus tehsils, and denser name spaces push the false-match ceiling up. Re-tune
# against the real table before trusting this in ingest — the margin check below
# is the second line of defence in the meantime.
DEFAULT_THRESHOLD = 0.62

# A match this much better than the runner-up is unambiguous. When two
# candidates are near-tied the name is genuinely ambiguous ("Khairpur" exists in
# both Sindh and KP) and deserves a human, however high the top score.
DEFAULT_MARGIN = 0.05


@dataclass(frozen=True)
class PlaceMatch:
    name: str
    score: float
    margin: float
    unit_id: int | None = None
    level: str | None = None


def normalise(name: str) -> str:
    """Lowercase, strip accents, drop admin suffixes and punctuation.

    Applied identically to both sides of every comparison, so the gazetteer and
    the incoming name are always normalised the same way.
    """
    if not name:
        return ""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    without_suffix = _SUFFIX_RE.sub(" ", ascii_only)
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", without_suffix.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def similarity(a: str, b: str) -> float:
    """Orthographic similarity of two already-normalised names, 0.0-1.0."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def match_name(probe: str, candidates: dict[str, object] | list[str], *,
               threshold: float = DEFAULT_THRESHOLD,
               margin: float = DEFAULT_MARGIN) -> PlaceMatch | None:
    """Best candidate for `probe`, or None when it is not confident enough.

    `candidates` may be a list of names or a name -> payload mapping (the
    mapping form is how the DB-backed caller carries unit ids through).

    Returns None in two distinct situations, both of which mean "ask a human":
    the best score is below `threshold`, or the top two are within `margin` of
    each other and the name is therefore ambiguous.
    """
    names = list(candidates)
    if not names or not probe:
        return None

    probe_n = normalise(probe)
    if not probe_n:
        return None

    scored = sorted(((similarity(probe_n, normalise(n)), n) for n in names),
                    key=lambda pair: (-pair[0], pair[1]))
    best_score, best_name = scored[0]
    runner_up = scored[1][0] if len(scored) > 1 else 0.0
    gap = best_score - runner_up

    if best_score < threshold or (len(scored) > 1 and gap < margin):
        return None

    payload = candidates[best_name] if isinstance(candidates, dict) else None
    unit_id = level = None
    if isinstance(payload, dict):
        unit_id, level = payload.get("id"), payload.get("level")

    return PlaceMatch(name=best_name, score=round(best_score, 4),
                      margin=round(gap, 4), unit_id=unit_id, level=level)


def load_gazetteer(conn: psycopg.Connection,
                   level: str | None = None) -> dict[str, dict]:
    """Every admin_boundary name -> {id, level}, optionally one level only.

    Cheap enough to call per ingest batch (a few thousand rows, names only, no
    geometry), so there is no cache to invalidate.
    """
    sql = "SELECT id, name, level FROM admin_boundary"
    params: tuple = ()
    if level:
        sql += " WHERE level = %s"
        params = (level,)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return {r["name"]: {"id": r["id"], "level": r["level"]} for r in cur.fetchall()}


def resolve_place(conn: psycopg.Connection, probe: str, *, level: str | None = None,
                  threshold: float = DEFAULT_THRESHOLD) -> PlaceMatch | None:
    """Resolve one dirty place name against admin_boundary."""
    return match_name(probe, load_gazetteer(conn, level), threshold=threshold)
