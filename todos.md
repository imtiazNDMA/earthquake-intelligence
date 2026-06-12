# USGS FDSN Integration — Phased Plan

## Phase 1 ✅ Foundation — Schema + parser + eventtype filter

**Value:** Richer data in DB, non-earthquake noise filtered out.

**Backend only — no UI changes.**

| Step | File | What |
|------|------|------|
| ✅ 1 | `migrations/002_add_usgs_fields.sql` | ALTER TABLE ADD COLUMN for place, mag_type, event_type, alert, tsunami, sig, review_status, felt, cdi, mmi_report, gap, nst, url, detail_url, updated_at |
| ✅ 2 | `sources.py` | Extend `RawEvent` dataclass with 15 optional fields |
| ✅ 3 | `sources.py` | Extend `parse_usgs()` to extract all new fields from GeoJSON properties |
| ✅ 4 | `sources.py` | Add `eventtype=earthquake` default to `fdsn_query_params()` — filters out quarry blasts |
| ✅ 5 | `ingest.py` | Extend `_upsert()` INSERT to include all new columns |
| ✅ 6 | `repo.py` | Extend `_SELECT` to return new columns |
| ✅ 7 | `fixtures/usgs_sample.json`, `tests/test_sources.py` | Richer fixture + assertions for all new fields, eventtype test |

---

## Phase 2 ✅ Richer catalog UI

**Value:** Catalog goes from `M5.4 · USGS · 1/1/2026` to showing place, magType, alert badge, tsunami flag.

### Frontend
| File | What |
|------|------|
| ✅ `app.js:191-206` | Richer event card: magnitude + magType, alert badge (colored by level), tsunami flag, sig score, place name, source + timestamp |
| ✅ `index.html` | CSS for alert badges (green/yellow/orange/red), tsunami pill, mag-type label, text truncation |

### Backend
- No changes needed — `/events` endpoint already returns all new fields via `_SELECT`.

---

## Phase 3 ⏳ Incremental sync

**Value:** 1 API call per ingest instead of 30. Faster, less bandwidth.

| File | What |
|------|------|
| `sources.py` | Add `updatedafter` param to `fdsn_query_params()` + `USGSSource.fetch()` |
| `ingest.py` | Track `last_sync_at` in `IngestResult` |
| `api.py` | Read/write last_sync_at between ingests (file or DB) |
| `migrations/003_sync_state.sql` | `CREATE TABLE IF NOT EXISTS _sync_state (key TEXT PRIMARY KEY, value TEXT)` |

---

## Phase 4 ⏳ Event detail + USGS MMI comparison

**Value:** Click a catalog event → fetch full USGS detail (moment tensor, focal mechanism, ShakeMap MMI). Compare our MMI vs USGS MMI.

### Backend
| File | What |
|------|------|
| `sources.py` | `USGSSource.fetch_event(event_id)` using `?eventid=<id>&format=geojson` |
| `api.py` | `POST /events/{id}/refresh-from-usgs` endpoint |
| `migrations/004_usgs_detail.sql` | `ALTER TABLE seismic_event ADD COLUMN usgs_detail JSONB` |

### Frontend
| File | What |
|------|------|
| `app.js` | Detail panel: USGS MMI vs our MMI comparison, PAGER alert, DYFI, beachball |
| `index.html` | Detail panel section in sidebar |

---

## Quick reference

| Command | Description |
|---------|-------------|
| `uv run python -c "from eqmon.db import init_schema; init_schema()"` | Apply all pending migrations |
| `uv run pytest -q` | Run full test suite |
| `uv run pytest tests/test_sources.py -v` | Run source tests (Phase 1 coverage) |
