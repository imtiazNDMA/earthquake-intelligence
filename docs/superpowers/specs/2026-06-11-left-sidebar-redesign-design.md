# Left Sidebar Redesign — Icon Rail + Panel

**Date:** 2026-06-11
**Status:** Approved (design)
**Scope:** Frontend only (`web/index.html`, `web/app.js`). No backend or dependency changes.

## Problem

The current UI crams the event-input form, the earthquake catalog list, the impact
rollup table, and a status line into a single 240px floating white box at top-left
(`#panel`). Map configuration is scattered across three separate floating Leaflet
widgets: a layer control (overlay + basemap radios, top-right), a basemap cycle
button (top-left), and the MMI legend (bottom-right). The result is cramped and
visually inconsistent.

## Goal

Replace the single floating panel with a fixed full-height **icon rail + panel**
shell on the left edge that organizes all controls into three switchable sections,
and consolidate map configuration into one of those sections. Adopt a clean,
minimal visual style.

## 1. Layout & Structure

A fixed full-height shell pinned to the left edge of the viewport, in two parts:

- **Icon rail** — ~46px wide, `#fafafa` background, right border `#eee`. Contains
  three section icons and a collapse chevron at the bottom:
  - `✚` Event input
  - `≣` Catalog
  - `⚙` Map config
  - `‹` collapse/expand toggle (bottom)
- **Panel** — ~260px wide, white background, shows the active section's content.

**Behavior:**

- Default on load: **Event input** panel open.
- Clicking a non-active icon switches the panel to that section.
- Clicking the **currently active** icon collapses the panel to just the rail
  (map reclaims the space). The collapse chevron does the same. Clicking any icon
  while collapsed re-opens that section.
- Active icon is highlighted with the accent color (`#111` background, white glyph).

The Leaflet map remains full-viewport; the shell floats above its left edge with
`position: absolute` / `z-index` (consistent with how the old `#panel` floated). The
map is not reflowed when the panel collapses — collapsing simply reveals more map
under the freed space. Leaflet zoom and basemap buttons must stay usable to the right
of the rail/panel (repositioned via CSS, see §1 below).

The existing top-left Leaflet controls (zoom buttons, basemap cycle button) are
repositioned so they do not sit underneath the rail/panel — either nudged right via
CSS margin on `.leaflet-top.leaflet-left`, or the basemap cycle button is removed
(see §2, Map config).

## 2. The Three Panels

### ✚ Event input
The earthquake parameter form, unchanged in fields and endpoints:
- Inputs in a 2×2 grid: **Magnitude**, **Depth (km)**, **Latitude**, **Longitude**
  (same `id`s: `magnitude`, `depth_km`, `lat`, `lon`).
- **Calculate intensity** — primary button (`#111`), triggers existing `calculate()`
  → `POST /intensity`.
- **Pull USGS feed** — secondary button, triggers existing ingest handler →
  `POST /events/ingest`.
- **Status line** (`#status`) below the buttons.

### ≣ Catalog
- The `/events` list (`GET /events?limit=20`), restyled as clean rows:
  magnitude badge · source · relative/local time. Each row clickable to compute
  impact (existing `showImpact(id)` → `POST /events/{id}/impact`).
- The **impact rollup table** renders **below the list in this same panel**
  (province / district / tehsil level switcher via the existing `renderRollup()`).

### ⚙ Map config
Replaces the floating Leaflet layer control **and** the basemap cycle button:
- **Overlays** — a checklist of the seven overlays (National, Provinces, Districts,
  Tehsils, Faults, Plate boundaries, Plates). Each item shows a small swatch in its
  symbolizer color and a checkbox that adds/removes the corresponding
  `OVERLAYS[name]` layer from the map. Initial checked state mirrors current
  defaults (National + Provinces on).
- **Basemap** — a single-select control (radio list or `<select>`) over the six free
  basemaps in `BASEMAPS`. Selecting one swaps the active basemap (reusing the
  existing `setBasemap`/single-active-layer logic). Default: OpenStreetMap.

The `BASEMAPS` and `OVERLAYS` object definitions in `app.js` are **unchanged**; only
their UI host moves from Leaflet controls into DOM inside this panel.

## 3. Visual Style — Clean Minimal

- Panel background white; rail `#fafafa`; borders `#e2e2e2` / `#eee`.
- Single accent: near-black `#111` (active rail icon, primary button).
- Inputs: `#fafafa` fill, `1px solid #e2e2e2`, ~5px radius.
- Micro-labels above inputs: small, uppercase, letter-spaced, `#999`.
- System font stack (already in use).
- The **MMI legend stays floating** at bottom-right (it is data context, not config),
  visually retouched only if trivial.

## 4. Implementation Approach

### `web/index.html`
- Replace the single `#panel` markup with the shell: `#sidebar` containing
  `.rail` (icon buttons + collapse) and `#panel-body` (the three section
  containers, e.g. `#sec-event`, `#sec-catalog`, `#sec-config`).
- Update the `<style>` block to the clean-minimal theme and the new shell/rail/panel
  CSS. Keep CSS in the document `<style>` (matches current convention).
- Preserve all element `id`s that `app.js` references (`magnitude`, `depth_km`,
  `lat`, `lon`, `calc`, `ingest`, `status`, `events`, `impact`) so existing handlers
  keep working; add new ids for the config panel hosts.

### `web/app.js`
Three changes; everything else stays:
1. **Config panel UI** — replace `L.control.layers(BASEMAPS, OVERLAYS, …)` and the
   basemap cycle-button control with functions that render:
   - overlay checkboxes (wired to `layer.addTo(map)` / `map.removeLayer(layer)`),
   - basemap radios/select (wired to the existing basemap-swap logic).
   Keep `baselayerchange`/single-active-basemap invariants intact.
2. **Rail logic** — add tab-switching (show one `.section`, hide others; set active
   icon) and collapse/expand of the panel.
3. **Existing data functions** — `calculate()`, `refreshEvents()`, `showImpact()`,
   `renderRollup()`, and the ingest handler keep their logic; only the container
   elements they write into are re-pointed to the new panel structure.

### Out of scope
- No backend/API changes.
- No new dependencies (vanilla DOM + existing Leaflet/protomaps-leaflet).
- No change to `BASEMAPS`/`OVERLAYS` definitions, tile sources, or `/intensity`,
  `/events`, `/events/{id}/impact`, `/events/ingest` contracts.
- Mobile/responsive layout is not a goal for this pass (desktop-first; the shell may
  overlay more on narrow screens but is not separately optimized).

## 5. Verification

Load the page and confirm:
- Rail switches between Event input / Catalog / Map config; clicking the active icon
  (or the chevron) collapses the panel and re-opens it.
- **Calculate intensity** still draws MMI bands + epicenter marker and fits bounds.
- **Pull USGS feed** still ingests and refreshes the catalog.
- Clicking a catalog row still computes impact, draws bands, and renders the rollup
  table with a working level switcher — all inside the Catalog panel.
- Overlay checkboxes add/remove the correct layers; defaults (National + Provinces)
  are on at load.
- Basemap radios/select swap the basemap; OpenStreetMap is the default.
- The MMI legend still shows at bottom-right.
- Leaflet zoom / basemap controls are not hidden under the rail/panel.
