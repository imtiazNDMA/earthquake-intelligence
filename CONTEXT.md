# Seismic Intelligence Platform

This context defines the shared language for a seismic intelligence platform focused on earthquake impact analysis and mapping for Pakistan and nearby countries.

## Language

**Coverage Region**:
The fixed geographic scope for version 1 earthquake monitoring and visualization. It includes Pakistan, India, Afghanistan, Iran, China, and Nepal.
_Avoid_: Nearby countries, regional area, South Asia coverage

**Primary Focus Country**:
The country used as the default operational focus in the user interface and map viewport. For version 1, this is Pakistan.
_Avoid_: Main region, default territory

**Primary Seismic Source**:
The preferred authoritative provider of earthquake event data for this platform. For version 1, this is the Pakistan MET Department feed.
_Avoid_: Main API, default feed

**Secondary Seismic Source**:
The fallback provider used when the primary source is unavailable or missing an event. For version 1, this is the USGS feed.
_Avoid_: Backup API, alternate stream

**Manual Event Input**:
An operator-entered earthquake event containing core parameters used for impact calculations when feed integration is not yet active.
_Avoid_: Ad hoc event, temporary record

**Coverage Enforcement**:
The rule set that keeps operations within the Coverage Region without requiring geometric clipping of all rendered layers. For version 1, enforcement uses viewport defaults, event filtering, and boundary overlays.
_Avoid_: Hard clip policy, map cutoff

**Default Site Condition**:
The site parameter used when no Vs30 polygon value is available for a location during intensity calculation. For version 1, this uses a fixed Vs30 value of 760 m/s.
_Avoid_: Random fallback, unknown soil default

## Example dialogue

Dev: Does this event appear in the platform if it is in Iran?
Domain expert: Yes. Iran is inside the Coverage Region.

Dev: Why does the map open centered on Pakistan?
Domain expert: Pakistan is the Primary Focus Country, even though the Coverage Region includes six countries.
