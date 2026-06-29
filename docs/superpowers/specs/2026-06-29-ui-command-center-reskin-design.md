# UI Reskin — "Seismic Slate v2 · Command Center"

**Date:** 2026-06-29
**Status:** Approved (design)
**Type:** Front-end visual reskin (CSS + markup), no functional/API changes

## Goal

Give the web UI a fresh, modern **refined-command-center** look (Linear/Vercel/Geist
family): crisp, data-dense, restrained, with hairline borders, strong hierarchy,
Inter typography, and one decisive cool accent. **Dark theme leads** by default;
light remains as a refreshed toggle option.

The current "Seismic Slate" design system is already token-driven and coherent —
this is an evolution of it, not a teardown.

## Decisions (from brainstorming)

| Question | Decision |
| :-- | :-- |
| Scope | New visual identity, **same layout / IA** |
| Aesthetic | Refined command-center (Linear/Vercel/Geist) |
| Default theme | **Dark-default** (light kept via toggle) |
| Accent | Refined seismic **blue** (brighter, cleaner) |
| Typography | Switch UI sans to **Inter** (mono retained) |

## Non-Goals

- **No layout or IA changes** — the icon rail, panel set (Event input, Catalog,
  PAGER alerts, Analytics, Map config), dashboard view, map, and MMI legend stay
  where they are with the same behaviors.
- **No functional/JS behavior changes** beyond the one theme-default tweak and any
  class/markup hooks needed for styling. No API, no endpoints, no data flow.
- **No change to the domain-locked hazard ramp** — MMI band colors and the
  PAGER alert ramp (green/yellow/orange/red) are untouched. Brand never borrows
  hazard hues.
- No new dependencies beyond swapping the web-font family.

## Architecture / Approach

The styling is already variable-driven: `web/styles.css` defines `:root` tokens
and `:root[data-theme="dark"]` overrides; components consume the tokens. The reskin
is therefore primarily a **token + component-style rewrite**, so changes cascade
consistently across every surface.

**Files touched:**
- `web/styles.css` — token palette (dark-default + refreshed light), typography,
  elevation, and every component block.
- `web/index.html` — swap the Google Fonts link (IBM Plex Sans → Inter; keep a
  mono), update `<meta name="theme-color">`, and add a few styling hooks/classes
  where components currently rely on inline styles (e.g. the "Save to catalog"
  checkbox).
- `web/app.js` — **one** change: make the theme-init fallback default to dark
  (see below). Any other JS edits are limited to swapping inline styles for
  classes; no behavioral logic changes.

## Design Tokens

Concrete **starting** values (tuned in-browser during implementation). Dark is the
primary; light is the refreshed secondary.

### Dark (default / hero)
```
--bg:          #0B0F14   /* app background, behind map controls/panels */
--surface:     #111722   /* panels, cards */
--surface-2:   #19212E   /* nested fills, inputs, hover */
--border:      #222C3A   /* hairline borders (primary structural device) */
--text:        #E7ECF3
--text-muted:  #93A0B2   /* WCAG-AA on --surface */
--slate:       #C9D3E0   /* headings */
--slate-muted: #93A0B2

--brand:       #4C8DF5   /* refined seismic blue: primary actions, active nav, links, focus */
--brand-hover: #6AA1F8
--brand-tint:  rgba(76,141,245,.14)   /* selected rows, subtle fills */

--copper:      #E0954A   /* sparing secondary accent (compare "event 2", chart accent) */
--copper-tint: rgba(224,149,74,.14)

--ring:        0 0 0 3px rgba(76,141,245,.35)   /* focus-visible */
```

### Light (refreshed, toggle)
```
--bg:          #F6F8FB
--surface:     #FFFFFF
--surface-2:   #F0F3F7
--border:      #E3E8EF
--text:        #16202E
--text-muted:  #5A6675
--brand:       #2563EB   /* refined blue, light-mode tuned */
--brand-hover: #1D4FD7
--brand-tint:  #E8F0FE
```

### Elevation (command-center = borders, not shadows)
Lean on `--border` for structure; minimize drop shadows. Keep one soft shadow for
true popovers/overlays only.
```
--shadow-sm: 0 1px 2px rgba(0,0,0,.35)   /* dark; light variant softer */
--shadow-md: 0 4px 16px rgba(0,0,0,.40)  /* popovers/toasts only */
```

