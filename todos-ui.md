# eqMonitoring2 — UI/UX & Frontend Improvement Roadmap

> Scope: `web/index.html` (255-line inline `<style>`) + `web/app.js` (~1,240 lines).
> Stack: vanilla JS, Leaflet 1.9, protomaps-leaflet, Chart.js 4. No build step.
> Goal: a calm, authoritative, "government command-center" look — professional palette,
> one coherent icon language, and restrained, purposeful motion.

Legend: 🔴 high impact / low effort · 🟡 medium · 🟢 polish · ⏳ larger effort

---

## ✅ Shipped (2026-06-16) — "Seismic Slate" palette + unified icon language

- **Design tokens** (`web/styles.css` `:root`): full color/spacing/radii/shadow/type/motion scale.
- **Inline `<style>` extracted** to `web/styles.css`; `index.html` links it + `<meta theme-color>`.
- **Palette applied** across CSS + JS: brand `#0F4C81` for primary buttons/active rail/links;
  muted grays → WCAG-safe `--text-muted`; dashboard hero re-tuned to brand; alert ramp unified
  to PAGER tokens (badges, timeline dots, doughnut, "top significant"); Chart.js palette (`C_`)
  + GR/moment/rate/diurnal fills recolored; compare event-1/2 → brand/copper.
- **Alert color-rail** added to catalog cards (left bar keyed to alert level).
- **Unified icon set**: rail glyphs + all action-button emoji (refresh/edit/save/delete/export)
  replaced with one inline-SVG set (Lucide-style, `currentColor`); `aria-label`s added.
- **Lordicon hook**: `<lord-icon>` loader wired; paste a "Copy CDN link" url into the
  `LORD_ICONS` registry in `app.js` (page urls included) to upgrade any icon to animated.
- **Motion**: section fade/slide-in, animated confirm dialog (backdrop fade + box pop),
  sliding sidebar collapse, button press states, refresh-spin, `prefers-reduced-motion` guard.
- **A11y**: global `:focus-visible` ring; tabular-nums on stats/magnitudes.
- Verified in-browser (Playwright): icons render, palette live, active state correct, no JS errors.

### Dark mode (2026-06-16, follow-up)
- `:root[data-theme="dark"]` token overrides + `color-scheme` for native controls/scrollbars.
- Rail **sun/moon toggle**; choice persists in `localStorage`, defaults to `prefers-color-scheme`.
- Canvas views re-themed (Chart.js `defaults.color`/`borderColor`, timeline grid/axis/dot-ring,
  doughnut segment dividers) since canvas can't read CSS vars.
- Translucent alert chips for dark; de-hardcoded the stray white "min mag" input.
- Verified in-browser: dark applies + persists across reload, all inputs themed, no JS errors.

### Loading + toast states (2026-06-16, follow-up)
- **Toast system** (`toast(msg, type)`): success/error/warn/info, top-right, slide+fade in,
  auto-dismiss (pauses on hover), dismiss button, `aria-live`/`role=alert`. Self-creates host.
- **Loading states**: catalog **skeleton shimmer** while fetching; inline `.spinner` for
  intensity calc, impact compute, dashboard load, and the ingest button (disabled + "Pulling…").
- **Routed through toasts** (replacing silent failures / status-line text): ingest result,
  delete, edit-save, USGS-refresh, export, and all calc/impact/catalog/stats errors.
- Verified in-browser: all three toast types render + auto-dismiss, skeleton renders, no JS errors.

### Typography + catalog density (2026-06-16, follow-up)
- **Typeface**: IBM Plex Sans (body, via Google Fonts + preconnect, `display=swap`) with a
  system-stack fallback; `--font-sans` / `--font-mono` tokens.
- **IBM Plex Mono on data readouts**: catalog magnitudes, dashboard stat values, MMI legend
  numbers — instrument-panel feel, tabular figures. Chart.js `font.family` set to match.
- **Catalog cards redesigned**: more padding/rhythm, magnitude promoted (mono, 15px, leading),
  alert color-rail per card, bolder place line, muted tabular metadata, hover inset ring.
- Verified in-browser: both Plex faces load + apply (mono at weight 600), cards render cleanly.

**Skipped per request:** responsive/mobile.

