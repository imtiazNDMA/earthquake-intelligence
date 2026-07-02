# UI Reskin — "Seismic Slate v2 · Command Center" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reskin the web UI to a dark-default, refined "command-center" look (Inter type, refined seismic-blue accent, hairline-border surfaces) without changing layout, behavior, or the hazard color ramp.

**Architecture:** The UI is already token-driven (`web/styles.css` defines `:root` + `:root[data-theme="dark"]` tokens; components consume them). This reskin rewrites the token palette and component styles so changes cascade. Only three files change: `web/styles.css` (palette + every component block), `web/index.html` (font link, `theme-color`, a couple of class hooks), and `web/app.js` (one theme-default line + inline-style→class swaps where noted). This is **verification-driven, not unit-test-driven**: there is no CSS test harness, so each task is verified by (a) the existing Python suite staying green and (b) browser checks in **both themes**.

**Tech Stack:** Vanilla CSS custom properties, HTML, vanilla JS, Leaflet. Inter + IBM Plex Mono via Google Fonts. App served by `uvicorn eqmon.api:app`.

## Global Constraints

- **Layout / IA unchanged.** No rearranging panels, rail, map, legend, or dashboard. No new navigation.
- **No functional/JS behavior changes** except: (1) the theme-default fallback line in `web/app.js`, and (2) swapping inline styles for CSS classes where a task says so. No API/endpoint/data-flow changes.
- **Hazard ramp is domain-locked and UNCHANGED:** MMI band colors and the PAGER ramp (`--alert-green #2E7D32`, `--alert-yellow #F9A825`, `--alert-orange #EF6C00`, `--alert-red #C62828`) keep their exact values. Brand never uses hazard hues.
- **Accessibility:** WCAG AA contrast in both themes; preserve focus-trap and keyboard nav; visible `:focus-visible` rings on all interactive elements; honor `prefers-reduced-motion` (the existing `@media` block at `styles.css:496` stays).
- **Security posture unchanged:** keep SRI on pinned scripts (e.g. Leaflet); Google Fonts loaded via `<link>` as today (no SRI on the font CSS, matching current).
- **Theme default:** dark on first load when no preference is stored; an explicit toggle persists in `localStorage["eqmon-theme"]` and wins.
- **Fonts:** Inter weights 400/500/600/700 + IBM Plex Mono 500/600. `--font-sans` = Inter, `--font-mono` = IBM Plex Mono.
- **Regression gate:** the full Python suite (currently **78 tests**) must stay green after every task. Run with `./.venv/Scripts/python.exe -m pytest -q`.

### Browser verification (used by most tasks)
Start the app once per task (or leave it running): `PYTHONPATH=src ./.venv/Scripts/python.exe -m uvicorn eqmon.api:app --host 127.0.0.1 --port 8014 --log-level warning &`, then open `http://127.0.0.1:8014/`. Toggle theme via the rail's theme button (moon/sun icon) to check **both** dark and light. Stop the server at the end of a task or leave it for the next.

---

### Task 1: Foundation — token palette, fonts, dark-default

**Files:**
- Modify: `web/styles.css` (the `:root` block ~L6-60 and `:root[data-theme="dark"]` block ~L66-91 — token values, elevation, radii)
- Modify: `web/index.html:14-15` (Google Fonts link), `web/index.html:11` (`theme-color`)
- Modify: `web/app.js` (theme-init fallback, ~L1678-1679)

**Interfaces:**
- Produces: the new token values every later task consumes (`--bg`, `--surface`, `--surface-2`, `--border`, `--text`, `--text-muted`, `--slate`, `--slate-muted`, `--brand`, `--brand-hover`, `--brand-tint`, `--copper`, `--copper-tint`, `--ring`, `--shadow-*`, `--r-*`, `--font-sans`, `--font-mono`). Names are unchanged; only values change.

- [ ] **Step 1: Swap the font link and theme-color in `web/index.html`**

Replace the IBM Plex link (`index.html:14-15`) with Inter + IBM Plex Mono:
```html
  <link rel="stylesheet"
        href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500;600&family=Inter:wght@400;500;600;700&display=swap" />
```
Change `index.html:11` to the dark background:
```html
  <meta name="theme-color" content="#0B0F14" />
```

