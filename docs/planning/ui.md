# Seismic Intelligence Platform UI/UX Redesign Plan

**Date:** 2026-07-24
**Status:** Proposed design plan
**Scope:** Frontend/UI/UX redesign of `web/index.html`, `web/app.js`, `web/styles.css`, and supporting frontend assets.
**Backend contract:** Preserved unless a later design decision explicitly requires a new read model or endpoint.

## 1. Direction

The portal should stop feeling like a collection of map controls around a form and become a focused **seismic operations console**: a place where an operator can understand what is happening, investigate one event, compare evidence, and move from signal to impact without losing map context.

The redesign may replace the current layout and visual language. The existing `Seismic Slate v2` reskin specification established a coherent token system, but it explicitly preserved the current information architecture. This plan reopens that constraint because the current rail-and-panel layout now carries too many workflows:

- Manual Event Input
- MMI intensity calculation
- Historical earthquake overlay
- Catalog filtering and impact inspection
- PMD and USGS ingestion
- Aftershock Probability
- Seismicity Analytics
- Map overlays and basemap configuration

The redesign should be visually distinctive, operationally calm, and data-dense without becoming a generic dashboard.

### Design thesis

> **The map is the primary analytical surface. Panels are contextual instruments, not permanent storage for every feature.**

The operator should always know:

1. What event or time window is currently in focus.
2. Which map layers and model outputs are visible.
3. What has changed or requires attention.
4. Which values are observed, modeled, or user-entered.
5. How to return to the previous analytical state.

## 2. Current-State Audit

### Strengths to preserve

- Leaflet map remains full-viewport and is the correct primary spatial surface.
- Existing theme tokens support light and dark modes.
- MMI hazard colors and PAGER alert colors are domain-significant and must remain recognizable.
- The portal already has clear workflows for event input, catalog, map events, aftershock analysis, analytics, and configuration.
- The catalog supports filtering, source tabs, time range, export, comparison, and impact drill-down.
- The dashboard has analytics KPIs, frequency-magnitude distribution, depth/rate views, hotspot map, and tectonic-zone drill-down.
- Existing status, toast, spinner, skeleton, confirmation, and reduced-motion patterns provide a useful base.

### Friction to solve

- The fixed icon rail hides the meaning of the application behind icons and tooltips.
- The 268px panel is too narrow for dense filters, impact tables, and operator context.
- Event calculation and event catalog are separate sections even when the user is investigating the same event.
- Historical earthquakes are configured inside the event input workflow, although they are a map-analysis layer.
- Aftershock probability is a separate destination instead of a natural event-inspection mode.
- Analytics replaces the map with a separate full view, which breaks spatial continuity.
- Map configuration mixes overlays, basemaps, MMI opacity, and epicenter styling without clear grouping.
- Several controls depend on inline styles and generated HTML, making visual consistency difficult.
- The interface exposes technical actions such as “Pull PMD feed” beside user-facing analysis actions without a strong operational distinction.
- The current visual hierarchy gives similar weight to calculation, ingestion, navigation, and configuration.
- Mobile behavior is mostly incidental; the desktop shell is not an intentional small-screen experience.
- Loading, empty, stale, low-sample, and failed-data states are not consistently framed as analytical states.

## 3. Product Goals

### Primary goals

- Make the current event and current analysis state visible at all times.
- Reduce navigation friction between map, catalog, impact, and aftershock workflows.
- Make the map readable at a glance without hiding important controls.
- Give analysts a larger, more legible inspection surface for event details and impact.
- Make the distinction between model output and observed/source data explicit.
- Establish a visual system that can support future ML confidence, uncertainty, provenance, and GenAI explanations.
- Make desktop, tablet, and mobile behavior intentional.
- Preserve keyboard access, focus visibility, reduced motion, and WCAG AA contrast.

### Secondary goals

- Improve discoverability for first-time operators.
- Make the system feel credible during high-attention events without using alarmist decoration.
- Support screenshots and exported reports that retain event context and provenance.
- Reduce duplicated visual patterns and inline-style markup.

### Non-goals for the first redesign

- No automatic earthquake prediction claims.
- No change to the scientific MMI calculation solely for visual reasons.
- No replacement of Leaflet, Chart.js, or the current tile stack without a separate evaluation.
- No new authentication model in the visual redesign; security work remains a separate platform concern.
- No GenAI assistant implementation in the first visual slice, but the layout must reserve a trustworthy place for future analyst assistance.