### Accessibility batch (2026-06-16, follow-up)
- **Accessible confirm dialog**: `role="dialog"` + `aria-modal` + `aria-labelledby`; opens with
  focus on the safe default (Cancel); Tab/Shift+Tab trapped between the two buttons; `Esc` closes;
  focus restored to the triggering control on close. Fixed the `visibility`-transition focus trap
  (instant on open via `visibility 0s`, delayed on close) so the dialog is focusable immediately.
- **Rail = ARIA toolbar**: `role="toolbar"` + `aria-orientation="vertical"`; Arrow/Home/End move
  focus between buttons.
- **Catalog cards keyboard-operable**: `tabindex="0"` + Enter/Space activation (delete button
  still reachable via Tab; key events on it are ignored by the card).
- **Live region + labels**: `#status` is `role="status" aria-live="polite"`; `aria-label`s on all
  catalog filter controls; toasts already announce via their `aria-live` host.
- Verified in-browser (Playwright): focus/trap/Esc/restore, arrow nav, and card-Enter all pass.

**Note for future testing:** `python -m http.server` lets the browser cache `styles.css`/`app.js`,
so re-test on a fresh port (or hard-reload) after edits — stale cache caused false failures here.

### Emoji → SVG + SRI (2026-06-16, follow-up)
- **Finished the icon language**: detail-card informational emoji converted to the inline-SVG set
  — 📍→pin, 👤→user, ⚡→zap, 🏛→building (ShakeMap), 🌀→target (moment tensor), 📊→chart (DYFI),
  ⚙→settings (focal mechanism), 🌊→waves (tsunami, tinted brand). No emoji remain in the UI.
- **Subresource Integrity** added to the two unprotected CDN scripts (Leaflet/protomaps already
  had it): Chart.js 4.4.7 (`sha384-vsrfeLOOY6Ku…`) and the Lordicon loader (`sha384-bf8L80dN…`),
  both with `crossorigin` (verified both CDNs send `Access-Control-Allow-Origin: *`).
  - Caveat documented in `index.html`: the Lordicon loader is evergreen, so a future update will
    fail the hash and be blocked → icons fall back to SVG. Refresh the hash or self-host to re-enable.
  - Google Fonts CSS can't carry SRI (generated/variable) — left as-is.
- Verified in-browser: both scripts load through SRI (Chart + lord-icon defined), all detail-card
  icons are SVG, zero emoji left.

### Dark Matter basemap auto-switch (2026-06-16, follow-up)
- Dark mode auto-switches the basemap to **Dark (Dark Matter)**; light mode restores **OpenStreetMap**.
- **Respects the user**: once they pick a basemap from the config panel (`_userPickedBasemap`),
  the theme never overrides it again. Config-panel radios stay in sync with the auto-switch.
- Verified in-browser: dark→Dark Matter (tiles actually load), light→OSM, and a manual pick is
  preserved across theme toggles.

---

**🎉 Core UI/UX backlog shipped.** Design tokens · Seismic Slate palette · dark mode (+ basemap
sync) · unified inline-SVG icon language (+ Lordicon hook) · motion/transitions · toasts +
loading/skeleton states · IBM Plex typography · denser catalog cards · accessibility (dialog
focus-trap, keyboard nav, live regions, labels) · Subresource Integrity. All verified in-browser
via Playwright.

**Remaining (optional polish)** — see unchecked boxes in §0–§6 below:
favicon/app title · MMI palette single-source with `contours.py` (`[~]` partial) · uppercase label
convention pass · per-card stagger-fade (skeleton shipped instead) · map-layer fade + epicenter
pulse · richer empty state (icon + CTA) · responsive/mobile (skipped per request).

> Checklist legend: `[x]` done · `[~]` partial · `[ ]` open.

---

## 0. Foundations (do these first — everything else depends on them)

- [x] 🔴 **Introduce a design-token layer.** Define one `:root { --… }` block (colors, spacing,
      radii, shadows, type scale). Today the same hex values are hand-typed in ~50 places across
      CSS *and* JS — e.g. alert colors exist twice: CSS `.evt-alert.green` and JS `AC`/`alertColors`.
      A token layer makes theming (and dark mode) a one-file change.
- [x] 🔴 **Move the inline `<style>` block into `web/styles.css`.** 255 lines in `<head>` is hard to
      diff and impossible to cache. Link it instead.
