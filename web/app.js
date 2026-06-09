const map = L.map("map").setView([30.4, 69.3], 5); // Primary Focus Country: Pakistan
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "© OpenStreetMap", maxZoom: 12,
}).addTo(map);

// MMI legend (colors mirror _MMI_COLORS in src/eqmon/contours.py).
const MMI_PALETTE = [
  [2, "#bfccff"], [3, "#a0e6ff"], [4, "#80ffff"], [5, "#7aff93"],
  [6, "#ffff00"], [7, "#ffc800"], [8, "#ff9100"], [9, "#ff0000"], [10, "#c80000"],
];
const legend = L.control({ position: "bottomright" });
legend.onAdd = function () {
  const div = L.DomUtil.create("div", "legend");
  div.style.cssText = "background:#fff;padding:8px 10px;border-radius:6px;box-shadow:0 1px 6px rgba(0,0,0,.3)";
  div.innerHTML = "<strong>MMI</strong><br>" +
    MMI_PALETTE.map(([m, c]) => `<i style="background:${c}"></i>${m}`).join("<br>");
  return div;
};
legend.addTo(map);

let intensityLayer = null;
let epicenterMarker = null;
const statusEl = document.getElementById("status");

function style(feature) {
  return { color: feature.properties.color, weight: 1,
           fillColor: feature.properties.color, fillOpacity: 0.45 };
}

async function calculate() {
  const payload = {
    magnitude: parseFloat(document.getElementById("magnitude").value),
    depth_km:  parseFloat(document.getElementById("depth_km").value),
    lat:       parseFloat(document.getElementById("lat").value),
    lon:       parseFloat(document.getElementById("lon").value),
  };
  statusEl.textContent = "Calculating…";
  try {
    const resp = await fetch("/intensity", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      const err = await resp.json();
      statusEl.textContent = "Error: " + JSON.stringify(err.detail ?? err);
      return;
    }
    const fc = await resp.json();
    if (intensityLayer) map.removeLayer(intensityLayer);
    intensityLayer = L.geoJSON(fc, {
      style,
      onEachFeature: (f, l) =>
        l.bindPopup(`MMI ${f.properties.mmi_lower}–${f.properties.mmi_upper}`),
    }).addTo(map);

    if (epicenterMarker) map.removeLayer(epicenterMarker);
    epicenterMarker = L.circleMarker([payload.lat, payload.lon], {
      radius: 6, color: "#000", fillColor: "#fff", fillOpacity: 1,
    }).addTo(map).bindPopup("Epicenter");

    statusEl.textContent = `${fc.features.length} intensity bands`;
    if (intensityLayer.getBounds().isValid()) map.fitBounds(intensityLayer.getBounds());
  } catch (e) {
    statusEl.textContent = "Request failed: " + e.message;
  }
}

document.getElementById("calc").addEventListener("click", calculate);

// --- Event catalog (Plan B) ---
const eventsEl = document.getElementById("events");
const impactEl = document.getElementById("impact");

async function refreshEvents() {
  const resp = await fetch("/events?limit=20");
  if (!resp.ok) return;
  const events = await resp.json();
  eventsEl.innerHTML = "<strong>Catalog</strong>" + events.map(e =>
    `<div class="evt" data-id="${e.id}" style="cursor:pointer;padding:3px 0;border-bottom:1px solid #eee">
       M${e.magnitude.toFixed(1)} · ${e.source} · ${new Date(e.occurred_at).toLocaleString()}
     </div>`).join("");
  document.querySelectorAll(".evt").forEach(el =>
    el.addEventListener("click", () => showImpact(el.dataset.id)));
}

async function showImpact(id) {
  impactEl.textContent = "Computing impact…";
  const resp = await fetch(`/events/${id}/impact`, { method: "POST" });
  if (!resp.ok) { impactEl.textContent = "Impact failed"; return; }
  const data = await resp.json();
  if (intensityLayer) map.removeLayer(intensityLayer);
  intensityLayer = L.geoJSON(data.bands, { style }).addTo(map);
  if (intensityLayer.getBounds().isValid()) map.fitBounds(intensityLayer.getBounds());
  const top = data.districts.filter(d => d.mmi_max > 0).slice(0, 12);
  impactEl.innerHTML = "<strong>District impact</strong><table style='width:100%'>" +
    "<tr><th align=left>District</th><th>Max</th><th>Repr</th></tr>" +
    top.map(d => `<tr><td>${d.name ?? "?"}</td><td align=center>${d.mmi_max}</td>` +
                 `<td align=center>${d.mmi_repr}</td></tr>`).join("") + "</table>";
}

document.getElementById("ingest").addEventListener("click", async () => {
  statusEl.textContent = "Pulling USGS feed…";
  try {
    const r = await fetch("/events/ingest", { method: "POST" });
    const res = await r.json();
    statusEl.textContent = `Ingest: ${res.inserted} new of ${res.fetched}`;
  } catch (e) {
    statusEl.textContent = "Ingest failed: " + e.message;
  }
  refreshEvents();
});

refreshEvents();
