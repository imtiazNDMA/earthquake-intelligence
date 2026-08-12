from pathlib import Path


def test_sparse_minor_faults_not_default_overlay():
    app_js = Path("web/app.js").read_text(encoding="utf-8")

    # Colours are a design decision and change with the palette; what this test
    # guards is which fault overlay is on by default.
    assert '"Pakistan Major": { id: "pak_faults_major"' in app_js
    assert 'id: "pak_faults_major", color: "#' in app_js
    assert 'width: 1.1, defaultOn: true' in app_js
    assert 'id: "pak_faults_minor", color: "#' in app_js
    assert 'width: 1.1, defaultOn: false' in app_js
    assert "Source currently contains one feature" in app_js
