# PAGER Alerts Section — Design

**Date:** 2026-06-16
**Scope:** Frontend only (`web/index.html`, `web/styles.css`, `web/app.js`). No backend changes.

## Goal

A dedicated sidebar section that surfaces USGS **PAGER** alert levels — the
at-a-glance "what needs attention now" view for disaster-management decisions.

## Data

Single existing endpoint: `GET /events/stats`.
- `alert_dist` → `[{alert, count}]` (per-level totals).
- `top_significant` → `[{id, magnitude, place, sig, alert, tsunami, occurred_at}]`
  (significance-ranked events; includes `id` for click-through).

No new endpoint, no alert filter param, no auto-refresh timer.

## UI

**Rail.** A 5th section button (bell icon, `data-section="alerts"`), placed after
*Catalog*. Wires into existing `SECTIONS` / `RAIL_GLYPH` / `showSection` machinery.
New `<section id="sec-alerts">` with an `#alerts-body` container.

**Contents** (rendered by `renderAlerts()`, fetched on section open like the Dashboard):
1. **Counts summary** — colored-dot chips per level from `alert_dist`:
   🔴 red · 🟠 orange · 🟡 yellow · 🟢 green, mono counts.
2. **Active alerts list** — `top_significant` filtered to red/orange/yellow, sorted by
   severity (red>orange>yellow) then `sig` desc. Row: level dot · `M{mag}` · place ·
   (tsunami icon) · sig. Keyboard-operable (`role=button`, `tabindex=0`, Enter/Space).
   **Click → `showImpact(id)`** (renders MMI bands + epicenter on the map; reuses existing code).
3. **Reference legend** — four PAGER levels with standard fatality bands:
   - 🔴 Red — 1,000+ estimated fatalities; extensive impact
   - 🟠 Orange — 100–999; significant, national response likely
   - 🟡 Yellow — 1–99; local impact possible
   - 🟢 Green — no significant impact expected

## States

- Loading: inline spinner ("Loading alerts…").
- Error: inline message + error toast (reuse `toast()`).
- Empty: "No active PAGER alerts." when nothing is red/orange/yellow.

## Styling

All colors from the already-unified alert ramp tokens (`--alert-*`); section uses
existing tokens so it is light/dark-mode correct automatically.

## Out of scope (YAGNI)

New endpoint · per-event alert filter on the catalog · auto-refresh · notifications.
