/* One catalogue of basemaps and terrain, described once and handed to whichever
 * renderer needs it. Loads before app.js: the 2D map builds Leaflet tile layers
 * from these definitions, and the 3D map builds MapLibre raster sources from the
 * same rows, so the two can never drift apart on URL, zoom ceiling, or credit.
 *
 * Placeholder differences between the two renderers are resolved here and
 * nowhere else: Leaflet rotates hosts through `{s}` and picks retina tiles with
 * `{r}`, while MapLibre takes an explicit list of URLs with neither.
 */
(function () {
  "use strict";

  const OSM_ATTR = "© OpenStreetMap contributors";
  const CARTO_ATTR = OSM_ATTR + " © CARTO";
  const ESRI_ATTR = "Tiles © Esri";

  const BASEMAPS = [
    { name: "OpenStreetMap", template: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      subdomains: "abc", maxZoom: 19, attribution: OSM_ATTR },
    { name: "Humanitarian (HOT)", template: "https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png",
      subdomains: "abc", maxZoom: 19, attribution: OSM_ATTR + " © Humanitarian OpenStreetMap Team" },
    { name: "Topographic", template: "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
      subdomains: "abc", maxZoom: 17, attribution: OSM_ATTR + " © OpenTopoMap (CC-BY-SA)" },
    { name: "Light (Positron)", template: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
      subdomains: "abcd", maxZoom: 20, attribution: CARTO_ATTR },
    { name: "Voyager", template: "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
      subdomains: "abcd", maxZoom: 20, attribution: CARTO_ATTR },
    { name: "Dark (Dark Matter)", template: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
      subdomains: "abcd", maxZoom: 20, attribution: CARTO_ATTR },
    { name: "CyclOSM", template: "https://{s}.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png",
      subdomains: "abc", maxZoom: 20, attribution: OSM_ATTR + " © CyclOSM" },
    { name: "Transport (OPNVKarte)", template: "https://tileserver.memomaps.de/tilegen/{z}/{x}/{y}.png",
      subdomains: "", maxZoom: 18, attribution: OSM_ATTR + " © ÖPNVKarte" },
    { name: "Satellite (Esri)",
      template: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      subdomains: "", maxZoom: 19, attribution: ESRI_ATTR + ", Maxar, Earthstar Geographics" },
  ];

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

  const THEME_BASEMAPS = { light: "OpenStreetMap", dark: "Dark (Dark Matter)" };

  const byName = new Map(BASEMAPS.map(def => [def.name, def]));

  function get(name) {
    return byName.get(name) || byName.get(THEME_BASEMAPS.light);
  }

  // Leaflet reads the template as written; only the host rotation needs naming.
  function leafletOptions(def) {
    const options = { attribution: def.attribution, maxZoom: def.maxZoom };
    if (def.subdomains) options.subdomains = def.subdomains;
    return options;
  }

  // MapLibre has no `{s}` or `{r}`, so hosts are expanded into one URL each and
  // the retina suffix is resolved against this display.
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
    names: () => BASEMAPS.map(def => def.name),
    get,
    leafletOptions,
    tileUrls,
    maplibreSource,
    themeBasemap: mode => (mode === "dark" ? THEME_BASEMAPS.dark : THEME_BASEMAPS.light),
  };
})();
