"""Deterministic, duplicate-safe place resolution."""
from __future__ import annotations

import math

import pytest

from eqmon.ai.places import (BoundaryCandidate, load_gazetteer, match_name,
                             normalise, resolve_place, similarity)

GAZETTEER = [
    BoundaryCandidate(i, name, "district")
    for i, name in enumerate([
        "Quetta", "Karachi", "Lahore", "Peshawar", "Muzaffarabad",
        "Rawalpindi", "Gilgit", "Skardu", "Chaman", "Khuzdar",
        "Mardan", "Abbottabad",
    ], start=1)
]


@pytest.mark.parametrize("raw,expected", [
    ("Quetta", "quetta"),
    ("  QUETTA  ", "quetta"),
    ("Rawalpindi Dist.", "rawalpindi"),
    ("Quetta City", "quetta"),
    ("Peshawar District", "peshawar"),
    ("Muzaffarābād", "muzaffarabad"),
    ("Dera Ghazi Khan", "dera ghazi khan"),
    ("Gilgit-Baltistan", "gilgit baltistan"),
    ("", ""),
])
def test_normalise(raw, expected):
    assert normalise(raw) == expected


def test_normalise_only_strips_trailing_admin_suffixes():
    assert normalise("Cityabad") == "cityabad"
    assert normalise("District of Columbia") == "district of columbia"


def test_similarity_misspelling_beats_different_city():
    assert similarity(normalise("Peshwar"), normalise("Peshawar")) > \
           similarity(normalise("Peshwar"), normalise("Khuzdar"))


@pytest.mark.parametrize("probe,expected", [
    ("Kwetta", "Quetta"),
    ("Quetta City", "Quetta"),
    ("Peshwar", "Peshawar"),
    ("Muzafarabad", "Muzaffarabad"),
    ("Rawalpindi Dist.", "Rawalpindi"),
    ("Abbotabad", "Abbottabad"),
    ("Skardo", "Skardu"),
])
def test_match_name_resolves_known_variants(probe, expected):
    result = match_name(probe, GAZETTEER)
    assert result.status == "resolved"
    assert result.match.name == expected
    assert result.method == "text"


def test_match_name_returns_not_found_for_unrelated_name():
    result = match_name("Reykjavik", GAZETTEER)
    assert result.status == "not_found"
    assert result.match is None


def test_low_confidence_near_tie_is_not_false_ambiguity():
    candidates = [
        BoundaryCandidate(1, "Katlang", "tehsil"),
        BoundaryCandidate(2, "Balanari", "tehsil"),
    ]
    result = match_name("Atlantis", candidates)
    assert result.status == "not_found"


@pytest.mark.parametrize("probe", ["Paris", "Kathmandu", "America"])
def test_unrelated_names_do_not_resolve_by_string_similarity(probe):
    result = match_name(probe, GAZETTEER)
    assert result.status == "not_found"


def test_duplicate_exact_names_remain_ambiguous():
    candidates = [
        BoundaryCandidate(1, "Khairpur", "tehsil", parent="Khairpur"),
        BoundaryCandidate(2, "Khairpur", "tehsil", parent="Shikarpur"),
    ]
    result = match_name("Khairpur", candidates)
    assert result.status == "ambiguous"
    assert [candidate.unit_id for candidate in result.candidates] == [1, 2]


def test_parent_hint_disambiguates_duplicate_names():
    candidates = [
        BoundaryCandidate(1, "Khairpur", "tehsil", parent="Khairpur"),
        BoundaryCandidate(2, "Khairpur", "tehsil", parent="Shikarpur"),
    ]
    result = match_name("Khairpur", candidates, parent="Shikarpur")
    assert result.status == "resolved"
    assert result.match.unit_id == 2


def _insert_boundary(conn, level, name, parent, wkt):
    return conn.execute(
        "INSERT INTO admin_boundary (level, name, parent, geom) VALUES "
        "(%s, %s, %s, ST_Multi(ST_GeomFromText(%s, 4326))) RETURNING id",
        (level, name, parent, wkt),
    ).fetchone()[0]


def test_load_gazetteer_preserves_duplicate_names(db_conn):
    first = _insert_boundary(
        db_conn, "tehsil", "Testville", "North",
        "POLYGON((0 0,1 0,1 1,0 1,0 0))",
    )
    second = _insert_boundary(
        db_conn, "tehsil", "Testville", "South",
        "POLYGON((2 0,3 0,3 1,2 1,2 0))",
    )
    gazetteer = load_gazetteer(db_conn, level="tehsil")
    assert {candidate.unit_id for candidate in gazetteer} == {first, second}


