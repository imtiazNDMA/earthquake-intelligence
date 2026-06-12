# eqMonitoring2 — Roadmap

## ✅ Complete — USGS FDSN Integration (Phases 1-4)

Full pipeline: fetch → ingest → dedup → incremental sync → detail cache → catalog UI with impact rollups and USGS metadata card.

See git log for details: `git log --oneline --author-date-order HEAD~4..HEAD`

---

## 🔲 Phase 5 — METSource (Primary)

**Value:** Pakistan MET Department feed becomes the primary source, winning dedup priority over USGS.

| File | What |
|------|------|
| `sources.py` | Implement `METSource.fetch()` once feed format is known |
| `config.py` | Add MET feed URL, polling interval, etc. |
| `sources.py` | Add source priority constant (MET=1, USGS=2) |
| `ingest.py` | _recluster already prefers MET over USGS |

**Blocked by:** MET feed format unknown.

---

## 🔲 Phase 6 — Boundary data pipeline

**Value:** Fresh developer can run `uv run python scripts/load_boundaries.py && uv run python scripts/build_tiles.py` and get admin overlays working.

| File | What |
|------|------|
| `scripts/load_boundaries.py` | Review/update; add idempotency |
| `scripts/build_tiles.py` | Review/update; add `--force` or check for existing tiles |
| `scripts/` | Add README or docstring with prerequisites (Docker, PostGIS) |
| `AGENTS.md` | Add build pipeline section |

---

## 🔲 Phase 7 — Edit/delete events

**Value:** Clean up test data, delete/update imported events without raw DB access.

| File | What |
|------|------|
| `repo.py` | `delete_event(conn, event_id)`, `update_event(...)` |
| `api.py` | `DELETE /events/{id}`, `PUT /events/{id}` |
| `app.js` | Delete button on event cards or detail panel, confirmation dialog |

---

## 🔲 Phase 8 — Automated ingest scheduler

**Value:** Catalog stays current without manual "Pull USGS feed" button clicks.

| File | What |
|------|------|
| `api.py` | Add `@app.on_event("startup")` or background task with apscheduler |
| `config.py` | Add `INGEST_INTERVAL_MINUTES = 15` |
| `api.py` | One-shot ingest on startup + periodic timer |

---

## 🔲 Phase 9 — Auto schema on startup

**Value:** No manual `init_schema()` invocation — migrations run automatically when the server starts.

| File | What |
|------|------|
| `api.py` | Call `db.init_schema()` in a startup event |
| `db.py` | Ensure `init_schema()` is safe to call multiple times (it already is) |

---

## 🔲 Phase 10 — Event filtering & search

**Value:** Filter catalog by magnitude range, date range, source; search by place name.

| File | What |
|------|------|
| `repo.py` | Add `search_events()`, `count_events()` |
| `api.py` | Add query params to `GET /events` |
| `app.js` | Filter inputs in catalog section |

---

## Quick reference

| Command | Description |
|---------|-------------|
| `uv sync --group dev` | Install all deps (dev included) |
| `uv run pytest -q` | Run full test suite |
| `uv run python -c "from eqmon.db import init_schema; init_schema()"` | Apply pending migrations |
| `uv run uvicorn eqmon.api:app --port 8000` | Start dev server |
