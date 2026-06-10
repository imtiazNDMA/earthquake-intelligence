import pytest
from eqmon.boundaries import map_feature


def test_district_maps_all_columns():
    props = {"Districts": "Bagh", "province": "Azad Kashmir",
             "division": "Poonch Division", "Population": "530861.6", "country": "Pakistan"}
    row = map_feature("district", props)
    assert row == {"level": "district", "name": "Bagh", "parent": "Azad Kashmir",
                   "division": "Poonch Division", "population": 530861.6}


def test_tehsil_has_no_population():
    props = {"name": "Bagh", "district": "Bagh", "province": "Azad Kashmir",
             "division": "Poonch Division", "country": "Pakistan"}
    row = map_feature("tehsil", props)
    assert row["level"] == "tehsil"
    assert row["name"] == "Bagh"
    assert row["parent"] == "Bagh"          # parent of a tehsil is its district
    assert row["division"] == "Poonch Division"
    assert row["population"] is None


def test_national_minimal():
    row = map_feature("national", {"Admin01_Na": "Pakistan"})
    assert row == {"level": "national", "name": "Pakistan",
                   "parent": None, "division": None, "population": None}


def test_unknown_level_raises():
    with pytest.raises(ValueError, match="unknown level"):
        map_feature("galaxy", {"name": "x"})


def test_missing_name_raises():
    with pytest.raises(ValueError, match="missing name"):
        map_feature("province", {"OBJECTID": "1"})
