/* One catalogue of basemaps and terrain, described once and handed to whichever
 * renderer needs it. Loads before app.js: the 2D map builds Leaflet layers from
 * these definitions and the 3D map builds MapLibre styles from the same rows, so
 * the two can never drift apart on URL, zoom ceiling, or credit.
 *
 * Every source here is keyless and openly licensed. Nothing may be added that
 * needs a token, an account, or a commercial licence.
 *
 * Three kinds of basemap:
 *   raster — a tile template. Leaflet reads it as written; MapLibre has no `{s}`
 *            or `{r}`, so hosts are expanded into one URL each and the retina
 *            suffix is resolved against this display.
 *   vector — a MapLibre style URL (OpenFreeMap). MapLibre loads it directly;
 *            Leaflet renders it through the maplibre-gl-leaflet plugin.
 *   hybrid — raster imagery plus the symbol layers of a vector style, so
 *            satellite views carry place names.
 */
(function () {
  "use strict";

  const OSM_ATTR = "© OpenStreetMap contributors";
  const OPENFREEMAP_ATTR = OSM_ATTR + ' © <a href="https://openfreemap.org/">OpenFreeMap</a>';
  const S2_ATTR =
    '<a href="https://s2maps.eu">Sentinel-2 cloudless 2020</a> by EOX IT Services (CC BY-NC-SA 4.0), ' +
    "modified Copernicus Sentinel data 2020";

  const RASTER = "raster";
  const VECTOR = "vector";
  // Raster imagery with the label layers of a vector style drawn over it.
  const HYBRID = "hybrid";

  const OPENFREEMAP_LABELS = "https://tiles.openfreemap.org/styles/bright";

  const BASEMAPS = [
    { name: "OpenStreetMap", kind: RASTER, template: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      subdomains: "abc", maxZoom: 19, attribution: OSM_ATTR },
    { name: "Humanitarian (HOT)", kind: RASTER, template: "https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png",
      subdomains: "abc", maxZoom: 19, attribution: OSM_ATTR + " © Humanitarian OpenStreetMap Team" },
    { name: "Topographic", kind: RASTER, template: "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
      subdomains: "abc", maxZoom: 17, attribution: OSM_ATTR + " © OpenTopoMap (CC-BY-SA)" },
    { name: "CyclOSM", kind: RASTER, template: "https://{s}.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png",
      subdomains: "abc", maxZoom: 20, attribution: OSM_ATTR + " © CyclOSM" },
    { name: "Transport (OPNVKarte)", kind: RASTER, template: "https://tileserver.memomaps.de/tilegen/{z}/{x}/{y}.png",
      subdomains: "", maxZoom: 18, attribution: OSM_ATTR + " © ÖPNVKarte" },
    // Copernicus Sentinel-2, cloud-free mosaic. The only openly licensed
    // satellite basemap with usable ground resolution; ~10 m native, so it is
    // capped where upscaling starts to mislead.
    { name: "Satellite (Sentinel-2)", kind: RASTER,
      template: "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2020_3857/default/g/{z}/{y}/{x}.jpg",
      subdomains: "", maxZoom: 15, attribution: S2_ATTR },
    { name: "Satellite + labels", kind: HYBRID,
      template: "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2020_3857/default/g/{z}/{y}/{x}.jpg",
      subdomains: "", maxZoom: 15, labelStyleUrl: OPENFREEMAP_LABELS,
      attribution: S2_ATTR + " · labels " + OPENFREEMAP_ATTR },
    { name: "Light (Positron)", kind: VECTOR, styleUrl: "https://tiles.openfreemap.org/styles/positron",
      maxZoom: 20, attribution: OPENFREEMAP_ATTR },
    { name: "Bright", kind: VECTOR, styleUrl: "https://tiles.openfreemap.org/styles/bright",
      maxZoom: 20, attribution: OPENFREEMAP_ATTR },
    { name: "Dark", kind: VECTOR, styleUrl: "https://tiles.openfreemap.org/styles/dark",
      maxZoom: 20, attribution: OPENFREEMAP_ATTR },
  ];

  // maplibre-gl-leaflet renders a vector style inside Leaflet. It reads the
  // maplibregl global when it loads, so it must be injected after the library.
  const VECTOR_PLUGIN = {
    id: "maplibre-gl-leaflet",
    src: "https://unpkg.com/@maplibre/maplibre-gl-leaflet@0.1.2/leaflet-maplibre-gl.js",
    integrity: "sha384-ZKxYl00xGmiHEkJHDvj3R0VrT/0hEGlK7NgYMhDPLUuVREQxpqWuKMCysEH1vgNM",
  };

  // DG-1: public Terrarium DEM for the first release. A locally hosted archive
  // is a later hardening task and would only replace `tiles` here.
  const TERRAIN = {
    tiles: ["https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"],
    encoding: "terrarium",
    tileSize: 256,
    maxzoom: 15,
    // Real relief at true scale. Exaggeration would misrepresent the ground a
    // hazard footprint is drawn on, which is the one thing 3D must not do.
    exaggeration: 1.0,
    attribution: 'Terrain: <a href="https://registry.opendata.aws/terrain-tiles/">Terrain Tiles</a> on AWS Open Data',
    // Beyond this the DEM is treated as unavailable and 3D stays pitched but flat.
    timeoutMs: 8000,
  };

  const THEME_BASEMAPS = { light: "OpenStreetMap", dark: "Dark" };

  const byName = new Map(BASEMAPS.map(def => [def.name, def]));

  function get(name) {
    return byName.get(name) || byName.get(THEME_BASEMAPS.light);
  }

  const isVector = name => get(name).kind === VECTOR;
  const isRaster = name => get(name).kind === RASTER;
  const styleUrl = name => get(name).styleUrl;

  // Style documents are fetched once and shared by both renderers.
  const styleCache = new Map();
  function styleJson(url) {
    if (!styleCache.has(url)) {
      styleCache.set(url, fetch(url).then(response => {
        if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
        return response.json();
      }).catch(error => {
        styleCache.delete(url);
        throw error;
      }));
    }
    return styleCache.get(url);
  }

  // Place names and shields only: every fill and line is dropped so the imagery
  // underneath is the map, and the labels are the annotation.
  async function labelStyle(name) {
    const style = await styleJson(get(name).labelStyleUrl);
    return { ...style, layers: style.layers.filter(layer => layer.type === "symbol") };
  }

  function leafletOptions(def) {
    const options = { attribution: def.attribution, maxZoom: def.maxZoom };
    if (def.subdomains) options.subdomains = def.subdomains;
    return options;
  }

  function tileUrls(def) {
    const retina = (window.devicePixelRatio || 1) > 1 ? "@2x" : "";
    const resolved = def.template.replace("{r}", retina);
    const hosts = def.subdomains ? def.subdomains.split("") : [];
    if (!hosts.length) return [resolved];
    return hosts.map(host => resolved.replace("{s}", host));
  }

  function maplibreSource(name) {
    const def = get(name);
    return {
      type: "raster",
      tiles: tileUrls(def),
      tileSize: 256,
      maxzoom: def.maxZoom,
      attribution: def.attribution,
    };
  }

  window.eqmonMapStyleConfig = {
    BASEMAP_DEFS: BASEMAPS,
    TERRAIN,
    THEME_BASEMAPS,
    VECTOR_PLUGIN,
    names: () => BASEMAPS.map(def => def.name),
    get,
    isVector,
    isRaster,
    styleUrl,
    labelStyle,
    leafletOptions,
    tileUrls,
    maplibreSource,
    themeBasemap: mode => (mode === "dark" ? THEME_BASEMAPS.dark : THEME_BASEMAPS.light),
  };
})();