- [~] 🟡 **Single source of truth for the MMI & alert palettes.** _(partial: alert ramp unified across CSS/JS; MMI still dual-sourced with `contours.py`)_ Export them once (a small JS
      constant + matching CSS vars) and have `contours.py`, the legend, the timeline dots, and the
      compare legend all read from it. Right now MMI colors live in `MMI_PALETTE` (app.js:256) *and*
      `_MMI_COLORS` in `contours.py` — they can drift.
- [~] 🟢 Add a `<meta name="theme-color">` and a favicon/app title that reflects the brand. _(theme-color done; favicon still open)_

---

## 1. Color & Theme

The current palette is essentially grayscale (`#111`, `#888`, `#999`, `#aaa`, `#bbb`) with a
black primary button and a lone green dashboard gradient. It reads as a prototype, not a platform.

**Proposed palette — "Seismic Slate" (professional, calm, high-trust):**

| Token | Light value | Use |
|---|---|---|
| `--bg` | `#f7f8fa` | app background |
| `--surface` | `#ffffff` | panels, cards |
| `--surface-2` | `#f1f3f5` | inset inputs, hover rows |
| `--border` | `#e4e7eb` | hairlines |
| `--text` | `#1a2230` | primary text |
| `--text-muted` | `#5b6675` | secondary (replaces `#999`/`#aaa` — those fail WCAG) |
| `--brand` | `#0f4c81` (deep seismic blue) | primary actions, active rail |
| `--brand-hover` | `#0c3d68` | |
| `--accent` | `#d97706` (amber) | warnings, secondary highlight |
| `--danger` | `#c0341d` | destructive |
| `--ring` | `rgba(15,76,129,.35)` | focus ring |

- [x] 🔴 Replace the black `#111` primary button + active rail with `--brand`. Black-on-white feels
      like an unstyled default; a deep blue reads as "official monitoring system."
- [x] 🔴 Bump all muted text to `--text-muted`. `#bbb`/`#ccc` on white (`.evt-sig`, `.evt-meta`,
      `.field-label`) is below the 4.5:1 contrast floor — fails accessibility audits.
- [x] 🟡 **Dark mode.** You already ship a "Dark Matter" basemap but the chrome stays white — jarring.
      With tokens, dark mode is a `@media (prefers-color-scheme: dark)` (or a `.theme-dark` class +
      toggle in the rail) override of the `:root` vars. High value for an ops tool used at night.
- [x] 🟢 Re-tune the dashboard hero gradient (`#dash-title`, currently green→green) to match `--brand`
      so the dashboard and map don't look like two different products.
- [x] 🟢 Define a consistent **alert color ramp** (green/yellow/orange/red) as tokens and apply the
      same fills to: catalog badges, timeline dots, dashboard doughnut, "top significant" bars.

---

## 2. Typography

- [x] 🟡 Adopt a real type system. `system-ui, sans-serif` is fine for body, but add **Inter**
      (or keep system stack) with an explicit **type scale** via tokens: `--fs-xs:11px`,
      `--fs-sm:12px`, `--fs-base:13px`, `--fs-lg:15px`, `--fs-xl:22px`. Today sizes are scattered
      (9px, 10px, 11px, 12px, 13px, 17px, 22px, 26px) with no rhythm.
- [x] 🟢 Use **tabular numbers** (`font-variant-numeric: tabular-nums`) on the dashboard stat values
      and magnitudes so digits don't jitter during the count-up animation.
- [ ] 🟢 Establish a label convention: uppercase + letter-spacing for section labels (already partly
      done in `.field-label` / `.tl-title`) and apply consistently.

---

## 3. Iconography (currently the weakest visual area)

The rail uses geometric Unicode glyphs (`✚ ≣ ◰ ⚙ ‹`) while detail cards use color emoji
(`🔄 ✏️ 💾 🏛 🌀 📊 ⚙ 📍 👤 ⚡ 🌊`). Two clashing visual languages; emoji render differently per OS.

- [x] 🟡 Adopt **one inline-SVG icon set** (Lucide or Feather — MIT, no build step needed; paste SVGs
      or load via CDN sprite). Replace rail glyphs and all emoji buttons with stroked SVGs that
      inherit `currentColor`. This single change does the most to make it look "designed."