### Radii (slightly tightened)
`--r-sm: 4px; --r-md: 6px; --r-lg: 8px; --r-xl: 10px;`

### Semantic / hazard (UNCHANGED)
PAGER ramp (`--alert-green/yellow/orange/red`), `--danger`, and all MMI band hues
remain exactly as today.

## Typography

- **Inter** for UI sans (weights 400/500/600/700) + **IBM Plex Mono retained** for
  monospace / tabular data (good numerals, already in use). The Google Fonts
  `<link>` loads both families: `Inter:wght@400;500;600;700` and
  `IBM+Plex+Mono:wght@500;600`. `--font-sans` becomes Inter; `--font-mono` stays
  IBM Plex Mono.
- Type scale refined and kept compact: `--fs-xs 11 / --fs-sm 12 / --fs-base 13 /
  --fs-lg 15`, with tightened heading letter-spacing (~-0.01em) and comfortable
  line-heights.
- **Tabular figures** (`font-variant-numeric: tabular-nums`) applied to all numeric
  data: magnitudes, depths, coordinates, counts, analytics tables, legend values.

## Theme default behavior (the one JS change)

Current init (`web/app.js` ~L1678): reads `localStorage["eqmon-theme"]`; if unset,
follows `prefers-color-scheme`. **Change:** when no stored preference exists, default
to **dark** (dark leads). An explicit user toggle still persists and wins. Update
`<meta name="theme-color">` to the dark background/accent. (System-preference
following is intentionally dropped on first load in favor of dark-leads, per the
"dark-default" decision over "match system".)

## Component Treatment (same layout, refreshed)

All within the existing structure:

- **Icon rail:** crisp active state (accent pill/indicator bar), refined hover,
  consistent tooltips, accessible active/selected semantics preserved.
- **Panels:** hairline-bordered surfaces, consistent internal spacing scale,
  tighter section headers, clear single primary action per panel.
- **Buttons:** redefine primary / secondary / danger against the new accent; crisp
  hover/active and `:focus-visible` rings. (`btn-primary`, `btn-secondary`, etc.)
- **Inputs / selects / checkboxes:** one unified modern field style. Promote the
  bare inline-styled **"Save event to catalog"** checkbox (added recently) to a
  proper class-based control matching the system.
- **Catalog event rows:** cleaner rows with emphasized magnitude, aligned tabular
  figures, and tidy **source badges/chips** (MET / USGS / MANUAL) using neutral +
  accent treatments (never hazard hues).
- **MMI legend card:** refined surface, crisp band swatches (hazard colors intact),
  cleaner per-band checkboxes and the "Export shapefile" button.
- **Dashboard view** (`#dashboard-view` / `#dash-title`): typographic and surface
  refresh to match.
- **Map controls, toasts, loading spinners, empty states:** restyled to the new
  tokens for consistency.
- **Micro-interactions:** consistent transitions via existing motion tokens;
  unified `:focus-visible` ring.

## Accessibility (preserve + improve)

- Maintain existing focus-trap and keyboard navigation.
- All text and UI meets **WCAG AA contrast** in both themes (dark-default tuned for it).
- Visible `:focus-visible` rings on all interactive elements.
- Respect `prefers-reduced-motion` for transitions.

## Security posture (unchanged)

Keep the current external-resource approach (SRI on pinned scripts like Leaflet;
Google Fonts CSS link as today). Swapping the font family doesn't change the model.

## Verification

CSS/markup-only, so no automated test changes are expected and the **78-test suite
stays green** (run it to confirm). Manual verification:

- Browser-check **every panel** in **both dark and light** themes.
- Key flows still work and look right: calculate intensity, pull USGS/PMD feeds,
  source filter, catalog rows/badges, MMI legend + export, theme toggle, dashboard.
- A11y spot-checks: keyboard nav through rail + panels, focus rings visible,
  contrast sampled, reduced-motion honored.
- Screenshot before/after for the main views.

## Out of Scope (future, if wanted)

The bolder "structural rethink" options (floating/collapsible panels, command
palette, redesigned navigation/IA) — explicitly deferred.
