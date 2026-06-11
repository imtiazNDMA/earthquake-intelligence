# Left Sidebar Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the cramped single floating `#panel` with a fixed icon-rail + panel shell holding three switchable sections (Event input, Catalog, Map config), in a clean-minimal style, and move the overlay + basemap controls into the Map config panel.

**Architecture:** Pure frontend change in `web/index.html` (markup + CSS) and `web/app.js` (rail switching, collapse, and config-panel rendering of overlays/basemap). The `BASEMAPS` and `OVERLAYS` object definitions and all backend endpoints are unchanged — only the UI host for the controls moves. The shell floats above the map's left edge (`position:absolute`), matching how the old `#panel` floated.

**Tech Stack:** Vanilla JS + DOM, Leaflet 1.9.4, protomaps-leaflet 5.1.0 (all already loaded). No new dependencies. No JS test runner exists in this repo and adding one is out of scope (YAGNI); verification is manual browser observation against the running FastAPI static server.

**How to run for verification (used in every task):**

```bash
# From repo root. Serves web/ statically at http://127.0.0.1:8000/
uv run uvicorn eqmon.api:app --host 127.0.0.1 --port 8000
# or double-click start.bat
```
Then open `http://127.0.0.1:8000/`. The intensity Calculate button needs `data/Vs30.tif`; overlays, basemap, and catalog work without it.

**Reference — values reused across tasks:**
- Overlay names + swatch colors (from current `OVERLAYS` symbolizers in `app.js`):
  `National #444`, `Provinces #666`, `Districts #999`, `Tehsils #bbb`,
  `Faults #d00000`, `Plate boundaries #ff8800`, `Plates #ffcc66`.
- Overlays ON by default: `National`, `Provinces`.
- Basemap names (from current `BASEMAPS`): `OpenStreetMap`, `Humanitarian (HOT)`,
  `Topographic`, `Light (Positron)`, `Dark (Dark Matter)`, `Satellite (Esri)`.
  Default basemap: `OpenStreetMap`.
- Element ids that existing `app.js` handlers depend on and MUST be preserved:
  `magnitude`, `depth_km`, `lat`, `lon`, `calc`, `ingest`, `status`, `events`, `impact`.

---

### Task 1: New HTML shell + clean-minimal CSS

Replace the single `#panel` box with the `#sidebar` shell (rail + three section
containers). The existing event form moves into `#sec-event`; the `#events` and
`#impact` divs move into `#sec-catalog`; `#sec-config` gets two empty host divs
(`#overlay-list`, `#basemap-list`) filled by JS in Task 3. All required ids are
preserved, so the existing `app.js` keeps working. Rail switching is added in Task 2;
until then all three sections are visible stacked (acceptable interim state).

**Files:**
- Modify: `web/index.html` (the `<style>` block and the `<body>` `#panel` markup)

- [ ] **Step 1: Replace the `<style>` block**

Replace the entire current `<style>…</style>` in `web/index.html` with:

```html
  <style>
    html, body { margin: 0; height: 100%; font-family: system-ui, sans-serif; }
    #map { position: absolute; inset: 0; }

    /* --- Sidebar shell: icon rail + panel --- */
    #sidebar {
      position: absolute; z-index: 1000; top: 0; left: 0; bottom: 0;
      display: flex; align-items: stretch;
      box-shadow: 0 0 14px rgba(0,0,0,.12);
    }
    #sidebar .rail {
      width: 46px; background: #fafafa; border-right: 1px solid #eee;
      display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 8px 0;
    }
    .rail-ic {
      width: 32px; height: 32px; border: none; background: transparent; cursor: pointer;
      border-radius: 7px; font-size: 17px; line-height: 1; color: #888;
      display: flex; align-items: center; justify-content: center;
    }
    .rail-ic:hover { background: #eee; color: #333; }
    .rail-ic.active { background: #111; color: #fff; }
    .rail-collapse { margin-top: auto; font-size: 20px; }

    #panel-body {
      width: 260px; background: #fff; padding: 14px; box-sizing: border-box;
      overflow-y: auto;
    }
    #sidebar.collapsed #panel-body { display: none; }

    #panel-body h4 { margin: 0 0 8px; font-size: 13px; font-weight: 700; color: #1a1a1a; }
    #panel-body section + section { display: none; } /* JS controls visibility from Task 2 */

    .field-label {
      display: block; font-size: 10px; margin: 9px 0 2px; color: #999;
      text-transform: uppercase; letter-spacing: .4px;
    }
    .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    #panel-body input[type="number"] {
      width: 100%; box-sizing: border-box; padding: 6px;
      border: 1px solid #e2e2e2; background: #fafafa; border-radius: 5px; font-size: 13px;
    }
    .btn-primary {
      margin-top: 12px; width: 100%; padding: 9px; cursor: pointer; font-weight: 600;
      background: #111; color: #fff; border: none; border-radius: 6px;
    }
    .btn-secondary {
      margin-top: 8px; width: 100%; padding: 8px; cursor: pointer; font-size: 12px;
      background: #f0f0f0; color: #333; border: 1px solid #e2e2e2; border-radius: 6px;
    }
    #status { font-size: 12px; margin-top: 8px; color: #777; min-height: 16px; }

    #events { font-size: 12px; }
    #impact { margin-top: 10px; font-size: 12px; }

    /* Map config rows (overlays checklist + basemap radios) */
    .cfg-row {
      display: flex; align-items: center; gap: 7px;
      font-size: 12px; padding: 4px 0; cursor: pointer;
    }
    .cfg-row .swatch {
      width: 14px; height: 14px; border-radius: 3px; flex: none;
      border: 1px solid rgba(0,0,0,.15);
    }
    .cfg-group + .cfg-group { margin-top: 14px; }

    .legend { line-height: 18px; color: #333; }
    .legend i { width: 16px; height: 16px; float: left; margin-right: 6px; opacity: .8; }
  </style>
```

- [ ] **Step 2: Replace the `#panel` markup**

In `web/index.html`, replace the whole `<div id="panel">…</div>` block with:

```html
  <div id="sidebar">
    <div class="rail">
      <button class="rail-ic active" data-section="event" title="Event input">✚</button>
      <button class="rail-ic" data-section="catalog" title="Catalog">≣</button>
      <button class="rail-ic" data-section="config" title="Map config">⚙</button>
      <button id="rail-collapse" class="rail-ic rail-collapse" title="Collapse">‹</button>
    </div>
    <div id="panel-body">
      <section id="sec-event">
        <h4>Event input</h4>
        <div class="grid2">
          <div><span class="field-label">Magnitude</span>
            <input id="magnitude" type="number" value="6.5" step="0.1" /></div>
          <div><span class="field-label">Depth (km)</span>
            <input id="depth_km" type="number" value="10" step="1" /></div>
        </div>
        <div class="grid2">
          <div><span class="field-label">Latitude</span>
            <input id="lat" type="number" value="34.0" step="0.01" /></div>
          <div><span class="field-label">Longitude</span>
            <input id="lon" type="number" value="72.5" step="0.01" /></div>
        </div>
        <button id="calc" class="btn-primary">Calculate intensity</button>
        <button id="ingest" class="btn-secondary">Pull USGS feed</button>
        <div id="status"></div>
      </section>
      <section id="sec-catalog">
        <h4>Catalog</h4>
        <div id="events"></div>
        <div id="impact"></div>
      </section>
      <section id="sec-config">
        <h4>Map configuration</h4>
        <div class="cfg-group"><div class="field-label">Overlays</div>
          <div id="overlay-list"></div></div>
        <div class="cfg-group"><div class="field-label">Basemap</div>
          <div id="basemap-list"></div></div>
      </section>
    </div>
  </div>
```