- [x] 🟢 Give every icon-only control an `aria-label` (rail buttons have `title` but no accessible name).

---

## 4. Motion & Animation (make it feel sleek)

You already have good chart entrances (`easeOutQuart`, staggered `barDelay`, count-up). Extend that
restraint to the *chrome*, which is currently all instant `display:none` swaps.

- [x] 🔴 **Panel section transitions.** Switching rail sections hard-cuts (`display:block/none`,
      app.js:853). Add a subtle 150–200ms fade + 4px upward slide on the incoming `<section>`.
- [x] 🔴 **Confirm dialog.** `#confirm-overlay` toggles `display:flex` instantly (index.html:131).
      Add a backdrop fade + a `scale(.96)→1` pop on `#confirm-box` (200ms, `cubic-bezier(.2,.8,.2,1)`).
- [x] 🟡 **Sidebar collapse.** Animate the panel width (`width: 260px → 0` with `overflow:hidden`)
      instead of `display:none`, so it slides shut.
- [ ] 🟡 **Catalog list.** Stagger-fade event cards in on load/filter (60ms increments, capped). _(skeleton shimmer shipped instead; per-card stagger still open)_
- [ ] 🟢 **Map layers.** Fade intensity bands / epicenter marker in (opacity transition) rather than
      popping. A soft pulse on the epicenter `circleMarker` reads as "live."
- [x] 🟢 **Micro-interactions.** Add `:active` press states (`transform: translateY(1px)`) and
      `transition` on all buttons; you already have nice `.legend-item.active` scale — reuse that feel.
- [x] 🟢 **Respect `prefers-reduced-motion`** — wrap non-essential transitions so motion-sensitive
      users get instant swaps.

---

## 5. Layout, Components & States

- [x] 🔴 **Focus-visible rings everywhere.** No focus styles today → keyboard users are lost. Add
      `:focus-visible { outline: 2px solid var(--ring) }` on inputs, buttons, rail items.
- [x] 🟡 **Loading states.** "Calculating…" / "Computing impact…" are bare text. Add a small inline
      spinner and a skeleton shimmer on the catalog list while fetching.
- [ ] 🟡 **Empty states.** The "No events yet" line (app.js:401) is plain. Give it an icon + a clear
      CTA button ("Pull USGS feed") instead of just instructional text.
- [x] 🟡 **Catalog card density.** Cards pack mag/type/alert/tsunami/sig/place/source/date into tight
      gray rows. Increase line-height, promote magnitude to a clear lead, demote metadata. Add a thin
      left color-bar keyed to alert level for instant scannability.
- [x] 🟢 **Toasts instead of status-line text.** Ingest results ("Ingest: 3 new of 50") and errors
      currently land in `#status`. A transient toast (top-right, auto-dismiss) is more legible and
      doesn't compete with the form.
- [x] 🟢 **Card elevation system.** Standardize the three shadow depths you use ad-hoc
      (`0 1px 4px`, `0 2px 10px`, `0 8px 20px`) into `--shadow-sm/md/lg` tokens.
- [ ] ⏳ **Responsive / mobile.** _(skipped per request)_ Fixed 46px rail + 260px panel overlaps the map on phones. Add a
      breakpoint where the sidebar becomes a bottom sheet or a full-width drawer.

---

## 6. Accessibility (ties into "professional")

- [x] 🔴 Contrast pass (see §1) — target WCAG AA (4.5:1 text, 3:1 UI).
- [x] 🟡 `aria-label`s on icon buttons; `role="dialog"` + focus trap on the confirm overlay; `Esc`
      to close it.
- [x] 🟡 Keyboard nav for the rail and catalog list (arrow keys / Enter).
- [x] 🟢 Announce async results (intensity computed, ingest done) via an `aria-live="polite"` region.

---

## Suggested execution order

1. **Foundations** (§0) — tokens + external stylesheet. Unblocks everything.
2. **Color + contrast** (§1, §6 contrast) — biggest "looks professional" jump for least effort.
3. **Icons** (§3) — second-biggest visual upgrade.
4. **Motion** (§4) — panel/dialog transitions are the "sleek" payoff.
5. **States, dark mode, responsive** (§5, §1 dark, §5 mobile) — depth and robustness.

Each step is independently shippable and low-risk (no backend changes, no build step added).