- [ ] **Step 2: Rewrite the `:root` (light, refreshed) tokens in `web/styles.css`**

In the `:root` block, set the neutral + brand + font tokens (leave the PAGER/danger ramp lines exactly as they are):
```css
  --brand:        #2563EB;
  --brand-hover:  #1D4FD7;
  --brand-tint:   #E8F0FE;

  --slate:        #16202E;
  --slate-muted:  #5A6675;

  --bg:           #F6F8FB;
  --surface:      #FFFFFF;
  --surface-2:    #F0F3F7;
  --border:       #E3E8EF;
  --text:         #16202E;
  --text-muted:   #5A6675;

  --ring: 0 0 0 3px rgba(37,99,235,.30);

  --shadow-sm: 0 1px 2px rgba(16,32,52,.06);
  --shadow-md: 0 4px 16px rgba(16,32,52,.10);
  --shadow-lg: 0 10px 28px rgba(16,32,52,.16);

  --r-sm: 4px; --r-md: 6px; --r-lg: 8px; --r-xl: 10px;

  --font-sans: "Inter", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;
```

- [ ] **Step 3: Rewrite the `:root[data-theme="dark"]` tokens (dark, hero)**

```css
  --brand:        #4C8DF5;
  --brand-hover:  #6AA1F8;
  --brand-tint:   rgba(76,141,245,.14);

  --slate:        #C9D3E0;
  --slate-muted:  #93A0B2;

  --copper:       #E0954A;
  --copper-tint:  rgba(224,149,74,.14);

  --bg:           #0B0F14;
  --surface:      #111722;
  --surface-2:    #19212E;
  --border:       #222C3A;
  --text:         #E7ECF3;
  --text-muted:   #93A0B2;

  --ring: 0 0 0 3px rgba(76,141,245,.35);
  --shadow-sm: 0 1px 2px rgba(0,0,0,.35);
  --shadow-md: 0 4px 16px rgba(0,0,0,.40);
  --shadow-lg: 0 10px 28px rgba(0,0,0,.50);
```
(Keep the existing dark-mode hazard/alert overrides below these lines.)

- [ ] **Step 4: Make dark the default in `web/app.js`**

At the theme-init (`app.js:1678-1679`), change the fallback so dark leads when nothing is stored:
```js
  try { mode = localStorage.getItem("eqmon-theme"); } catch (e) { /* ignore */ }
  if (!mode) mode = "dark";
```

- [ ] **Step 5: Run the Python suite (regression gate)**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: `78 passed`.

- [ ] **Step 6: Browser-verify**

Start the server (see Global Constraints) and open `http://127.0.0.1:8014/`. Confirm: app loads **dark by default**; body text is Inter (not IBM Plex); no console errors except the favicon 404; theme toggle flips to the refreshed light palette and back; `localStorage["eqmon-theme"]` persists the choice.

- [ ] **Step 7: Commit**

```bash
git add web/styles.css web/index.html web/app.js
git commit -m "feat(ui): dark-default command-center token palette + Inter"
```

---

### Task 2: Dark-safety — tokenize hardcoded light-mode colors

Several rules hardcode pale hex fills that only work on light surfaces; on the new dark default they look wrong. Replace them with translucent/token values that work in both themes. (The dark block already does this for alert chips at `styles.css:92`; extend the same idea.)

**Files:**
- Modify: `web/styles.css` (the specific rules below)

**Interfaces:**
- Consumes: Task 1 tokens. Produces: nothing new (visual correctness only).

- [ ] **Step 1: Replace hardcoded fills with translucent equivalents**

Update these rules so they read on both themes:
```css
/* alert chips on event cards — use translucent tints, not pastel hex */
.evt-alert.green  { background: color-mix(in srgb, var(--alert-green) 16%, transparent);  color: var(--alert-green); }
.evt-alert.yellow { background: color-mix(in srgb, var(--alert-yellow) 18%, transparent); color: var(--alert-yellow); }
.evt-alert.orange { background: color-mix(in srgb, var(--alert-orange) 16%, transparent); color: var(--alert-orange); }
.evt-alert.red    { background: color-mix(in srgb, var(--alert-red) 16%, transparent);    color: var(--alert-red); }

/* destructive hovers — translucent danger, not #FBEAE7 */
.btn-del-detail:hover { background: color-mix(in srgb, var(--danger) 14%, transparent); }
.evt-del:hover        { color: var(--danger); background: color-mix(in srgb, var(--danger) 14%, transparent); }

/* compare "exit" border — token, not #F0C6C0 */
#compare-bar .cmp-exit { background: transparent; color: var(--danger); border-color: color-mix(in srgb, var(--danger) 45%, transparent); }
```
Then scan the file for any remaining literal `#` hex inside component rules (not the `:root`/dark token blocks, not the hazard ramp) and convert each to the nearest token or a `color-mix` of one. Leave all MMI/PAGER hazard hues alone.