## 4. Proposed Visual Language

### Concept: “Seismic Observatory”

The visual direction should feel like a field instrument rather than a SaaS admin dashboard:

- Dark obsidian workspace by default.
- A quiet blue-gray structural palette for navigation and chrome.
- A narrow electric cyan signal accent for active controls and live state.
- Warm amber reserved for attention and operator actions.
- MMI and PAGER colors remain domain-locked and visually dominant only when the data requires them.
- Hairline geometry, restrained shadows, compact technical typography, and larger analytical numbers.
- Small coordinate/time labels use a readable mono face.
- Avoid excessive glassmorphism, giant gradients, rounded card grids, or decorative “AI” effects.

The map should feel like it sits beneath a transparent instrument overlay, not inside a dashboard card.

### Theme direction

Dark mode leads because the map, hazard ramp, and high-density event markers read better against a dark workspace. Light mode remains fully supported and is not treated as an afterthought.

Dark starting tokens:

```css
--canvas: #080C12;
--surface: #101721;
--surface-raised: #151F2C;
--surface-inset: #0C131D;
--line: #243140;
--line-strong: #34465A;
--ink: #EDF3F8;
--ink-muted: #93A4B5;
--signal: #55B8FF;
--signal-strong: #2C91E6;
--attention: #F0A45B;
--positive: #63C58A;
--danger: #F07171;
```

Light mode should invert the structural values without changing semantic meaning:

```css
--canvas: #F3F6F9;
--surface: #FFFFFF;
--surface-raised: #FFFFFF;
--surface-inset: #EAF0F5;
--line: #D7E0E8;
--line-strong: #B8C6D3;
--ink: #172431;
--ink-muted: #5D6D7C;
--signal: #146EB4;
--signal-strong: #0C578F;
--attention: #A45D19;
```

These are starting values, not final values. Contrast must be measured against actual text sizes and states.

### Typography

- Inter or a comparable neutral UI sans for labels and controls.
- IBM Plex Mono for coordinates, timestamps, magnitudes, depths, counts, and model values.
- Display headings should be restrained, not oversized.
- Numeric values use tabular figures.
- Uppercase labels are reserved for compact metadata, not every heading.
- Use weight and spacing for hierarchy before adding color.

### Shape and elevation

- Small controls: 4px radius.
- Instrument panels: 8px radius.
- Major drawers: 12px radius.
- Structural separation comes from line and tone; shadows are reserved for floating drawers, menus, and dialogs.
- Hazard polygons and event markers must not be visually weakened by decorative surfaces.

## 5. Information Architecture

Replace the current icon-only rail with a clear **workspace navigation strip**. The map remains visible for map-centric modes and is covered or replaced only when the task truly requires a full analytical view.

### Primary workspaces

1. **Overview**
   - Current seismic activity.
   - Latest significant events.
   - Source freshness.
   - High-level impact and model caveats.
   - Map remains central.

2. **Event Analysis**
   - Select a catalog event or enter a Manual Event Input.
   - Calculate MMI intensity.
   - Show epicenter, intensity bands, observations, historical context, and impact.
   - Event context remains pinned while switching analysis tabs.

3. **Catalog**
   - Search, filter, compare, export, and inspect events.
   - Selecting an event opens the Event Analysis inspector rather than losing the map.

4. **Aftershock Probability**
   - Event selector and Manual Event Input as alternate sources.
   - Probability table and chart.
   - Region, model parameters, completeness caveats, and uncertainty shown together.

5. **Seismicity Analytics**
   - Time window, minimum magnitude, zone/cell focus, KPIs, FMD, depth, rate, hotspots, and zone table.
   - Analytics should open as a workspace with an optional map split, not only as a map replacement.

6. **Layers and Display**
   - Basemap.
   - Administrative overlays.
   - Faults, plates, and tectonic zones.
   - MMI opacity.
   - Epicenter marker color and size.
   - Historical earthquake visibility and date range.

### Secondary surfaces

- **Event inspector drawer:** selected event details, source provenance, model results, impact, aftershock, and actions.
- **Global command/search:** jump to event, place, workspace, or action.
- **Status strip:** source freshness, active model, current time window, and warnings.
- **Notification center:** ingest failures, stale source, low sample size, failed analysis, and completed exports.

