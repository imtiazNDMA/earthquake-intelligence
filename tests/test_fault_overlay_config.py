from pathlib import Path


def test_sparse_minor_faults_not_offered_as_an_overlay():
    """The Minor_Faults source holds one feature (the Karakuram Fault), which
    does not earn a toggle in the layer list. It was removed rather than left
    switched off; this guards against it being reinstated by habit."""
    app_js = Path("web/app.js").read_text(encoding="utf-8")
    build = Path("scripts/build_tiles.py").read_text(encoding="utf-8")

    assert "pak_faults_minor" not in app_js
    assert "Pakistan Minor" not in app_js
    # And nothing should still be spending a tippecanoe run on it.
    assert '("pak_faults_minor"' not in build


def test_national_faults_is_the_default_fault_overlay():
    app_js = Path("web/app.js").read_text(encoding="utf-8")

    # Colours are a design decision and change with the palette; what this test
    # guards is which fault overlay is on by default. The tile id stays
    # pak_faults_major — only the label the operator reads was renamed.
    assert '"National Faults": { id: "pak_faults_major"' in app_js
    assert 'id: "pak_faults_major", color: "#' in app_js
    assert 'width: 1.1, defaultOn: true' in app_js


def test_characterised_major_faults_ships_its_hazard_fields():
    """The Major Faults layer exists for Mmax and slip rate; a tooltip without
    them is the layer without its point."""
    app_js = Path("web/app.js").read_text(encoding="utf-8")

    assert 'id: "major_faults"' in app_js
    for field in ("FAULTNAME", "Fault_Type", "Mmax", "Slip_rate"):
        assert field in app_js