def test_coordinates_are_primary_and_text_corroborates(db_conn):
    unit_id = _insert_boundary(
        db_conn, "district", "Quetta", "Balochistan",
        "POLYGON((66 29,68 29,68 31,66 31,66 29))",
    )
    result = resolve_place(
        db_conn, "Kwetta", lon=67, lat=30, level="district",
    )
    assert result.status == "resolved"
    assert result.method == "spatial+text"
    assert result.match.unit_id == unit_id


def test_spatial_text_disagreement_returns_conflict(db_conn):
    spatial_id = _insert_boundary(
        db_conn, "district", "Quetta", "Balochistan",
        "POLYGON((66 29,68 29,68 31,66 31,66 29))",
    )
    text_id = _insert_boundary(
        db_conn, "district", "Karachi", "Sindh",
        "POLYGON((66 24,68 24,68 26,66 26,66 24))",
    )
    result = resolve_place(
        db_conn, "Karachi", lon=67, lat=30, level="district",
    )
    assert result.status == "conflict"
    assert {candidate.unit_id for candidate in result.candidates} == {spatial_id, text_id}


def test_shared_boundary_coordinates_return_ambiguous(db_conn):
    _insert_boundary(
        db_conn, "district", "West", None,
        "POLYGON((0 0,1 0,1 1,0 1,0 0))",
    )
    _insert_boundary(
        db_conn, "district", "East", None,
        "POLYGON((1 0,2 0,2 1,1 1,1 0))",
    )
    result = resolve_place(db_conn, "", lon=1, lat=0.5, level="district")
    assert result.status == "ambiguous"
    assert result.method == "spatial"
    assert len(result.candidates) == 2


def test_text_disambiguates_candidates_on_shared_boundary(db_conn):
    _insert_boundary(
        db_conn, "district", "West", None,
        "POLYGON((0 0,1 0,1 1,0 1,0 0))",
    )
    expected = _insert_boundary(
        db_conn, "district", "East", None,
        "POLYGON((1 0,2 0,2 1,1 1,1 0))",
    )
    result = resolve_place(db_conn, "East", lon=1, lat=0.5, level="district")
    assert result.status == "resolved"
    assert result.method == "spatial+text"
    assert result.match.unit_id == expected


def test_default_level_returns_most_specific_boundary(db_conn):
    _insert_boundary(
        db_conn, "province", "Balochistan", None,
        "POLYGON((0 0,4 0,4 4,0 4,0 0))",
    )
    district_id = _insert_boundary(
        db_conn, "district", "Quetta", "Balochistan",
        "POLYGON((1 1,3 1,3 3,1 3,1 1))",
    )
    result = resolve_place(db_conn, "", lon=2, lat=2)
    assert result.status == "resolved"
    assert result.match.unit_id == district_id


def test_coordinates_outside_coverage_do_not_fall_back_to_text(db_conn):
    _insert_boundary(
        db_conn, "district", "Quetta", "Balochistan",
        "POLYGON((66 29,68 29,68 31,66 31,66 29))",
    )
    result = resolve_place(
        db_conn, "Quetta", lon=0, lat=0, level="district",
    )
    assert result.status == "conflict"
    assert result.match is None


def test_ambiguous_text_is_disambiguated_by_coordinates(db_conn):
    expected = _insert_boundary(
        db_conn, "tehsil", "Khairpur", "North",
        "POLYGON((0 0,1 0,1 1,0 1,0 0))",
    )
    _insert_boundary(
        db_conn, "tehsil", "Khairpur", "South",
        "POLYGON((2 0,3 0,3 1,2 1,2 0))",
    )
    result = resolve_place(db_conn, "Khairpur", lon=0.5, lat=0.5,
                           level="tehsil")
    assert result.status == "resolved"
    assert result.method == "spatial+text"
    assert result.match.unit_id == expected


@pytest.mark.parametrize("lon,lat", [
    (181, 0), (-181, 0), (0, 91), (0, -91), (math.inf, 0), (0, math.nan),
])
def test_invalid_coordinates_are_rejected(db_conn, lon, lat):
    with pytest.raises(ValueError):
        resolve_place(db_conn, lon=lon, lat=lat)