## 6. Proposed Layout

### Desktop layout

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ brand / workspace      current event context       freshness / theme / user │
├───────┬──────────────────────────────────────────────────────────────┬─────┤
│       │                                                              │     │
│ nav   │                         MAP WORKSPACE                        │     │
│ strip │       intensity / historical events / overlays / legend      │     │
│       │                                                              │     │
│       ├──────────────────────────────────────────────────────────────┤     │
│       │ timeline / selected event summary / active analysis status   │     │
└───────┴──────────────────────────────────────────────────────────────┴─────┘
                                      └── contextual inspector drawer ──┘
```

The inspector drawer is closed by default on the Overview workspace and opens when an event is selected. It can be pinned for comparison or impact work.

### Map composition

- Map fills the available workspace.
- Top-left: workspace label and optional breadcrumb.
- Top-right: compact map tools, search, location, and fullscreen.
- Bottom-left: map scale, coordinate readout, and data timestamp.
- Bottom-right: MMI legend or active event/historical legend.
- Right drawer: event or layer context, never an opaque permanent panel.
- A map-only focus mode hides nonessential chrome.

### Desktop inspector widths

- Compact: 320px.
- Standard: 400px.
- Wide analysis: 520px.
- The drawer width must be adjustable only if resizing can be implemented accessibly; otherwise use three explicit sizes.

### Tablet layout

- Navigation becomes a top or bottom workspace bar.
- Inspector opens as a large sheet covering 45-70% of the viewport.
- Map remains visible behind the sheet.
- Dense tables become horizontally scrollable or switch to stacked rows.

### Mobile layout

- Map remains the home surface.
- Primary navigation is a bottom bar with 4-5 high-value destinations: Overview, Analyze, Catalog, Aftershock, More.
- Inspector becomes a full-height bottom sheet with a visible drag/close affordance.
- Event input is a stepper or stacked form, not a two-column grid.
- Map controls are grouped into one floating tool button.
- Analytics charts stack vertically.
- Comparison mode becomes a swipeable or stacked event summary, never a squeezed two-column table.

## 7. Core User Flows

### Flow A: Analyze a Manual Event Input

1. Operator chooses **Analyze**.
2. Event Analysis opens with Magnitude, Depth, Latitude, and Longitude as the primary form.
3. Optional advanced fields are collapsed: source type, mechanism, strike, rupture dimensions, observations.
4. “Calculate intensity” is the single dominant action.
5. On success, the map centers on the epicenter and displays MMI bands.
6. The inspector switches to an event summary with:
   - Event parameters
   - Model mode
   - Uncertainty label
   - Number of intensity bands
   - Active observations
7. Secondary tabs expose Impact, Historical Context, and Aftershock Probability.

### Flow B: Investigate a catalog event

1. Operator searches or filters the Catalog.
2. Selecting a row opens the Event Analysis inspector and highlights the event on the map.
3. The selected event context is pinned in the header.
4. Impact rollups are shown in a tabbed inspector with Province, District, and Tehsil levels.
5. Source details and provenance remain available without navigating away.
6. “Compare” adds a second event to the inspector and uses explicit Event 1/Event 2 colors.

### Flow C: Historical earthquake context

1. Operator activates Historical Events from Layers or Event Analysis.
2. A date range, source selection, minimum magnitude, and result limit appear together.
3. The map legend explains marker size and color.
4. Selecting a historical event opens the same inspector used by the Catalog.
5. The current MMI polygon remains visible unless the operator explicitly hides it.

### Flow D: Aftershock Probability

1. Operator opens Aftershock from an event inspector or workspace navigation.
2. The current event is preselected when available.
3. Manual entry remains available as an explicit alternate mode.
4. The result shows probability, expected rate, forecast window, target magnitude, completeness, and caveats in one visual hierarchy.
5. Export is secondary to interpretation, not the primary visual action.

### Flow E: Seismicity Analytics

1. Operator selects a time window and minimum magnitude.
2. The platform shows the query context in a persistent provenance strip.
3. KPIs, FMD, depth, and rates appear beside or below a spatial hotspot map.
4. Clicking a hotspot or zone updates the focus state without losing the filter context.
5. “Reset focus” is always visible when a spatial drill-down is active.

### Flow F: Source and model health

1. Header status shows PMD and USGS freshness independently.
2. Stale or failed sources are visible but do not block manual analysis.
3. Model output displays source data timestamp, model mode, and uncertainty label.
4. Warnings are concise and actionable: “PMD last updated 42 min ago” rather than generic red error decoration.

## 8. Component Inventory

### Shell

- `AppShell`
- `WorkspaceNav`
- `WorkspaceHeader`
- `StatusStrip`
- `InspectorDrawer`
- `CommandSearch`

### Map

- `MapViewport`
- `MapToolbar`
- `MapLegend`
- `LayerDrawer`
- `HistoricalEventControls`
- `EpicenterMarkerControl`
- `MapTimestamp`

### Event analysis

- `EventInputForm`
- `EventSummary`
- `ModelQualityBadge`
- `ObservationSummary`
- `ImpactTabs`
- `EventComparison`
- `EventActionMenu`

### Catalog

- `CatalogToolbar`
- `CatalogFilterBar`
- `SourceTabs`
- `EventTable` or `EventList`
- `EventRow`
- `ExportMenu`
- `SelectionBar`

### Analytics

- `AnalyticsFilterBar`
- `KpiStrip`
- `FrequencyMagnitudeChart`
- `DepthScatter`
- `RateChart`
- `HotspotMap`
- `ZoneTable`
- `ProvenanceStrip`

### Feedback and trust

- `LoadingState`
- `EmptyState`
- `ErrorState`
- `StaleDataBadge`
- `UncertaintyNotice`
- `ToastStack`
- `ConfirmDialog`

These names are planning vocabulary. They do not require a framework or a component library. The implementation may remain vanilla JavaScript, but each visual responsibility should have a clear owner and class/state contract.

## 9. Data and Trust Presentation

The redesign must make model trust visible without overwhelming the operator.

### Every analyzed event should expose

- Event source: PMD, USGS, Manual Event Input, or combined.
- Occurrence time and data retrieval time.
- Magnitude, magnitude type, depth, latitude, and longitude.
- Model mode: model-only, observation-assisted, or finite-fault approximation.
- Uncertainty label and any uncertainty caveat.
- Observation count and provenance.
- Number of intensity bands.
- Whether the result is historical, current, or hypothetical.

### Visual language for trust

- Blue/cyan: active selection and structural state.
- Amber: caveat, stale data, incomplete observations, or operator attention.
- Red: destructive action or actual severe alert state only.
- Gray: unavailable or not applicable.
- Never use a green “success” state to imply that a hazard is safe.

### Provenance placement

Provenance should not be buried at the bottom of a long panel. Use a compact, expandable strip near the event title:

```text
PMD + USGS | observed 12:43 UTC | calculated 12:44 UTC | model-only | uncertainty elevated
```

## 10. Interaction Rules

- One dominant action per workspace or inspector state.
- Destructive actions require confirmation and are never adjacent to primary analysis actions without separation.
- Loading states keep the surrounding context visible.
- A failed request does not clear the last valid map or report unless the user explicitly resets it.
- Empty states explain what action would produce data.
- Disabled controls explain why through nearby text or accessible descriptions.
- Changing a filter resets pagination and announces the result count.
- Opening an inspector does not unexpectedly change the active workspace.
- Closing an inspector preserves the selected event and can reopen it from the map marker.
- Escape closes the topmost drawer, dialog, or command surface.
- Browser back/forward behavior should be evaluated for workspace, selected event, filters, and drill-down state.

## 11. Accessibility Plan

### Keyboard

- Workspace navigation is a named navigation landmark.
- Active workspace is exposed with `aria-current="page"` or an equivalent state.
- Inspector drawer has a heading, close button, and focus management.
- Map tools have visible labels or tooltips and keyboard access.
- Charts include text summaries or accessible data tables.
- Color is never the only channel for depth, source, alert, or selected state.
- All custom controls expose native keyboard semantics where possible.

### Visual

- WCAG AA contrast in both themes.
- Focus rings remain visible against map and surface backgrounds.
- Minimum practical hit area of 40px for touch controls.
- No critical information conveyed only through tiny map markers.
- Text remains readable at 200% zoom without losing access to primary actions.

### Motion

- Keep transitions short and purposeful.
- Respect `prefers-reduced-motion`.
- Do not animate map markers continuously.
- Avoid drawer animations that obscure context or trap focus.

## 12. Responsive Acceptance Matrix

| Surface | Desktop | Tablet | Mobile |
|---|---|---|---|
| Map | Full workspace with inspector drawer | Full workspace with sheet | Full viewport with bottom sheet |
| Navigation | Left workspace strip | Top/bottom bar | Bottom navigation |
| Event form | Two-column essentials | Two-column where space allows | Single-column stepper |
| Catalog | Filter bar + list/table | List with collapsible filters | Filter sheet + stacked rows |
| Impact | Inspector tabs | Sheet tabs | Stacked sections |
| Analytics | Split map/charts | Vertical sections | Single-column scroll |
| Layers | Right drawer | Sheet | Full-screen sheet |
| Comparison | Two event columns | Stacked event headers | Swipe/stacked summaries |

## 13. Implementation Phases

### Phase 0: Product decisions and visual prototype

- [ ] Confirm whether this plan supersedes the approved “same layout / IA” reskin.
- [ ] Choose final visual direction from two low-fidelity alternatives.
- [ ] Define the primary operator persona and top three workflows.
- [ ] Produce desktop and mobile shell prototypes.
- [ ] Validate navigation labels with a domain operator.
- [ ] Create a screenshot baseline of the current portal.

**Exit criteria:** One selected shell, one selected visual language, and validated primary flows before production markup changes.

### Phase 1: Foundation and shell

- [ ] Replace the current rail/panel shell with the new workspace shell.
- [ ] Introduce tokenized surfaces, type, spacing, line, elevation, and semantic colors.
- [ ] Add desktop, tablet, and mobile layout states.
- [ ] Add persistent workspace header and status strip.
- [ ] Establish a consistent drawer/sheet primitive.
- [ ] Move inline styles into named classes.
- [ ] Preserve existing element IDs temporarily where handlers still depend on them.

**Exit criteria:** All existing sections can render inside the new shell, even before their content is fully redesigned.

### Phase 2: Map workspace

- [ ] Build the map toolbar and map-only focus mode.
- [ ] Move layer, basemap, MMI opacity, epicenter style, and historical controls into a layer drawer.
- [ ] Improve legend placement, collapsibility, and mobile behavior.
- [ ] Add visible map timestamp and source/model status.
- [ ] Ensure historical earthquake marker legend explains color and size.

**Exit criteria:** Map analysis is usable without opening the old configuration panel and remains legible at desktop, tablet, and mobile widths.

### Phase 3: Event Analysis and inspector

- [ ] Merge Manual Event Input and selected catalog event into one Event Analysis workspace.
- [ ] Add event context header and inspector drawer.
- [ ] Separate essential inputs from advanced source/rupture/observation inputs.
- [ ] Add model quality, uncertainty, provenance, and observation summaries.
- [ ] Move impact rollups into inspector tabs.
- [ ] Add direct transition from selected event to Aftershock Probability.
- [ ] Keep Save to catalog and destructive actions visually separated.

**Exit criteria:** An operator can calculate, inspect, compare, and assess one event without losing map context.

### Phase 4: Catalog redesign

- [ ] Redesign catalog toolbar and filter hierarchy.
- [ ] Use a readable event list/table with magnitude, source, time, place, depth, and confidence/alert metadata.
- [ ] Add sticky selection/comparison bar.
- [ ] Make filters responsive through a filter sheet on mobile.
- [ ] Preserve export and pagination behavior.
- [ ] Add clear empty, loading, stale, and failed states.

**Exit criteria:** An operator can find a historical event in under three interactions from the Catalog workspace and open it in Event Analysis.

### Phase 5: Aftershock and analytics workspaces

- [ ] Reframe Aftershock Probability around selected event context.
- [ ] Show forecast caveats and completeness next to probabilities.
- [ ] Redesign Analytics as a spatially anchored workspace.
- [ ] Keep hotspot map and drill-down context visible while inspecting charts.
- [ ] Add a persistent provenance strip to analytics.
- [ ] Provide accessible text summaries for charts.

**Exit criteria:** Analytics and Aftershock workflows no longer feel detached from the event/map context.

### Phase 6: Interaction, accessibility, and polish

- [ ] Keyboard and focus audit.
- [ ] Screen-reader landmark and naming audit.
- [ ] Contrast audit for both themes.
- [ ] Touch target and mobile gesture audit.
- [ ] Reduced-motion audit.
- [ ] Loading/error/empty state audit.
- [ ] Performance audit for map layers, charts, and inspector transitions.
- [ ] Remove obsolete CSS and markup after migration.

**Exit criteria:** No critical accessibility, responsive, or interaction regressions remain.

## 14. Technical Plan

### Files likely to change

```text
web/index.html       shell, landmarks, drawers, workspace containers
web/styles.css       tokens, layout, components, responsive states
web/app.js           workspace state, routing, rendering ownership, event wiring
web/catalog-state.js catalog state/query seam already extracted
```

Potential future files if the vanilla implementation needs stronger locality:

```text
web/ui/
  shell.js
  map-workspace.js
  event-inspector.js
  catalog-view.js
  analytics-view.js
  aftershock-view.js
  layer-drawer.js
  feedback.js
