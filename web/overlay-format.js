/* Reference-overlay presentation shared by both renderers.
 *
 * The hover tooltip is the one place an operator reads raw boundary and fault
 * attributes, and those columns are not uniform across the source shapefiles.
 * The rules for turning them into a tooltip therefore live here once, so the 2D
 * and 3D maps cannot format the same feature two different ways.
 *
 * Loads before app.js. Pure: no DOM, no renderer, no configuration of its own.
 */
(function () {
  "use strict";

  // Tried in order when an overlay declares no `hoverFields` of its own.
  const DEFAULT_HOVER_FIELDS = [
    "Name", "name", "Fault_Name", "FAULT", "fault",
    "TYPE", "Type", "type", "Length_km", "Fault_Leng", "SlipRate",
  ];

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // A stable pastel per distinct name. Used where a layer has many polygons and
  // no published palette, so the point is telling neighbours apart, not encoding
  // a value. The hash must not change: both renderers have to land on the same
  // colour for the same name.
  function pastelFromName(name) {
    let hash = 0;
    for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
    return `hsl(${((hash % 360) + 360) % 360}, 45%, 75%)`;
  }

  function hoverFields(config) {
    return config?.hoverFields ?? DEFAULT_HOVER_FIELDS;
  }

  // Hit tolerance in pixels. Lines need slack because an operator cannot land a
  // cursor on a one-pixel fault; filled polygons do not.
  function hoverTolerance(config) {
    if (config?.hoverTolerancePx != null) return config.hoverTolerancePx;
    return config?.lineOnly || config?.faultStyle ? 8 : 16;
  }

  // Faults and named zones carry attributes worth reading; a plain boundary line
  // usually does not, unless it declares fields explicitly.
  function needsHover(name, config) {
    return Boolean(config?.hoverFields) ||
      name.includes("Fault") || name.includes("fault") || name === "Tectonic Zones";
  }

  function tooltipHtml(name, config, props) {
    const fields = hoverFields(config);
    const labels = config?.hoverLabels || {};
    const units = config?.hoverUnits || {};
    const lines = [];
    for (const key of fields) {
      const value = props?.[key];
      if (value == null || value === "") continue;
      // A configured label wins; otherwise fall back to the raw column name,
      // de-underscored. An explicit null means "no label" -- the value stands on
      // its own as the tooltip's heading.
      const label = key in labels ? labels[key] : key.replace(/_/g, " ");
      const unit = units[key] ? ` ${escapeHtml(units[key])}` : "";
      const text = escapeHtml(String(value)) + unit;
      lines.push(label ? `${escapeHtml(label)}: ${text}` : `<b>${text}</b>`);
    }
    if (lines.length === 0) return escapeHtml(name);
    // A single unlabelled field is the feature's name: show it plainly rather
    // than emphasised, since there is nothing for it to stand out against.
    if (fields.length === 1 && lines.length === 1) return escapeHtml(String(props[fields[0]]));
    return lines.join("<br>");
  }

  window.eqmonOverlayFormat = {
    DEFAULT_HOVER_FIELDS,
    escapeHtml,
    pastelFromName,
    hoverFields,
    hoverTolerance,
    needsHover,
    tooltipHtml,
  };
})();
