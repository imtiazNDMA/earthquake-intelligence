"""Stage the backend (eqmon API + eq_arc) and upload it to a Hugging Face Space.

The Space builds deploy/hf-space/Dockerfile. Vs30.tif and the eq_arc layer
caches are gitignored, so they are uploaded from this machine; unchanged files
are deduplicated by the Hub, so redeploys only send what changed.

Prerequisites:
  - A Docker Space created at huggingface.co/new-space (SDK: Docker, blank)
  - `uvx hf auth login` once, with a write token
  - data/Vs30.tif and eq_arc/data/cache/*.npz present locally

Usage:
  uv run python scripts/deploy_hf_space.py <user>/<space>
  uv run python scripts/deploy_hf_space.py <user>/<space> --dry-run   # stage only"""
from __future__ import annotations
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPACE_DIR = ROOT / "deploy" / "hf-space"

# (source under ROOT, destination in the Space)
STAGED = [
    (SPACE_DIR / "Dockerfile", "Dockerfile"),
    (SPACE_DIR / "README.md", "README.md"),
    (ROOT / "pyproject.toml", "pyproject.toml"),
    (ROOT / "uv.lock", "uv.lock"),
    (ROOT / "notebooks" / "pyproject.toml", "notebooks/pyproject.toml"),
    (ROOT / "src", "src"),
    (ROOT / "migrations", "migrations"),
    (ROOT / "data" / "Vs30.tif", "data/Vs30.tif"),
    (ROOT / "eq_arc" / "requirements.txt", "eq_arc/requirements.txt"),
    (ROOT / "eq_arc" / "scripts", "eq_arc/scripts"),
    (ROOT / "eq_arc" / "data" / "sample_mmi", "eq_arc/data/sample_mmi"),
    (ROOT / "eq_arc" / "data" / "cache", "eq_arc/data/cache"),
]

_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")


def stage(dest: Path) -> None:
    missing = [str(src.relative_to(ROOT)) for src, _ in STAGED if not src.exists()]
    if missing:
        sys.exit("Missing, cannot deploy: " + ", ".join(missing))
    for src, rel in STAGED:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, target, ignore=_IGNORE)
        else:
            shutil.copy2(src, target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("space", help="Space id, e.g. myname/eqmon-api")
    parser.add_argument("--dry-run", action="store_true",
                        help="stage into a temp dir and print it, without uploading")
    args = parser.parse_args()

    staging = Path(tempfile.mkdtemp(prefix="hf-space-"))
    stage(staging)
    if args.dry_run:
        print(f"Staged at {staging}")
        return 0
    try:
        return subprocess.call([
            "uvx", "--from", "huggingface_hub", "hf", "upload", args.space,
            str(staging), ".", "--repo-type", "space",
            "--commit-message", "Deploy from eqMonitoring2",
        ])
    finally:
        shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
