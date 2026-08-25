from pathlib import Path
import re


INDEX = Path("web/index.html").read_text(encoding="utf-8")


def test_mutable_frontend_assets_are_revisioned():
    """HTML and local assets must not drift across browser cache versions."""
    for asset in ("styles.css", "app.js"):
        assert re.search(rf'["\']{re.escape(asset)}\?v=[^"\']+["\']', INDEX), (
            f"{asset} needs a cache-busting revision in web/index.html"
        )
