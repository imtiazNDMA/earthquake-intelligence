from pathlib import Path


def test_sparse_minor_faults_not_default_overlay():
    app_js = Path("web/app.js").read_text(encoding="utf-8")

    assert '"Pakistan Major": { id: "pak_faults_major"' in app_js
    assert '"Pakistan Major": { id: "pak_faults_major", color: "#dc2626", width: 1.1, defaultOn: true' in app_js
    assert '"Pakistan Minor": { id: "pak_faults_minor", color: "#dc2626", width: 1.1, defaultOn: false' in app_js
    assert "Source currently contains one feature" in app_js
