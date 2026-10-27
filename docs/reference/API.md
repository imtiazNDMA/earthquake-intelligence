# API — how to send and receive

Start the server with `run_server.bat`. It listens on **all interfaces**, so:

| From | Base URL |
| --- | --- |
| this machine | `http://172.18.0.29:5001` |
| another machine on the network | `http://<server-ip>:5001` |

The server prints its own network address on startup — use the one shown under
`on network`. If other machines cannot connect, run `allow_firewall.bat` once
as administrator to open the port.

**Check the port it actually started on.** If something else already owns 5000,
`run_server.bat` steps to the next free port and says so:

```
[!] Port 5000 is already in use by another program.
    Using port 5001 instead.
```

The startup banner always shows the real URLs — trust that over the port in
these examples.

The examples below use `172.18.0.29`; swap in the server's IP when calling from
elsewhere. CORS is enabled, so browser pages on other hosts can call it
directly.

---

## POST `/api/analyze`

Send an MMI polygon layer, get back the elements underneath each band.

### Send

`Content-Type: application/json`

```json
{
  "source": "sample"
}
```

That is the whole minimum request. Smoothing settings live on the server
(`scripts/eqarc/config.py` → `DEFAULT_SMOOTHING`) and are not sent by the
client.

**Fields**

| Field | Required | Default | Meaning |
| --- | --- | --- | --- |
| `source` | no | `"sample"` | `"sample"`, `"path"` or `"geojson"` |
| `path` | only if `source` is `"path"` | — | server-side path to a `.shp` or `.geojson` |
| `geojson` | only if `source` is `"geojson"` | — | inline GeoJSON FeatureCollection |
| `layers` | no | all 7 | which element layers to count |
| `include_geometry` | no | `true` | return the dissolved band geometry |

`layers` accepts any of: `population`, `settlements`, `hospitals`, `schools`,
`roads`, `bridges`, `airports`.

**The three ways to send the polygon**

```json
{ "source": "sample" }
```

```json
{ "source": "path", "path": "D:/abdul_sattar/eq_arc/data/sample_mmi/mmi_bands.shp" }
```

> `path` is restricted to the project directory, because the server is
> reachable over the network. To read MMI layers from elsewhere, add the folder
> to `ALLOWED_PATH_ROOTS` in `scripts/eqarc/config.py`, or use the upload
> endpoint below.

```json
{ "source": "geojson", "geojson": { "type": "FeatureCollection", "features": [] } }
```

When using `source: "geojson"`, each feature needs an `mmi_high` property —
that is the attribute the bands are dissolved on.

### Receive

```jsonc
{
  "ok": true,

  "bands": [
    {
      "mmi_low": 9,
      "mmi_high": 10,
      "color": "#ff0000",
      "area_km2": 52.0,
      "elements": {
        "population":  { "total": 35999.0, "male": 18499.0, "female": 17499.0, "points": 41 },
        "settlements": { "count": 9 },
        "hospitals":   { "count": 0 },
        "schools":     { "count": 2 },
        "roads":       { "count": 2 },
        "bridges":     { "count": 0 },
        "airports":    { "count": 0 }
      }
    }
    // ... one entry per band, strongest shaking first
  ],

  "totals":     { /* same "elements" shape, summed over all bands */ },
  "cumulative": [ { "mmi_min": 10, "area_km2": 52.0, "elements": { } } ],
  "geometry":   { "type": "FeatureCollection", "features": [] },

  "source":   { "type": "sample", "path": "..." },
  "dissolve": { "input_holes": 2942, "output_holes": 280 },
  "meta":     { "timings_s": { }, "crs": "EPSG:4326" }
}
```

**What to read**

- `bands[]` — one row per MMI band, **strongest first** (10 → 2).
- `totals` — the same shape, summed across every band.
- `cumulative[]` — running totals, i.e. everything at `MMI ≥ mmi_min`.
- `geometry` — the smoothed bands, ready to drop on a map. Set
  `include_geometry: false` if you do not need it; the response gets much smaller.

**Units**

- `population` → `total`, `male`, `female` are people. `points` is how many
  population grid cells were hit, not people.
- everything else → `count` is a number of features.
- `area_km2` → square kilometres.

**Counting rule.** Each element is counted **once**, in the highest MMI band it
falls in. So bands never double-count, and summing all bands gives `totals`.

---

## POST `/api/analyze/upload`

Same thing, but you upload the MMI layer instead of pointing at one.

### Send

`Content-Type: multipart/form-data`, form field **`files`**. Send either:

- a `.zip` containing the shapefile, or
- the loose `.shp` + `.shx` + `.dbf` + `.prj` together, or
- a single `.geojson`.

Optional form fields: `layers` (comma-separated or a JSON array),
`include_geometry`. Maximum 200 MB.

```bat
curl -X POST http://172.18.0.29:5001/api/analyze/upload ^
  -F "files=@mmi_bands.shp" -F "files=@mmi_bands.shx" ^
  -F "files=@mmi_bands.dbf" -F "files=@mmi_bands.prj" ^
  -F "layers=population,hospitals"
```

### Receive

Identical to `/api/analyze`.

> Uploading a `.shp` on its own fails — a shapefile is not one file. Send the
> `.shx` and `.dbf` with it, or zip the set.

---

## Errors

Any failure returns a non-2xx status and:

```json
{ "ok": false, "error": "Path does not exist: D:\\nope\\missing.shp" }
```

Always check `ok` before reading `bands`.

---

## Other endpoints

| Endpoint | Returns |
| --- | --- |
| `GET /api/health` | whether the server is ready and the caches are built |
| `GET /api/layers` | the 7 element layers and what each one measures |
| `GET /api/mmi/sample` | the raw, undissolved sample bands as GeoJSON |

---

## Examples

**JavaScript**

```js
const res  = await fetch("http://172.18.0.29:5001/api/analyze", {
  method:  "POST",
  headers: { "Content-Type": "application/json" },
  body:    JSON.stringify({ source: "sample", include_geometry: false })
});
const data = await res.json();
if (!data.ok) throw new Error(data.error);

console.log("people exposed:", data.totals.population.total);
for (const b of data.bands) {
  console.log(`MMI ${b.mmi_low}-${b.mmi_high}:`,
              b.elements.population.total, "people,",
              b.elements.hospitals.count, "hospitals");
}
```

**Python**

```python
import requests

r = requests.post("http://172.18.0.29:5001/api/analyze",
                  json={"source": "sample", "include_geometry": False})
data = r.json()
assert data["ok"], data.get("error")

print("people exposed:", data["totals"]["population"]["total"])
for b in data["bands"]:
    print(f"MMI {b['mmi_low']}-{b['mmi_high']}:",
          b["elements"]["population"]["total"], "people,",
          b["elements"]["hospitals"]["count"], "hospitals")
```

**curl**

```bat
curl -X POST http://172.18.0.29:5001/api/analyze ^
  -H "Content-Type: application/json" ^
  -d "{\"source\":\"sample\",\"include_geometry\":false}"
```
