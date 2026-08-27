# Historical earthquake catalog coverage

Research checked on 2026-08-19. This note uses first-party USGS and Pakistan
Meteorological Department (PMD) pages and endpoints. Endpoint observations are
time-sensitive and are identified as such.

## Repository scope

The application requests earthquakes in the WGS84 bounding box
`44.0 to 105.0 E, 8.0 to 56.0 N`, described in `src/eqmon/config.py` as Iran through
China/Nepal and covering Pakistan, India, Afghanistan, Iran, China, and Nepal.
`USGSSource` uses the USGS FDSN event query with `eventtype=earthquake`,
`orderby=time`, and `limit=20000`. With no caller-supplied start, it requests the
last 30 days in one-day windows; its error fallback is the USGS all-day feed.
`PMDSource` points to `https://weather.gov.pk/api/seismic-events` and can send a
bearer token. These are implementation choices, not source-completeness
guarantees.

The repository already makes the correct distinction in
`events.repo.catalog_coverage`: the minimum and maximum stored event times
describe what has been ingested, not completeness within that interval. The
search API reports `completeness: not_asserted`.

## 1. USGS FDSN event API

### Limits and time support

- The official [FDSN event API documentation](https://earthquake.usgs.gov/fdsnws/event/1/)
  defines `limit` as an integer from 1 through 20,000. A query that would exceed
  20,000 results produces `400 Bad Request`. The companion `count` method accepts
  the same filters and can be used to size a query before retrieval.
- The documentation gives `starttime` a default of `NOW - 30 days` and
  `endtime` a default of the present. These are defaults, not a statement that
  only 30 days are searchable. Times are ISO 8601; UTC is assumed when no zone is
  supplied.
- USGS does **not** document one universal earliest supported/catalog-complete
  date for an unqualified ComCat query. ComCat combines catalogs with different
  time ranges. Its official [data-availability table](https://earthquake.usgs.gov/data/comcat/#avail)
  includes, for example, ISC-GEM from 1900 and an `OFFICIAL` historical catalog
  from 1638, while other contributing catalogs begin much later. The table is
  itself labeled as of 2020-10-20 and should not be treated as a live coverage
  guarantee.
- As an endpoint observation relevant to this repository, an explicit
  [`orderby=time-asc&limit=1` query over the repository bbox](https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&starttime=0001-01-01&endtime=2026-08-19&minlongitude=44&maxlongitude=105&minlatitude=8&maxlatitude=56&eventtype=earthquake&orderby=time-asc&limit=1)
  returned a reviewed M7.7 event dated 1902-08-22 near Kashgar. This establishes
  that historical data are queryable and that 1902 was the earliest matching
  row returned on the check date. It does **not** establish completeness from
  1902, an API lower bound, or uniform magnitude coverage.

### Ordering and pagination

The [official parameter definitions](https://earthquake.usgs.gov/fdsnws/event/1/#parameters)
specify:

- `offset` is one-based, defaults to 1, and returns results starting at that
  event count.
- `orderby=time` is origin time descending and is the default.
- `orderby=time-asc` is origin time ascending.
- `orderby=magnitude` and `orderby=magnitude-asc` sort by magnitude descending
  and ascending, respectively.

Thus a page after the first begins at `offset=limit+1`, not `offset=limit`.
The documentation does not promise a snapshot across requests or document a
tie-break key for equal time/magnitude values. For defensible historical
retrieval, use explicit bounded time windows, call `count` first, subdivide any
window approaching 20,000, and deduplicate by event ID. Offset pagination over
a catalog that can be updated should not be described as snapshot-stable.

The documentation does not state a numeric request-per-second quota. It does
recommend the [real-time GeoJSON feeds](https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php)
for automated applications displaying current earthquakes because those feeds
have better performance and availability. Absence of a published rate number
is not permission to issue unbounded parallel requests.

### Official completeness caveats

"Comprehensive" in the ComCat name is not a claim that every earthquake above a
single magnitude has been detected for all places and all dates:

- The official [ComCat documentation](https://earthquake.usgs.gov/data/comcat/)
  says it contains parameters and products produced by contributing seismic
  networks, and its availability table shows source-dependent temporal ranges.
- If `catalog` and `contributor` are omitted, the API returns the most preferred
  information from any catalog/contributor for an event. A result is therefore
  a merged preferred view, not one homogeneous observing network.
- Event `status` can be `automatic` or `reviewed`; USGS explains that automatic
  events have not been human verified, while the degree of review varies. The
  preferred event ID and preferred magnitude may change as information is
  updated.
- The official [NEIC/PDE catalog page](https://earthquake.usgs.gov/data/comcat/catalog/us/)
  documents changing formats and review stages, says events could be added,
  modified, or removed during finalization, and notes that the final PDE is not
  machine-readable before February 1981. Historical data availability and
  quality are therefore not uniform through time.

No reviewed USGS page found supplies a single magnitude-of-completeness value
or complete-since date for this repository's large bbox. Analyses requiring
statistical completeness must estimate and report it for the selected region,
period, and magnitude range rather than infer it from API availability.

## 2. PMD public availability

### Machine-readable catalog/API

No documented, unauthenticated PMD historical JSON/CSV catalog API was found on
the official site.

- The repository's endpoint,
  [`https://weather.gov.pk/api/seismic-events`](https://weather.gov.pk/api/seismic-events),
  returned `302 Found` with `Location: https://weather.gov.pk/login` when
  requested without credentials on 2026-08-19. Following the redirect produces
  the PMD login page, not earthquake data. It is therefore not a public
  unauthenticated machine-readable endpoint on the evidence checked.
- PMD's public [Recent Earthquakes page](https://weather.gov.pk/seismic/events)
  renders an HTML table and initializes the browser-side DataTables export
  controls (including CSV). This is publicly readable and mechanically
  extractable HTML, but it is not a documented data API or stable JSON/CSV
  contract.

The authenticated endpoint may be operationally available to this application
when `PMD_API_TOKEN` is supplied. That private access must not be described as a
public PMD API.

### Temporal range supported by official pages

- PMD publicly links a [monthly bulletin archive labeled 2008-2019](https://weather.gov.pk/seismic/bulletins/2008/2019)
  and another [labeled 2020-2026](https://weather.gov.pk/seismic/bulletins/2020/2026).
  The current seismic navigation separately groups the archive as 2015-2020 and
  2021-2026. These labels show navigable years, not that each month contains
  observations.
- The checked [January 2008 summary](https://weather.gov.pk/seismic/bulletin-summary/January/2008)
  and [December 2014 summary](https://weather.gov.pk/seismic/bulletin-summary/December/2014)
  contained column headings but no event rows. By contrast, the
  [January 2015 summary](https://weather.gov.pk/seismic/bulletin-summary/January/2015)
  contains rows beginning 2015-01-03.
- On 2026-08-19, parsing plausible years in the public Recent Earthquakes HTML
  found an observed event-date extent of 2015-01-03 through 2026-08-18. The page
  includes visibly malformed/inconsistent rows, so this is an observed display
  extent, not an asserted official completeness interval.

The defensible conclusion is: PMD exposes public human-facing HTML event and
monthly bulletin pages, with populated historical observations demonstrably
available from January 2015 through the present check date. PMD also exposes
archive navigation back to 2008, but checked pre-2015 summaries were empty. No
public historical machine-readable API and no official completeness threshold
or complete-since date were established.

## 3. Recommended coverage wording

Use wording based on observed and ingested coverage, not "complete catalog":

> This catalog contains earthquake observations ingested from USGS ComCat and,
> when authorized and available, PMD for the coverage region 44-105 E and 8-56
> N. Displayed earliest/latest dates are the extent of records currently stored,
> not a guarantee that all earthquakes in that interval were detected or
> ingested. Source availability, network sensitivity, magnitude thresholds,
> review status, historical reporting, parsing, synchronization, and
> deduplication vary by source and over time. Catalog completeness is not
> asserted; analyses that depend on completeness must estimate it for their
> selected region, period, and magnitude range.

Short UI/API form:

> Observed source coverage; completeness not asserted. Date extent reflects
> records currently ingested, not all earthquakes that occurred.

Source-specific form:

> USGS records are retrieved from the evolving ComCat preferred-event view.
> PMD records are included only for periods successfully retrieved through
> authorized access. Neither source's presence establishes uniform historical
> or magnitude completeness.