- [ ] **Step 2: Run the suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: `78 passed`.

- [ ] **Step 3: Browser-verify (dark + light)**

In dark theme, open the **Catalog** (event rows with alert chips), hover a delete button, and the **Compare** exit control — confirm fills are subtle/legible, not pale boxes. Repeat in light theme.

- [ ] **Step 4: Commit**

```bash
git add web/styles.css
git commit -m "fix(ui): tokenize hardcoded light-mode fills for dark-safety"
```

---

### Task 3: Typography & base elements

**Files:**
- Modify: `web/styles.css` (Type tokens ~L50-51, base `html, body` L98, headings/links)

**Interfaces:**
- Consumes: Task 1 `--font-sans`. Produces: refined type scale used everywhere.

- [ ] **Step 1: Refine the type scale and base rules**

Keep the compact scale, add tabular numerals globally for data, tighten heading tracking:
```css
/* in :root Type block */
  --fs-xs: 11px; --fs-sm: 12px; --fs-base: 13px; --fs-lg: 15px;

/* base */
html, body { margin: 0; height: 100%; font-family: var(--font-sans); color: var(--text); background: var(--bg);
             -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility; }
#panel-body h4 { margin: 0 0 8px; font-size: var(--fs-base); font-weight: 600; color: var(--slate); letter-spacing: -.01em; }
a { color: var(--brand); }
/* tabular figures for all numeric UI */
.evt-mag, .evt-meta, .legend-label, .pager-mag, .pager-sig, .dash-stat-val,
.filter-mag, input[type="number"], .ov-width { font-variant-numeric: tabular-nums; }
```

- [ ] **Step 2: Run the suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: `78 passed`.

- [ ] **Step 3: Browser-verify**

Confirm headings render in Inter with slightly tighter tracking; magnitudes/coords/stat values align as tabular figures; both themes.

- [ ] **Step 4: Commit**

```bash
git add web/styles.css
git commit -m "feat(ui): Inter type scale + tabular figures for data"
```

---

### Task 4: Navigation rail + panel shell

**Files:**
- Modify: `web/styles.css` (`#sidebar`, `.rail`, `.rail-ic*` L102-122; `#panel-body` L124-142)

**Interfaces:**
- Consumes: Task 1 tokens. Produces: shell styling; no class/markup changes.

- [ ] **Step 1: Restyle the rail + panel surfaces**

Command-center treatment: hairline borders, an accent indicator for the active rail item, crisp hover:
```css
.rail-ic { color: var(--slate-muted); border-radius: var(--r-md); transition: background var(--dur-fast) var(--ease), color var(--dur-fast) var(--ease); }
.rail-ic:hover { background: var(--surface-2); color: var(--slate); }
.rail-ic.active { background: var(--brand-tint); color: var(--brand); box-shadow: none; position: relative; }
.rail-ic.active::before { content: ""; position: absolute; left: -1px; top: 50%; transform: translateY(-50%); width: 3px; height: 18px; border-radius: 2px; background: var(--brand); }
#panel-body { border-left: 1px solid var(--border); background: var(--surface); }
.field-label { color: var(--text-muted); }
```
(Keep existing layout/positioning declarations in `#sidebar`, `.rail`, `#panel-body` — only adjust color/border/active treatment.)

- [ ] **Step 2: Run the suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: `78 passed`.

- [ ] **Step 3: Browser-verify**

Click through all rail sections (Event input, Catalog, PAGER, Analytics, Map config); confirm the active item shows the accent indicator and panels read as hairline-bordered surfaces; both themes.

- [ ] **Step 4: Commit**

```bash
git add web/styles.css
git commit -m "feat(ui): refined rail active state + panel surfaces"
```

---

