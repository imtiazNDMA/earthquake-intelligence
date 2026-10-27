"""EQ-ARC exposure API.

Endpoints
---------
GET  /                      the demo page
GET  /api/health            service + cache status
GET  /api/layers            element layer registry
GET  /api/mmi/sample        the raw sample MMI bands as GeoJSON (for the map)
POST /api/analyze           dissolve an MMI layer and count what sits under it
POST /api/analyze/upload    same, but the MMI layer arrives as files

POST /api/analyze body (all fields optional):

    {
      "source":   "sample" | "path" | "geojson",
      "path":     "D:/.../mmi_bands.shp",      # when source == "path"
      "geojson":  { ...FeatureCollection... }, # when source == "geojson"
      "layers":   ["population", "hospitals"], # default: all
      "include_geometry": true,
      "dissolve": {
          "field": "mmi_high",
          "closing_m": 600,
          "min_hole_km2": 1.0,
          "min_part_km2": 0.5,
          "simplify_m": 200,
          "enforce_exclusive": true
      }
    }
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import eqarc  # noqa: F401,E402  - configures PROJ_LIB before osgeo loads

import shapely                                                  # noqa: E402
from flask import Flask, jsonify, request, send_from_directory  # noqa: E402
from flask_cors import CORS                                     # noqa: E402

from eqarc import vectorio                                      # noqa: E402
from eqarc.config import (ALLOWED_PATH_ROOTS, LAYERS,           # noqa: E402
                          SAMPLE_MMI, UPLOAD_DIR, WEB_DIR, cache_path)
from eqarc.dissolve import (SmoothingOptions, bands_to_geojson, # noqa: E402
                            dissolve_bands)
from eqarc.exposure import LayerStore, analyze                  # noqa: E402

MAX_UPLOAD_MB = 200

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
CORS(app)

STORE = LayerStore()


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _fail(message: str, status: int = 400, **extra: Any):
    payload = {"ok": False, "error": message}
    payload.update(extra)
    return jsonify(payload), status


def _check_path_allowed(target: Path) -> None:
    """Keep `source: "path"` inside the configured roots.

    Once the server listens on 0.0.0.0 this is the difference between an API
    and a remote file-read primitive. Widen ALLOWED_PATH_ROOTS in config.py if
    your MMI layers live elsewhere.
    """
    if not ALLOWED_PATH_ROOTS:
        return

    try:
        resolved = target.resolve()
    except OSError as exc:
        raise ValueError(f"Cannot resolve path: {exc}") from exc

    for root in ALLOWED_PATH_ROOTS:
        try:
            resolved.relative_to(Path(root).resolve())
            return
        except ValueError:
            continue

    allowed = ", ".join(str(Path(r)) for r in ALLOWED_PATH_ROOTS)
    raise ValueError(
        f"Path is outside the allowed directories. Allowed: {allowed}. "
        "Add more roots to ALLOWED_PATH_ROOTS in scripts/eqarc/config.py, "
        "or upload the layer to /api/analyze/upload instead."
    )


def _records_from_request(payload: dict[str, Any]):
    """Resolve the request into (records, description-of-source)."""
    source = (payload.get("source") or "sample").lower()

    if source == "sample":
        if not SAMPLE_MMI.exists():
            raise ValueError(f"Sample MMI layer not found at {SAMPLE_MMI}")
        return list(vectorio.read_features(SAMPLE_MMI)), {
            "type": "sample", "path": str(SAMPLE_MMI)}

    if source == "path":
        raw = payload.get("path")
        if not raw:
            raise ValueError("source='path' requires a 'path' field")
        target = Path(raw)
        _check_path_allowed(target)
        if not target.exists():
            raise ValueError(f"Path does not exist: {target}")
        missing = vectorio.check_shapefile_set(target)
        if missing:
            raise ValueError(
                f"Shapefile is incomplete, missing: {', '.join(missing)}")
        return list(vectorio.read_features(target)), {
            "type": "path", "path": str(target)}

    if source == "geojson":
        data = payload.get("geojson")
        if not data:
            raise ValueError("source='geojson' requires a 'geojson' field")
        return list(vectorio.geojson_to_records(data)), {"type": "geojson"}

    raise ValueError(f"Unknown source '{source}'. Use sample, path or geojson.")


def _run_analysis(records, payload: dict[str, Any], source_info: dict[str, Any]):
    if not records:
        return _fail("The MMI source contained no usable polygons.")

    timings: dict[str, float] = {}

    started = time.perf_counter()
    options = SmoothingOptions.from_dict(payload.get("dissolve"))
    bands, dissolve_report = dissolve_bands(records, options)
    timings["dissolve_s"] = round(time.perf_counter() - started, 3)

    started = time.perf_counter()
    result = analyze(STORE, bands, payload.get("layers"))
    timings["exposure_s"] = round(time.perf_counter() - started, 3)

    response: dict[str, Any] = {
        "ok": True,
        "source": source_info,
        "dissolve": dissolve_report,
        "bands": result["bands"],
        "cumulative": result["cumulative"],
        "totals": result["totals"],
        "meta": {
            "layers_analyzed": result["layers_analyzed"],
            "layer_errors": result["layer_errors"],
            "timings_s": {**timings, "per_layer": result["timings_s"]},
            "counting_rule": (
                "Each element is attributed to the highest MMI band it falls "
                "in, so bands are mutually exclusive and nothing is counted "
                "twice. Population is the sum of glob_f_* and glob_m_* age "
                "columns; every other layer is a feature count."
            ),
            "crs": "EPSG:4326",
        },
    }

    if payload.get("include_geometry", True):
        response["geometry"] = bands_to_geojson(bands, options.field)

    return jsonify(response)


# --------------------------------------------------------------------------
# routes
# --------------------------------------------------------------------------

@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/<path:filename>")
def static_files(filename: str):
    return send_from_directory(WEB_DIR, filename)


@app.get("/api/health")
def health():
    status = STORE.status()
    missing = [n for n, s in status.items() if not s["cached"]]
    return jsonify({
        "ok": True,
        "service": "eq-arc-exposure",
        "sample_mmi_available": SAMPLE_MMI.exists(),
        "layers": status,
        "caches_missing": missing,
        "ready": not missing,
        "hint": ("Run 'python scripts/build_cache.py' to build the missing "
                 "caches.") if missing else None,
    })


@app.get("/api/layers")
def layers():
    return jsonify({
        "ok": True,
        "layers": [
            {"name": name, "label": spec["label"], "kind": spec["kind"],
             "metric": "population sum" if spec["kind"] == "pop" else "feature count",
             "cached": cache_path(name).exists()}
            for name, spec in LAYERS.items()
        ],
    })


@app.get("/api/mmi/sample")
def sample_mmi():
    """Raw (undissolved) sample bands, so the page can show a before/after."""
    if not SAMPLE_MMI.exists():
        return _fail(f"Sample MMI layer not found at {SAMPLE_MMI}", 404)
    records = list(vectorio.read_features(SAMPLE_MMI))
    features = [
        {"type": "Feature", "properties": attrs,
         "geometry": shapely.geometry.mapping(geom)}
        for geom, attrs in records
    ]
    return jsonify({"type": "FeatureCollection", "features": features})


@app.post("/api/analyze")
def analyze_route():
    payload = request.get_json(silent=True) or {}
    try:
        records, source_info = _records_from_request(payload)
    except ValueError as exc:
        return _fail(str(exc))
    except Exception as exc:
        app.logger.error("read failed: %s", traceback.format_exc())
        return _fail(f"Could not read the MMI source: {exc}", 500)

    try:
        return _run_analysis(records, payload, source_info)
    except ValueError as exc:
        return _fail(str(exc))
    except Exception as exc:
        app.logger.error("analysis failed: %s", traceback.format_exc())
        return _fail(f"Analysis failed: {exc}", 500)


@app.post("/api/analyze/upload")
def analyze_upload():
    """Accept either a zipped shapefile, the loose .shp/.shx/.dbf/.prj set,
    or a single .geojson, under the form field 'files'."""
    uploaded = request.files.getlist("files") or request.files.getlist("file")
    if not uploaded:
        return _fail("No files uploaded. Use the form field 'files'.")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix="mmi_", dir=UPLOAD_DIR))
    try:
        saved: list[Path] = []
        for item in uploaded:
            name = Path(item.filename or "").name
            if not name:
                continue
            dest = workdir / name
            item.save(dest)
            saved.append(dest)

        if not saved:
            return _fail("Uploaded files had no usable names.")

        zips = [p for p in saved if p.suffix.lower() == ".zip"]
        target = (vectorio.extract_zip(zips[0], workdir) if zips
                  else vectorio.find_vector_file(workdir))

        missing = vectorio.check_shapefile_set(target)
        if missing:
            return _fail(
                f"Incomplete shapefile: missing {', '.join(missing)}. "
                "Upload the .shp, .shx, .dbf and .prj together (or a .zip).")

        payload: dict[str, Any] = {}
        if "layers" in request.form:
            payload["layers"] = _parse_layers(request.form["layers"])
        if "include_geometry" in request.form:
            payload["include_geometry"] = _parse_bool(request.form["include_geometry"])
        if "dissolve" in request.form:
            value = _parse_form_value(request.form["dissolve"])
            if isinstance(value, dict):
                payload["dissolve"] = value

        records = list(vectorio.read_features(target))
        return _run_analysis(records, payload,
                             {"type": "upload", "file": target.name,
                              "files": [p.name for p in saved]})
    except ValueError as exc:
        return _fail(str(exc))
    except Exception as exc:
        app.logger.error("upload analysis failed: %s", traceback.format_exc())
        return _fail(f"Analysis failed: {exc}", 500)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _parse_form_value(raw: str) -> Any:
    import json
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return raw


def _parse_layers(raw: str) -> list[str]:
    """Accept a JSON array, or a comma/space separated list of layer names.

    Multipart form fields are always strings, so a bare ``layers=hospitals``
    must not be left as a str - iterating one yields single characters.
    """
    value = _parse_form_value(raw)
    if isinstance(value, str):
        value = [part for part in value.replace(",", " ").split() if part]
    elif not isinstance(value, list):
        value = [value]
    return [str(item).strip() for item in value if str(item).strip()]


def _parse_bool(raw: str) -> bool:
    value = _parse_form_value(raw)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@app.errorhandler(413)
def too_large(_exc):
    return _fail(f"Upload exceeds the {MAX_UPLOAD_MB} MB limit.", 413)


# --------------------------------------------------------------------------

def _lan_addresses() -> tuple[str | None, list[str]]:
    """This machine's IPv4 addresses, as (primary, others).

    A dev box typically has a pile of virtual adapters - Docker, WSL, VPNs -
    so listing every address unranked is not much help. The address the OS
    would actually route out of is the one worth trying first.
    """
    import socket

    primary: str | None = None
    try:
        # Does not send traffic - just asks the OS which interface it would use.
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("8.8.8.8", 80))
            primary = probe.getsockname()[0]
        finally:
            probe.close()
    except OSError:
        pass

    found: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(info[4][0])
    except OSError:
        pass

    others = sorted(
        a for a in found
        if a != primary
        and not a.startswith("127.")        # loopback
        and not a.startswith("169.254.")    # APIPA, never usefully reachable
    )
    return primary, others


def _port_is_free(host: str, port: int) -> bool:
    import socket

    bind_host = "" if host in ("0.0.0.0", "::") else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((bind_host, port))
            return True
        except OSError:
            return False


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="EQ-ARC exposure API")
    parser.add_argument("--host", default="0.0.0.0",
                        help="interface to bind (default: 0.0.0.0, all interfaces). "
                             "Use 127.0.0.1 to keep it on this machine only.")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--no-preload", action="store_true",
                        help="load layer caches on first request instead of at startup")
    parser.add_argument("--auto-port", action="store_true",
                        help="if the port is taken, move to the next free one")
    args = parser.parse_args()

    # Fail loudly rather than leaving the browser pointed at whatever else
    # happens to own the port - a stale 404 from an unrelated app is a
    # genuinely confusing way to find out the server never started.
    if not _port_is_free(args.host, args.port):
        if args.auto_port:
            original = args.port
            for candidate in range(original + 1, original + 25):
                if _port_is_free(args.host, candidate):
                    args.port = candidate
                    break
            else:
                print(f"!! Ports {original}-{original + 24} are all in use.",
                      flush=True)
                return 1
            print(f"!! Port {original} is already in use by another program - "
                  f"using port {args.port} instead.\n", flush=True)
        else:
            print(f"\n!! Port {args.port} is already in use by another program.",
                  flush=True)
            print("!! That other program is what your browser will show, not "
                  "this API.", flush=True)
            print(f"!! Free the port, or start on a different one:\n"
                  f"!!     python scripts/server.py --port {args.port + 1}\n"
                  f"!! To find what is using it:\n"
                  f'!!     netstat -ano | findstr :{args.port}\n', flush=True)
            return 1

    missing = STORE.missing()
    if missing:
        print(f"!! No cache for: {', '.join(missing)}", flush=True)
        print("!! Run: python scripts/build_cache.py\n", flush=True)

    if not args.no_preload and not missing:
        print("Loading layer caches into memory ...", flush=True)
        started = time.perf_counter()
        STORE.preload()
        print(f"Caches ready in {time.perf_counter() - started:,.1f}s", flush=True)

    print("\n  EQ-ARC exposure API", flush=True)
    print(f"    this machine   http://127.0.0.1:{args.port}", flush=True)

    if args.host in ("0.0.0.0", "::"):
        primary, others = _lan_addresses()
        if primary:
            print(f"    on network     http://{primary}:{args.port}", flush=True)
        else:
            print("    on network     (no network address detected)", flush=True)
        for address in others:
            print(f"      also         http://{address}:{args.port}"
                  "   (virtual adapter?)", flush=True)
        print("\n  Reachable from other machines. If they cannot connect, allow "
              f"TCP port {args.port}\n  through Windows Firewall - run "
              "allow_firewall.bat as administrator.", flush=True)
    else:
        print(f"    bound to       {args.host} (this machine only)", flush=True)
    print("", flush=True)

    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
