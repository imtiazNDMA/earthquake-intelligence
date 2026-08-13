"""Place-name resolution against admin_boundary.

Pure-function tests: no DB, no GPU, no LM Studio. That is the point of the
module — the measured comparison showed stdlib string distance beat the
embedding model 7/7 to 6/7 on realistic Pakistani place-name variants, so the
resolver needs no inference at all.
"""
from __future__ import annotations

import pytest

from eqmon.ai.places import (DEFAULT_THRESHOLD, PlaceMatch, load_gazetteer,
                             match_name, normalise, similarity)

# A slice of the real gazetteer, chosen to include names that are genuinely
# confusable (Khuzdar/Skardu, Mardan/Mardan-like) rather than a easy set.
GAZETTEER = ["Quetta", "Karachi", "Lahore", "Peshawar", "Muzaffarabad",
             "Rawalpindi", "Gilgit", "Skardu", "Chaman", "Khuzdar",
             "Mardan", "Abbottabad"]


# --- normalisation ---------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Quetta", "quetta"),
    ("  QUETTA  ", "quetta"),
    ("Rawalpindi Dist.", "rawalpindi"),
    ("Quetta City", "quetta"),
    ("Peshawar District", "peshawar"),
    ("Muzaffarābād", "muzaffarabad"),          # accent stripped
    ("Dera Ghazi Khan", "dera ghazi khan"),    # internal spaces kept
    ("Gilgit-Baltistan", "gilgit baltistan"),  # punctuation to space
    ("", ""),
])
def test_normalise(raw, expected):
    assert normalise(raw) == expected


def test_normalise_strips_suffix_only_as_whole_word():
    """'City' is a suffix; 'Cityabad' is part of a name. Substring stripping
    would corrupt real names."""
    assert normalise("Cityabad") == "cityabad"


# --- similarity ------------------------------------------------------------

def test_similarity_identical_is_one():
    assert similarity("quetta", "quetta") == 1.0


def test_similarity_empty_is_zero():
    assert similarity("", "quetta") == 0.0
    assert similarity("quetta", "") == 0.0


def test_similarity_misspelling_beats_different_city():
    """The property the whole module rests on, and the one embeddings failed:
    a misspelling must score higher than an unrelated real name."""
    assert similarity(normalise("Peshwar"), normalise("Peshawar")) > \
           similarity(normalise("Peshwar"), normalise("Khuzdar"))


# --- match_name: the measured variant set ---------------------------------

@pytest.mark.parametrize("probe,expected", [
    ("Kwetta", "Quetta"),
    ("Quetta City", "Quetta"),
    ("Peshwar", "Peshawar"),          # embeddings matched this to Khuzdar
    ("Muzafarabad", "Muzaffarabad"),
    ("Rawalpindi Dist.", "Rawalpindi"),
    ("Abbotabad", "Abbottabad"),
    ("Skardo", "Skardu"),
    ("QUETTA", "Quetta"),
    ("  Lahore  ", "Lahore"),
])
def test_match_name_resolves_known_variants(probe, expected):
    match = match_name(probe, GAZETTEER)
    assert match is not None, f"{probe!r} should have resolved to {expected!r}"
    assert match.name == expected


def test_match_name_returns_score_and_margin():
    match = match_name("Kwetta", GAZETTEER)
    assert 0.0 < match.score <= 1.0
    assert match.margin > 0


def test_exact_match_scores_one():
    assert match_name("Quetta", GAZETTEER).score == 1.0


# --- refusing to guess -----------------------------------------------------
# Returning None means "ask a human". For a module that feeds a review queue,
# a confident wrong answer is worse than an admitted unknown.

def test_unrelated_name_returns_none():
    assert match_name("Reykjavik", GAZETTEER) is None


def test_empty_probe_returns_none():
    assert match_name("", GAZETTEER) is None
    assert match_name("   ", GAZETTEER) is None


def test_empty_gazetteer_returns_none():
    assert match_name("Quetta", []) is None


def test_threshold_is_enforced():
    assert match_name("Kwetta", GAZETTEER, threshold=0.99) is None


def test_ambiguous_match_returns_none():
    """Two near-identical candidates mean the name is genuinely ambiguous —
    'Khairpur' exists in both Sindh and KP — so no score is high enough."""
    assert match_name("Khairpur", ["Khairpur North", "Khairpur South"]) is None


# --- payload mapping carries unit ids through -----------------------------

def test_mapping_candidates_carry_unit_id_and_level():
    match = match_name("Kwetta", {"Quetta": {"id": 42, "level": "district"},
                                  "Karachi": {"id": 7, "level": "district"}})
    assert (match.name, match.unit_id, match.level) == ("Quetta", 42, "district")


def test_list_candidates_have_no_unit_id():
    match = match_name("Kwetta", GAZETTEER)
    assert match.unit_id is None and match.level is None


# --- DB-backed loader (skipped without DATABASE_URL_TEST) -----------------

def test_load_gazetteer_returns_name_to_id_mapping(db_conn):
    db_conn.execute(
        "INSERT INTO admin_boundary (level, name, geom) VALUES "
        "('district', 'Testville', ST_GeomFromText('POLYGON((0 0,1 0,1 1,0 1,0 0))', 4326))")
    gazetteer = load_gazetteer(db_conn, level="district")
    assert "Testville" in gazetteer
    assert gazetteer["Testville"]["level"] == "district"
    assert isinstance(gazetteer["Testville"]["id"], int)