### Task 5: Buttons + unified focus ring

**Files:**
- Modify: `web/styles.css` (button rules L149-169, `.btn-edit` L222, `.btn-refresh` L230, `.btn-del-detail` L236, `.export-btn` L336, `.legend-export` L501; focus rule L172-174)

**Interfaces:**
- Consumes: Task 1 tokens. Produces: button system + `:focus-visible` ring used app-wide.

- [ ] **Step 1: Redefine button variants + focus-visible**

```css
.btn-primary { background: var(--brand); color: #fff; border: 1px solid var(--brand); border-radius: var(--r-md); font-weight: 600; }
.btn-primary:hover { background: var(--brand-hover); border-color: var(--brand-hover); box-shadow: none; }
.btn-secondary { background: var(--surface-2); color: var(--slate); border: 1px solid var(--border); border-radius: var(--r-md); }
.btn-secondary:hover { border-color: var(--brand); color: var(--brand); background: var(--surface-2); }
/* unified focus ring on every interactive element */
:focus-visible { outline: none; box-shadow: var(--ring); border-radius: var(--r-sm); }
input:focus-visible, select:focus-visible { border-color: var(--brand); box-shadow: var(--ring); }
```
Confirm `.btn-refresh` (primary-like), `.btn-edit`, `.btn-del-detail`, `.export-btn`, `.legend-export` still read correctly with the new tokens; adjust their `background`/`border` to tokens if any literal colors remain.

- [ ] **Step 2: Run the suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: `78 passed`.

- [ ] **Step 3: Browser-verify**

Check Calculate intensity (primary), Pull USGS/PMD feed (secondary), Export shapefile, and tab-focus several controls to confirm the consistent accent focus ring; both themes.

- [ ] **Step 4: Commit**

```bash
git add web/styles.css
git commit -m "feat(ui): button variants + unified focus-visible ring"
```

---

### Task 6: Inputs, selects, checkboxes + the Save-to-catalog control

**Files:**
- Modify: `web/styles.css` (`#panel-body input[type=number]` L143, `.filter-row input/select` L325-333, `.cfg-row` inputs L289)
- Modify: `web/index.html` (the "Save event to catalog" label/checkbox added earlier — replace inline styles with a class)
- Modify: `web/styles.css` (add the `.save-catalog` class rule)

**Interfaces:**
- Consumes: Task 1 tokens + Task 5 focus ring. Produces: `.save-catalog` class.

- [ ] **Step 1: Unify field styling**

```css
#panel-body input[type="number"], .filter-row input, .filter-row select, .filter-date {
  background: var(--surface-2); color: var(--text); border: 1px solid var(--border); border-radius: var(--r-sm);
}
.cfg-row input[type="checkbox"], .cfg-row input[type="radio"], .legend-cb, .save-catalog input { accent-color: var(--brand); }
.save-catalog { display: flex; align-items: center; gap: 6px; font-size: var(--fs-sm); margin: 2px 0; cursor: pointer; color: var(--text-muted); }
```

- [ ] **Step 2: Replace the inline-styled checkbox in `web/index.html`**

Change the inline-styled label to the class:
```html
        <label class="save-catalog">
          <input id="save-catalog" type="checkbox" /> Save event to catalog
        </label>
```

- [ ] **Step 3: Run the suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: `78 passed`.

- [ ] **Step 4: Browser-verify**

In the Event input panel confirm inputs/selects share the new field style and the Save-to-catalog checkbox matches the system; check the Catalog filter row and Map config checkboxes/radios; both themes. Verify a calc with the box checked still saves (then delete that test event).

- [ ] **Step 5: Commit**

```bash
git add web/styles.css web/index.html
git commit -m "feat(ui): unified field styling + class-based save-to-catalog control"
```

---

### Task 7: Catalog event rows, source badges, detail card

**Files:**
- Modify: `web/styles.css` (`.evt*` L177-216, `.evt-detail` card)
- Modify: `web/app.js` (the event-row render — add a `evt-source` class span around `${ev.source}` so the badge can be styled; locate via the `.evt-meta` line that renders `${ev.source} · ...`)
- Add: `web/styles.css` `.evt-source` badge rule

**Interfaces:**
- Consumes: Task 1 tokens. Produces: `.evt-source` badge class.