Note: the inline styles previously on `#events`/`#impact` (max-height, overflow,
font-size) and on the `#ingest` button are now handled by the CSS in Step 1, so they
are intentionally dropped from the markup.

- [ ] **Step 3: Verify in browser**

Run: `uv run uvicorn eqmon.api:app --host 127.0.0.1 --port 8000`
Open `http://127.0.0.1:8000/`. Expected:
- A left shell with a thin rail (✚ ≣ ⚙ and a `‹` at the bottom) and a white panel.
- The Event input form renders in the panel with the 2×2 field grid, a black
  **Calculate intensity** button, and a gray **Pull USGS feed** button.
- Clicking **Calculate intensity** still draws MMI bands (if `data/Vs30.tif` exists)
  or shows an error in `#status` — proving the handler is still wired by id.
- The catalog list still populates under the form (sections are not yet switchable;
  `#sec-catalog`/`#sec-config` may be hidden by the `section + section` CSS rule —
  that's expected; Task 2 makes them reachable).

- [ ] **Step 4: Commit**

```bash
git add web/index.html
git commit -m "feat(ui): icon-rail + panel sidebar shell, clean-minimal theme"
```

---

### Task 2: Rail section switching + collapse

Add JS so the rail icons switch which `<section>` is visible, the active icon is
highlighted, clicking the active icon (or the `‹` button) collapses the panel to just
the rail, and clicking any icon re-opens it. Default visible section: Event input.

**Files:**
- Modify: `web/app.js` (append a new block; no existing logic changes)

- [ ] **Step 1: Append the rail controller to `web/app.js`**

Add at the end of `web/app.js`:

```javascript
// --- Sidebar rail: section switching + collapse ---
const SECTIONS = { event: "sec-event", catalog: "sec-catalog", config: "sec-config" };
let activeSection = "event";
let sidebarCollapsed = false;

function setCollapsed(value) {
  sidebarCollapsed = value;
  document.getElementById("sidebar").classList.toggle("collapsed", value);
  document.getElementById("rail-collapse").textContent = value ? "›" : "‹";
}

function showSection(key) {
  // Clicking the already-active icon toggles the panel closed.
  if (key === activeSection && !sidebarCollapsed) { setCollapsed(true); return; }
  activeSection = key;
  setCollapsed(false);
  for (const [k, id] of Object.entries(SECTIONS)) {
    document.getElementById(id).style.display = (k === key) ? "block" : "none";
  }
  document.querySelectorAll(".rail-ic[data-section]").forEach((b) =>
    b.classList.toggle("active", b.dataset.section === key));
}

document.querySelectorAll(".rail-ic[data-section]").forEach((b) =>
  b.addEventListener("click", () => showSection(b.dataset.section)));
document.getElementById("rail-collapse")
  .addEventListener("click", () => setCollapsed(!sidebarCollapsed));

showSection("event"); // default panel on load
```

- [ ] **Step 2: Verify in browser**

Reload `http://127.0.0.1:8000/`. Expected:
- Only **Event input** shows on load; ✚ is highlighted black.
- Clicking ≣ shows the **Catalog** section (list + impact area); ≣ highlights.
- Clicking ⚙ shows the **Map config** section (the "Overlays"/"Basemap" labels with
  empty lists for now); ⚙ highlights.
- Clicking the currently-active icon, or the bottom `‹` button, collapses the panel to
  just the rail and the button flips to `›`; clicking any icon re-opens it.

- [ ] **Step 3: Commit**

```bash
git add web/app.js
git commit -m "feat(ui): rail section switching and panel collapse"
```

---

### Task 3: Move overlays + basemap into the Map config panel

Render the overlay checklist and basemap radio list into `#overlay-list` /
`#basemap-list`, wired to the existing `OVERLAYS` and `BASEMAPS` layers. Remove the
floating `L.control.layers(...)` and the basemap cycle button (and its
`baselayerchange` handler), simplify `setBasemap`, and move the Leaflet zoom control to
the top-right so it is not hidden under the shell.

**Files:**
- Modify: `web/app.js` (the basemap/overlay control block, currently
  `L.control.layers(...)` through `basemapControl.addTo(map);`)

- [ ] **Step 1: Replace the Leaflet control block**

In `web/app.js`, delete this entire block (from the layers-control line through the
basemap button control)…

```javascript
L.control.layers(BASEMAPS, OVERLAYS, { collapsed: true }).addTo(map);

// --- Basemap switching button: click to cycle to the next basemap ---
// Leaflet's baselayerchange keeps `current` in sync whether the user switches
// via this button or the layer-control radios.
const BASEMAP_NAMES = Object.keys(BASEMAPS);
let currentBasemap = "OpenStreetMap";
function setBasemap(name) {
  map.removeLayer(BASEMAPS[currentBasemap]);
  BASEMAPS[name].addTo(map);
  currentBasemap = name;
  if (basemapBtn) basemapBtn.title = `Basemap: ${name} (click to switch)`;
}
map.on("baselayerchange", (e) => { currentBasemap = e.name; basemapBtn.title = `Basemap: ${e.name} (click to switch)`; });

const basemapControl = L.control({ position: "topleft" });
let basemapBtn;
basemapControl.onAdd = function () {
  const div = L.DomUtil.create("div", "leaflet-bar leaflet-control");
  basemapBtn = L.DomUtil.create("a", "", div);
  basemapBtn.href = "#";
  basemapBtn.textContent = "🗺";
  basemapBtn.title = `Basemap: ${currentBasemap} (click to switch)`;
  basemapBtn.style.cssText = "font-size:18px;text-align:center;line-height:30px";
  L.DomEvent.on(basemapBtn, "click", L.DomEvent.stop).on(basemapBtn, "click", () => {
    const next = (BASEMAP_NAMES.indexOf(currentBasemap) + 1) % BASEMAP_NAMES.length;
    setBasemap(BASEMAP_NAMES[next]);
  });
  return div;
};
basemapControl.addTo(map);
```

…and replace it with:

```javascript
// Move the zoom control clear of the left-edge sidebar shell.
map.zoomControl.setPosition("topright");

// --- Map config panel: overlay checklist + basemap radios ---
// Hosts the controls that used to be the floating Leaflet layer control.
// `BASEMAPS` / `OVERLAYS` are defined above and unchanged.
const BASEMAP_NAMES = Object.keys(BASEMAPS);
let currentBasemap = "OpenStreetMap";
function setBasemap(name) {
  if (name === currentBasemap) return;
  map.removeLayer(BASEMAPS[currentBasemap]);
  BASEMAPS[name].addTo(map);
  currentBasemap = name;
}

const OVERLAY_COLORS = {
  National: "#444", Provinces: "#666", Districts: "#999", Tehsils: "#bbb",
  Faults: "#d00000", "Plate boundaries": "#ff8800", Plates: "#ffcc66",
};
const OVERLAY_DEFAULT_ON = new Set(["National", "Provinces"]); // mirrors addTo() above

function buildConfigPanel() {
  const ovEl = document.getElementById("overlay-list");
  Object.keys(OVERLAYS).forEach((name) => {
    const row = document.createElement("label");
    row.className = "cfg-row";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = OVERLAY_DEFAULT_ON.has(name);
    cb.addEventListener("change", () => {
      if (cb.checked) OVERLAYS[name].addTo(map);
      else map.removeLayer(OVERLAYS[name]);
    });
    const sw = document.createElement("span");
    sw.className = "swatch";
    sw.style.background = OVERLAY_COLORS[name];
    const txt = document.createElement("span");
    txt.textContent = name;
    row.append(cb, sw, txt);
    ovEl.appendChild(row);
  });

  const bmEl = document.getElementById("basemap-list");
  BASEMAP_NAMES.forEach((name) => {
    const row = document.createElement("label");
    row.className = "cfg-row";
    const rb = document.createElement("input");
    rb.type = "radio";
    rb.name = "basemap";
    rb.checked = (name === currentBasemap);
    rb.addEventListener("change", () => { if (rb.checked) setBasemap(name); });
    const txt = document.createElement("span");
    txt.textContent = name;
    row.append(rb, txt);
    bmEl.appendChild(row);
  });
}
buildConfigPanel();
```

- [ ] **Step 2: Verify in browser**

Reload `http://127.0.0.1:8000/` and open the ⚙ **Map config** section. Expected:
- **Overlays:** seven checkboxes each with a colored swatch; **National** and
  **Provinces** are checked on load and their outlines show on the map. Toggling
  **Faults** / **Plate boundaries** / **Plates** etc. adds/removes the layer live.
- **Basemap:** six radios; **OpenStreetMap** selected. Selecting **Satellite (Esri)**
  or **Dark (Dark Matter)** swaps the basemap immediately.
- The Leaflet zoom **+ / −** buttons now sit at the **top-right**, not under the shell.
- The old floating layer control (top-right box) and the 🗺 cycle button (top-left)
  are gone.
- The MMI legend still shows at the bottom-right.

- [ ] **Step 3: Commit**

```bash
git add web/app.js
git commit -m "feat(ui): overlays + basemap controls hosted in Map config panel"
```

---

### Task 4: Full end-to-end verification

No code changes — a final pass confirming every flow in the spec's verification list
works together, then a no-op confirmation commit is skipped (nothing to commit).

- [ ] **Step 1: Run the server and walk every flow**

Run: `uv run uvicorn eqmon.api:app --host 127.0.0.1 --port 8000`, open
`http://127.0.0.1:8000/`, and confirm each:
- Rail switches Event input / Catalog / Map config; active-icon click and `‹`
  collapse + re-open the panel.
- **Calculate intensity** (Event input) draws MMI bands + epicenter and fits bounds
  (requires `data/Vs30.tif`; if absent, expect a clear error in `#status`).
- **Pull USGS feed** ingests and the Catalog list refreshes.
- Clicking a Catalog row computes impact, draws bands, and renders the rollup table
  with a working province/district/tehsil switcher — all inside the Catalog panel.
- Map config: overlay checkboxes add/remove the right layers (National + Provinces on
  by default); basemap radios swap the basemap (OpenStreetMap default).
- Zoom control is top-right and unobstructed; MMI legend is bottom-right.

- [ ] **Step 2: Confirm no regressions / leftover dead code**

Run: `git grep -n "L.control.layers\|basemapControl\|basemapBtn\|baselayerchange" web/`
Expected: no matches (all the old floating-control code was removed in Task 3).

---

## Self-Review Notes

- **Spec coverage:** §1 layout/structure → Tasks 1–2; §2 panels (Event/Catalog/Config)
  → Task 1 (markup) + Task 3 (config contents); §3 visual style → Task 1 CSS; §4
  implementation approach → Tasks 1–3; §5 verification → Task 4. MMI-legend-stays-
  floating is preserved (untouched in `app.js`). Zoom-not-hidden requirement →
  Task 3 `setPosition("topright")`.
- **Preserved ids:** `magnitude/depth_km/lat/lon/calc/ingest/status/events/impact`
  are all kept in Task 1 markup, so `calculate()`, the ingest handler,
  `refreshEvents()`, `showImpact()`, and `renderRollup()` need no changes.
- **Type/name consistency:** `setBasemap`, `currentBasemap`, `BASEMAP_NAMES`,
  `OVERLAYS`, `BASEMAPS` keep their existing names; `buildConfigPanel`, `showSection`,
  `setCollapsed`, `SECTIONS`, `OVERLAY_COLORS`, `OVERLAY_DEFAULT_ON` are new and used
  consistently. `currentBasemap`/`BASEMAP_NAMES`/`setBasemap` are declared exactly
  once (the duplicate Task-3 replacement removes the old declarations).