```

Do not split these files before the new state and rendering responsibilities are clear. The first implementation should avoid creating thin files that only forward calls.

### State model

Create one explicit UI state model with fields similar to:

```text
workspace: overview | event | catalog | aftershock | analytics | layers
selectedEventId: number | null
comparisonIds: number[]
inspector: closed | compact | standard | wide
mapMode: intensity | historical | combined | neutral
analyticsFocus: zone | bbox | none
theme: dark | light
```

State transitions should be pure where possible. Leaflet, Chart.js, fetch, and DOM mutation remain rendering/adaptation concerns.

### URL/state persistence

Evaluate encoding these values in the URL:

- Workspace
- Selected event
- Catalog filters
- Analytics time window and focus
- Map mode

The first implementation may use in-memory state, but the decision must be explicit. Deep-linking an event analysis view is high value for operational collaboration.

### Backend compatibility

The redesign should consume existing contracts first:

- `POST /intensity`
- `GET /events`
- `GET /events/{id}`
- `POST /events/{id}/impact`
- `POST /events/{id}/refresh-from-usgs`
- `POST /events/ingest`
- `POST /events/ingest/pmd`
- `GET /analytics`
- `GET /zones`

Any missing presentation data should first be derived from existing responses. New endpoints should be proposed only when the UI cannot provide a coherent experience without them.

## 15. Performance Plan

- Avoid destroying and recreating the entire map when only the inspector changes.
- Avoid redrawing every chart when one filter changes.
- Cancel or ignore stale analytics requests when the user changes filters rapidly.
- Keep historical map markers bounded by the existing limit and visibly report the limit.
- Lazy-render charts and heavy tables when their workspace or tab becomes visible.
- Use skeletons that match the final layout to reduce perceived latency.
- Preserve the map viewport when drawers open and close.
- Measure first paint, map-ready time, event-selection latency, and analytics response-to-render time.

## 16. Quality and Verification Checklist

### Functional flows

- [ ] Calculate intensity from Manual Event Input.
- [ ] Save and display a catalog event.
- [ ] Pull PMD and USGS feeds.
- [ ] Search and filter the catalog.
- [ ] Open event impact and switch administrative levels.
- [ ] Compare two events.
- [ ] Show historical earthquakes with date range.
- [ ] Use coolwarm depth and magnitude-size marker encoding.
- [ ] Run Aftershock Probability from catalog and manual input.
- [ ] Run Analytics filters, hotspot drill-down, and zone drill-down.
- [ ] Change basemap and overlays.
- [ ] Change MMI opacity and epicenter appearance.
- [ ] Export CSV, GeoJSON, and MMI shapefile.

### Visual states

- [ ] First load.
- [ ] Loading.
- [ ] Empty catalog.
- [ ] Empty analytics result.
- [ ] Stale source.
- [ ] Feed failure.
- [ ] Calculation failure.
- [ ] No intensity bands.
- [ ] Low sample size.
- [ ] Missing zone data.
- [ ] Offline or slow network.
- [ ] Long place names and large event counts.

### Responsive

- [ ] 1440px desktop.
- [ ] 1024px laptop/tablet landscape.
- [ ] 768px tablet.
- [ ] 390px mobile.
- [ ] 320px narrow mobile.
- [ ] Browser zoom at 200%.

### Accessibility

- [ ] Keyboard-only navigation.
- [ ] Focus management for drawers and dialogs.
- [ ] Escape behavior.
- [ ] Screen-reader labels and landmarks.
- [ ] Chart summaries and table alternatives.
- [ ] Contrast in dark and light modes.
- [ ] Reduced-motion mode.
- [ ] Color-independent hazard/source/depth cues.

### Browser verification

- [ ] Chrome desktop.
- [ ] Firefox desktop.
- [ ] Safari or WebKit equivalent.
- [ ] Android viewport.
- [ ] iOS viewport.
- [ ] No uncaught console errors.
- [ ] No layout shift that hides map or inspector content.

## 17. Success Metrics

Measure before and after the redesign where possible:

- Time from load to first successful intensity calculation.
- Time from Catalog open to selected Event Analysis.
- Number of navigation actions to inspect impact.
- Number of mis-clicks or backtracks during common workflows.
- Percentage of users who discover historical earthquake controls.
- Percentage of users who can explain marker color and size encoding.
- Task completion rate on desktop and mobile.
- Accessibility issue count.
- Perceived clarity of model/source/provenance state in operator interviews.

Suggested usability tasks:

1. Calculate an M6.5 event near the Primary Focus Country.
2. Show historical PMD earthquakes between two dates.
3. Find the largest USGS event in the Catalog and inspect District impact.
4. Compare two catalog events.
5. Determine whether the current PMD feed is stale.
6. Run an Aftershock Probability forecast and identify its completeness caveat.

## 18. Risks and Mitigations

### Risk: Visual redesign changes operator muscle memory

Mitigation:

- Preserve familiar labels and domain terms.
- Use a transition mode or user walkthrough.
- Ship workspace by workspace rather than replacing everything in one untestable change.

### Risk: New shell hides existing capabilities

Mitigation:

- Maintain a capability inventory.
- Add a command/search surface and “More” overflow.
- Test every current flow before deprecating the old navigation.

### Risk: Map loses dominance under drawers and sheets

Mitigation:

- Keep map state alive while inspectors open.
- Add map-only focus mode.
- Define explicit drawer width and viewport behavior.

### Risk: Hazard colors become decorative

Mitigation:

- Keep MMI/PAGER palettes domain-locked.
- Reserve brand accent for navigation and interaction.
- Document all semantic color uses.

### Risk: UI state becomes harder to reason about

Mitigation:

- Use explicit state rather than DOM-attached state.
- Keep state transitions pure.
- Test workspace transitions and query construction without Leaflet or Chart.js.

### Risk: New frontend dependencies increase deployment friction

Mitigation:

- Continue with vanilla HTML/CSS/JavaScript unless a dependency earns its cost.
- Do not introduce a framework solely for visual components.
- Keep third-party scripts pinned with SRI where supported.

## 19. Decisions Needed Before Implementation

- [ ] Approve structural redesign over the existing same-IA reskin.
- [ ] Select the “Seismic Observatory” visual direction or request alternatives.
- [ ] Decide whether the map remains visible behind Analytics.
- [ ] Decide whether the inspector drawer is resizable.
- [ ] Decide whether UI state is URL-persisted.
- [ ] Decide whether Overview is a new workspace or a redesigned Dashboard.
- [ ] Decide whether source freshness is always visible in the header.
- [ ] Decide whether the current default dark theme remains the lead theme.
- [ ] Decide whether a small-screen layout is required for the first release.
- [ ] Identify one or two domain operators for usability review.

## 20. Recommended Delivery Order

1. Approve the visual direction and shell prototype.
2. Build the new shell with placeholder surfaces and no behavior changes.
3. Migrate Event Analysis and map context first because they represent the core product value.
4. Migrate Catalog and the Event Analysis inspector.
5. Migrate Layers and Historical Events controls.
6. Reframe Aftershock Probability around selected event context.
7. Reframe Analytics as a spatial workspace.
8. Complete responsive, accessibility, performance, and visual QA.
9. Remove obsolete rail/panel markup and CSS only after all acceptance flows pass.

The redesign is complete when the portal communicates a coherent operational story: **what happened, where it happened, how certain the model is, who may be affected, and what the operator can investigate next.**