- [ ] **Step 1: Add a source-badge hook in `web/app.js`**

In the event-card template (the `evt-meta` line currently `${ev.source} · ${new Date(...)}`), wrap the source:
```js
<div class="evt-meta"><span class="evt-source ${ev.source.toLowerCase()}">${ev.source}</span> · ${new Date(ev.occurred_at).toLocaleString()}</div>
```

- [ ] **Step 2: Style rows + the source badge**

```css
.evt { border-bottom: 1px solid var(--border); }
.evt:hover { background: var(--surface-2); box-shadow: inset 0 0 0 1px var(--border); }
.evt-mag { font-family: var(--font-mono); font-weight: 600; }
.evt-source { font-size: 9px; font-weight: 600; letter-spacing: .03em; text-transform: uppercase;
  padding: 1px 5px; border-radius: 3px; border: 1px solid var(--border); color: var(--text-muted); }
.evt-source.met    { color: var(--brand);  border-color: color-mix(in srgb, var(--brand) 45%, transparent); }
.evt-source.usgs   { color: var(--slate-muted); }
.evt-source.manual { color: var(--copper); border-color: color-mix(in srgb, var(--copper) 45%, transparent); }
.evt-detail { background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--r-md); }
```

- [ ] **Step 3: Run the suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: `78 passed`.

- [ ] **Step 4: Browser-verify**

Open the Catalog with MET/USGS/MANUAL events present; confirm magnitude emphasis, tabular alignment, and distinct source badges; click an event to confirm the detail card; both themes. (Badges must not use hazard hues.)

- [ ] **Step 5: Commit**

```bash
git add web/styles.css web/app.js
git commit -m "feat(ui): catalog rows + source badges + detail card"
```

---

### Task 8: Legend, map config, compare, timeline

**Files:**
- Modify: `web/styles.css` (`.legend*` L301-320, L500-508; `.cfg-row` L284-299; `#compare-bar`/`.cmp-*` L362-376; `#tl-*` L354-360)

**Interfaces:**
- Consumes: Task 1 tokens. Produces: nothing new. **MMI swatch colors stay as the data provides them.**

- [ ] **Step 1: Restyle these surfaces with tokens**

```css
.legend { background: var(--surface); border: 1px solid var(--border); box-shadow: var(--shadow-md); border-radius: var(--r-lg); }
.legend-title { color: var(--slate); font-weight: 600; }
.legend-item.active { background: var(--brand-tint); }
.cfg-row .ov-width, .ov-color { border-radius: var(--r-sm); }
#compare-bar button { background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--r-sm); }
#compare-bar .cmp-show { background: var(--brand); color: #fff; border-color: var(--brand); }
.cmp-toggle.active { background: var(--brand); color: #fff; border-color: var(--brand); }
.tl-title { color: var(--text-muted); }
```
Do **not** alter `.legend-swatch` background (set inline from MMI data) or the `.cmp-radio.selected2`/copper accents.

- [ ] **Step 2: Run the suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: `78 passed`.

- [ ] **Step 3: Browser-verify**

Calculate an intensity to show the legend; confirm the legend card, per-band swatches (unchanged hazard colors) + checkboxes + Export button. Open Map config and Compare mode; both themes.

- [ ] **Step 4: Commit**

```bash
git add web/styles.css
git commit -m "feat(ui): legend, map config, compare, timeline surfaces"
```

---

### Task 9: Dashboard + PAGER surfaces

**Files:**
- Modify: `web/styles.css` (`#dashboard-view`/`.dash-*` L378-407; `.pager-*` L423-446)

**Interfaces:**
- Consumes: Task 1 tokens. Produces: nothing new.

- [ ] **Step 1: Restyle dashboard + PAGER with tokens**

```css
#dash-title-main { font-weight: 700; letter-spacing: -.01em; color: var(--slate); }
.dash-card, .dash-stat-box { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg); }
.dash-stat-val { font-family: var(--font-mono); color: var(--slate); }
.pager-chip { background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--r-md); }
.pager-row:hover { background: var(--surface-2); }
```
Keep `.pager-dot` colors (hazard) and any data-driven chart colors as-is.

- [ ] **Step 2: Run the suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: `78 passed`.

- [ ] **Step 3: Browser-verify**

