/* Admin heatmap — Leaflet circles sized by country search volume.
 * Reads JSON from #heatmap[data-points], joins names against a static
 * gazetteer of producing countries, draws circle markers.
 *
 * Leaflet is loaded from cdnjs at runtime to avoid an npm build step.
 * If you'd rather vendor it, drop leaflet.css and leaflet.js in /static/js
 * and switch the URLs below.
 */
(function () {
  "use strict";

  // Origins covered. Lat/lon centroids (approx).
  const GAZETTEER = {
    "colombia":          [4.57,  -74.30],
    "ethiopia":          [9.15,   40.49],
    "kenya":             [-0.02,  37.91],
    "rwanda":            [-1.94,  29.87],
    "burundi":           [-3.37,  29.92],
    "tanzania":          [-6.37,  34.89],
    "uganda":            [1.37,   32.29],
    "guatemala":         [15.78,  -90.23],
    "el salvador":       [13.79,  -88.90],
    "honduras":          [15.20,  -86.24],
    "costa rica":        [9.75,   -83.75],
    "nicaragua":         [12.87,  -85.21],
    "panama":            [8.54,   -80.78],
    "mexico":            [23.63,  -102.55],
    "peru":              [-9.19,  -75.02],
    "bolivia":           [-16.29, -63.59],
    "ecuador":           [-1.83,  -78.18],
    "brazil":            [-14.24, -51.93],
    "indonesia":         [-0.79,  113.92],
    "papua new guinea":  [-6.31,  143.96],
    "yemen":             [15.55,  48.52],
    "india":             [20.59,  78.96],
    "thailand":          [15.87,  100.99],
    "myanmar":           [21.91,  95.96],
    "vietnam":           [14.06,  108.28],
    "china":             [23.40,  101.20],   // Yunnan-weighted, not geographic centre
    "taiwan":            [23.70,  121.00],
    "philippines":       [12.88,  121.77],
    "timor leste":       [-8.87,  125.73],
    "timor-leste":       [-8.87,  125.73],
    "laos":              [19.86,  102.50],
    "dr congo":          [-4.04,  21.76],
    "drc":               [-4.04,  21.76],
  };

  function init() {
    const el = document.getElementById("heatmap");
    if (!el || typeof L === "undefined") return;

    let points;
    try {
      points = JSON.parse(el.dataset.points || "[]");
    } catch (e) {
      console.warn("heatmap: bad data-points JSON", e);
      return;
    }
    if (!Array.isArray(points) || points.length === 0) {
      el.innerHTML = '<p style="text-align:center;padding:40px;color:#7d7770;font-size:13px;">No country searches in the past 30 days.</p>';
      return;
    }

    const map = L.map(el, {
      center: [10, 0],
      zoom: 2,
      scrollWheelZoom: false,
      zoomControl: true,
      attributionControl: true,
    });

    L.tileLayer(
      "https://cartodb-basemaps-{s}.global.ssl.fastly.net/light_all/{z}/{x}/{y}{r}.png",
      {
        attribution: "&copy; OpenStreetMap &copy; CartoDB",
        subdomains: "abcd",
        maxZoom: 6,
      }
    ).addTo(map);

    // Compute scale once
    const counts = points.map(p => p.count || 0);
    const maxCount = Math.max(...counts, 1);

    points.forEach(p => {
      const key = (p.name || "").toLowerCase().trim();
      const coords = GAZETTEER[key];
      if (!coords) return;
      const ratio = p.count / maxCount;
      const radius = 8 + ratio * 28;
      L.circleMarker(coords, {
        radius: radius,
        weight: 1,
        color: "#6b3410",
        fillColor: "#a25e2c",
        fillOpacity: 0.55,
      })
        .bindTooltip(`${p.name} — ${p.count}`, { direction: "top" })
        .addTo(map);
    });
  }

  // Lazy-load Leaflet from cdnjs, then run init()
  function loadLeaflet(cb) {
    if (typeof L !== "undefined") return cb();
    const css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css";
    document.head.appendChild(css);
    const js = document.createElement("script");
    js.src = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js";
    js.onload = cb;
    document.head.appendChild(js);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => loadLeaflet(init));
  } else {
    loadLeaflet(init);
  }
})();
