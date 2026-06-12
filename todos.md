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

## Phase 3 ✅ Incremental sync

**Value:** Each `/events/ingest` call after the first fetches *only* events updated since the last sync (1 API call) instead of re-fetching the full 30-day window (~30 API calls).

| File | What |
|------|------|
| ✅ `migrations/003_sync_state.sql` | `_sync_state` key-value table for `usgs_last_sync` |
| ✅ `sources.py` | `fdsn_query_params` accepts `updatedafter`; `USGSSource.fetch()` has fast incremental path (single query, falls back to chunking on error) |
| ✅ `ingest.py` | `ingest()` forwards `updatedafter` to `source.fetch()` |
| ✅ `api.py` | `/events/ingest` reads `usgs_last_sync`, writes current timestamp on success |

**Behavior:** First run → full chunking; subsequent → single `updatedafter` query; HTTP error on `updatedafter` → falls back to chunking.

---

## Phase 4 ✅ Event detail + USGS metadata

**Value:** Click a catalog event → fetch full USGS detail (moment tensor, focal mechanism, ShakeMap products). Shows USGS metadata card alongside the impact rollup.

### Backend
| File | What |
|------|------|
| ✅ `migrations/004_usgs_detail.sql` | `ALTER TABLE seismic_event ADD COLUMN usgs_detail JSONB` |
| ✅ `sources.py` | `USGSSource.fetch_event(event_id)` using `?eventid=<id>&format=geojson` |
| ✅ `repo.py` | `_SELECT_DETAIL` includes usgs_detail for `get_event`; `update_usgs_detail()` |
| ✅ `api.py` | `POST /events/{id}/refresh-from-usgs` endpoint |

### Frontend
| File | What |
|------|------|
| ✅ `app.js:211-289` | `showImpact` fetches both event+impact in parallel; `renderDetail()` displays USGS card with place, mag+type, depth, alert badge, tsunami flag, felt, sig, product badges (ShakeMap/Moment Tensor/DYFI/Focal Mechanism), USGS link; `refreshFromUsgs()` button triggers detail fetch |
| ✅ `index.html` | `#detail` div in catalog section; CSS for detail card, product badges, refresh button, detail info, USGS link |

### Behavior
- Clicking an event: fetches `/events/{id}` + impact in parallel, renders USGS card (if cached) + rollup table
- No USGS data cached yet: shows "No USGS detail cached" + Refresh button
- "Refresh from USGS" → calls detail fetch → stores to DB → re-renders card
- Manual events (no source_event_id): no USGS section shown

---

## Quick reference

| Command | Description |
|---------|-------------|
| `uv run python -c "from eqmon.db import init_schema; init_schema()"` | Apply all pending migrations |
| `uv run pytest -q` | Run full test suite |
| `uv run pytest tests/test_sources.py -v` | Run source tests (Phase 1 coverage) |