Open Analytics (dashboard view) and the PAGER alerts panel; confirm cards/stat boxes/chips read as hairline surfaces and charts still render; both themes.

- [ ] **Step 4: Commit**

```bash
git add web/styles.css
git commit -m "feat(ui): dashboard + PAGER surfaces"
```

---

### Task 10: States — toasts, spinner, skeleton, confirm dialog

**Files:**
- Modify: `web/styles.css` (`.toast*` L448-476; `.spinner` L479; `.skeleton`/`.skel-*` L486-493; `#confirm-overlay`/`#confirm-box` L252-282)

**Interfaces:**
- Consumes: Task 1 tokens. Produces: nothing new.

- [ ] **Step 1: Align state components to the new tokens**

The toast/spinner/skeleton already use tokens; verify they read on dark and adjust only literals. Confirm the confirm-dialog buttons use tokens:
```css
.toast { background: var(--surface); border: 1px solid var(--border); box-shadow: var(--shadow-lg); }
#confirm-box { background: var(--surface); border: 1px solid var(--border); box-shadow: var(--shadow-lg); }
#confirm-cancel { background: var(--surface-2); color: var(--slate); }
#confirm-cancel:hover { background: var(--border); }
```
The `@media (prefers-reduced-motion)` block at `styles.css:496` stays unchanged.

- [ ] **Step 2: Run the suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: `78 passed`.

- [ ] **Step 3: Browser-verify**

Trigger a toast (e.g. pull a feed), observe a spinner/loading state, and open the delete-confirmation dialog; confirm all read correctly on dark + light.

- [ ] **Step 4: Commit**

```bash
git add web/styles.css
git commit -m "feat(ui): toast/spinner/skeleton/confirm state styling"
```

---

### Task 11: Final verification sweep + before/after

**Files:** none (verification only; small polish commit if needed)

- [ ] **Step 1: Full regression gate**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: `78 passed`.

- [ ] **Step 2: Both-theme sweep of every panel**

With the server running, in **dark then light**: Event input, Catalog (rows/badges/detail/filter), PAGER, Analytics dashboard, Map config; plus legend + export after a calc. Screenshot dark and light of the main map view and the dashboard for the PR.

- [ ] **Step 3: Accessibility spot-checks**

Keyboard-tab through the rail and a panel (focus rings visible, focus-trap intact in the confirm dialog); sample text contrast on `--surface` in dark; verify `prefers-reduced-motion` still suppresses animation (DevTools emulation). Confirm no new console errors beyond the favicon 404.

- [ ] **Step 4: Optional polish commit**

If the sweep surfaces small fixes, apply and commit:
```bash
git add web/styles.css web/index.html web/app.js
git commit -m "polish(ui): command-center reskin final pass"
```

---

## Self-Review

**Spec coverage:**
- Dark-default palette → Task 1. Refreshed light → Task 1. Inter + tabular → Tasks 1, 3. Theme-default JS change → Task 1. Hairline-border command-center look → Tasks 2,4–10. Rail/panels → Task 4. Buttons/inputs/checkbox (incl. save-to-catalog promotion) → Tasks 5,6. Catalog rows + source badges → Task 7. Legend/map config/compare/dashboard/PAGER → Tasks 8,9. Toasts/loading/empty/confirm + reduced-motion → Task 10. Hazard ramp untouched → asserted in Global Constraints + Tasks 2,8,9. A11y (focus, contrast, keyboard, reduced-motion) → Global Constraints + Task 11. Verification (both themes, suite green, screenshots) → every task + Task 11. All spec sections map to a task.
- **Dark-safety of hardcoded fills** (not explicit in the spec but required by dark-default) → added as Task 2.

**Placeholder scan:** No "TBD"/"add appropriate styling"/vague steps — every CSS step lists concrete selectors and declarations. Exact pixel/hue fine-tuning is explicitly an in-browser verification activity per the spec, not a placeholder.

**Type/name consistency:** Token names (`--brand`, `--surface-2`, `--font-sans`, etc.) are used identically across tasks and match the existing `styles.css`. New classes introduced and reused consistently: `.save-catalog` (Task 6), `.evt-source` + `.evt-source.{met,usgs,manual}` (Task 7). The `#save-catalog` input id is unchanged (preserves the `app.js` reference). Theme key `localStorage["eqmon-theme"]` matches existing code.
