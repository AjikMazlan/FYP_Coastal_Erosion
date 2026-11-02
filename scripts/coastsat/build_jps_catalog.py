"""Build a draft JPS location catalogue and ROI preview."""

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Initial grouping settings, not validated coastal boundaries.
PAD_M = 750
MAX_GAP_M = 2500
MAX_SPAN_M = 4000


def dump_json(path, value):
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ) + "\n",
        encoding="utf-8",
    )


def dimensions(rows):
    lat = sum(r["lat"] for r in rows) / len(rows)

    width = (
        max(r["lon"] for r in rows)
        - min(r["lon"] for r in rows)
    )
    height = (
        max(r["lat"] for r in rows)
        - min(r["lat"] for r in rows)
    )

    return (
        width * 111320 * math.cos(math.radians(lat)),
        height * 111320,
    )


def distance(a, b):
    lat = math.radians((a["lat"] + b["lat"]) / 2)

    return math.hypot(
        (a["lon"] - b["lon"]) * 111320 * math.cos(lat),
        (a["lat"] - b["lat"]) * 111320,
    )


HTML = """<!doctype html>
<html lang="ms">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pratonton katalog JPS dan ROI</title>

<link rel="stylesheet"
 href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">

<style>
body {
  margin:0;
  font:15px system-ui;
  color:#173344;
  background:#f3f7f8;
}
header {padding:14px 20px;background:white}
h1 {font-size:21px;margin:0 0 8px}
p {margin:6px 0}
select {
  max-width:100%;
  padding:8px;
  margin:5px 12px 5px 0;
}
#map {height:72vh;min-height:360px}
.legend {font-size:13px}
</style>

<header>
<h1>Katalog lokasi JPS dan cadangan ROI</h1>
<p id="summary"></p>

<label>Lokasi
<select id="sites">
<option value="">Semua lokasi</option>
</select>
</label>

<label>ROI
<select id="rois">
<option value="">Semua ROI</option>
</select>
</label>

<p class="legend">
Hijau: Stable | Jingga: Warning |
Merah: Critical | Kelabu: Protected
</p>

<p>
Poligon jingga ialah ROI draf, bukan garis pantai atau ramalan.
Semak nama, kedudukan dan pertindihan sebelum muat turun.
</p>
</header>

<div id="map"></div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

<script>
const data = __PAYLOAD__;

document.getElementById('summary').textContent =
  `${data.points.features.length} titik JPS asal | ` +
  `${data.catalog.length} kumpulan lokasi | ` +
  `${data.rois.features.length} ROI draf`;

if (typeof L === 'undefined') {
  document.getElementById('map').textContent =
    'Peta memerlukan internet untuk memuatkan Leaflet dan OpenStreetMap.';
} else {
  const map = L.map('map');

  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom:19,
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">' +
      'OpenStreetMap</a> contributors'
  }).addTo(map);

  const esc = s => String(s).replace(
    /[&<>"']/g,
    c => ({
      '&':'&amp;',
      '<':'&lt;',
      '>':'&gt;',
      '"':'&quot;',
      "'":'&#39;'
    }[c])
  );

  const colors = {
    Stable:'#16a34a',
    Warning:'#f59e0b',
    Critical:'#dc2626',
    Protected:'#64748b'
  };

  const roiLayers = {};

  const rois = L.geoJSON(data.rois, {
    style:{
      color:'#b45309',
      weight:2,
      fillOpacity:0.07
    },
    onEachFeature:(f,l) => {
      roiLayers[f.properties.roi_id] = l;

      l.bindPopup(
        `<b>${esc(f.properties.roi_id)}</b><br>` +
        `JPS: ${f.properties.station_ids.join(', ')}<br>` +
        `Luas anggaran: ${f.properties.approx_area_km2} km2<br>` +
        'Status: draf, belum disemak'
      );
    }
  }).addTo(map);

  const points = L.geoJSON(data.points, {
    pointToLayer:(f,ll) => L.circleMarker(ll, {
      radius:6,
      color:'#111827',
      weight:1,
      fillOpacity:1,
      fillColor:colors[f.properties.risk_label] || '#64748b'
    }),
    onEachFeature:(f,l) => {
      l.bindPopup(
        `<b>${esc(f.properties.name)}</b><br>` +
        `${esc(f.properties.district)} / ` +
        `${esc(f.properties.coastal_cell)}<br>` +
        `JPS No: ${f.properties.station_id}<br>` +
        `Risiko: ${esc(f.properties.risk_label)}<br>` +
        `ROI: ${esc(f.properties.roi_id)}`
      );
    }
  }).addTo(map);

  const fullBounds = rois.getBounds();
  map.fitBounds(fullBounds,{padding:[20,20]});

  L.control.layers(null,{
    'ROI draf':rois,
    'Titik JPS asal':points
  }).addTo(map);

  const siteSelect = document.getElementById('sites');
  const roiSelect = document.getElementById('rois');

  for (const s of data.catalog) {
    siteSelect.add(new Option(
      `${s.name} | ${s.district} | ${s.coastal_cell}`,
      s.site_id
    ));
  }

  for (const f of data.rois.features) {
    roiSelect.add(new Option(
      `${f.properties.roi_id} | JPS ` +
      f.properties.station_ids.join(', '),
      f.properties.roi_id
    ));
  }

  siteSelect.onchange = () => {
    roiSelect.value = '';

    const s = data.catalog.find(
      x => x.site_id === siteSelect.value
    );

    const selected = s
      ? data.points.features.filter(
          f => s.station_ids.includes(f.properties.station_id)
        )
      : [];

    const bounds = s
      ? L.latLngBounds(selected.map(
          f => [
            f.geometry.coordinates[1],
            f.geometry.coordinates[0]
          ]
        ))
      : fullBounds;

    map.fitBounds(bounds,{
      padding:[35,35],
      maxZoom:15
    });
  };

  roiSelect.onchange = () => {
    siteSelect.value = '';

    const layer = roiLayers[roiSelect.value];

    map.fitBounds(
      layer ? layer.getBounds() : fullBounds,
      {padding:[25,25],maxZoom:15}
    );

    if (layer) layer.openPopup();
  };
}
</script>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "data/processed/coastal_app_locations.csv",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "results/jps_catalog_draft",
    )

    args = parser.parse_args()

    with args.input.open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        reader = csv.DictReader(stream)

        required = {
            "No", "Source_Type", "Area_Location",
            "District", "Coastal_Cell",
            "Latitude_DD", "Longitude_DD", "Risk_Label",
        }

        if not required.issubset(reader.fieldnames or []):
            raise ValueError(
                "Input CSV does not have the required app columns."
            )

        # Interpolated points are not independent JPS observations.
        originals = [
            r for r in reader
            if r["Source_Type"].strip() == "JPS_Original"
        ]

    rows = []

    for r in originals:
        number = float(r["No"])
        lat = float(r["Latitude_DD"])
        lon = float(r["Longitude_DD"])

        if not number.is_integer() or number < 1:
            raise ValueError("Invalid JPS station number.")

        if not (
            math.isfinite(lat)
            and math.isfinite(lon)
            and -90 < lat < 90
            and -180 <= lon <= 180
        ):
            raise ValueError("Invalid coordinates.")

        values = [
            r[k].strip()
            for k in [
                "Area_Location", "District",
                "Coastal_Cell", "Risk_Label",
            ]
        ]

        if not all(values):
            raise ValueError("Missing location or risk label.")

        rows.append({
            "id": int(number),
            "lat": lat,
            "lon": lon,
            "name": values[0],
            "district": values[1],
            "cell": values[2],
            "risk": values[3],
        })

    rows.sort(key=lambda r: r["id"])

    if not rows or len({r["id"] for r in rows}) != len(rows):
        raise ValueError(
            "Original JPS stations are empty or duplicated."
        )

    named = defaultdict(list)
    sectors = defaultdict(list)

    for r in rows:
        named[
            (r["cell"], r["district"], r["name"])
        ].append(r)

        sectors[
            (r["cell"], r["district"])
        ].append(r)

    # Draft grouping uses JPS station order and approximate distances.
    blocks = []

    for group in sectors.values():
        current = []

        for r in group:
            width, height = dimensions(current + [r])

            split = current and (
                distance(r, current[-1]) > MAX_GAP_M
                or max(width, height) > MAX_SPAN_M
            )

            if split:
                blocks.append(current)
                current = []

            current.append(r)

        if current:
            blocks.append(current)

    roi_features = []
    station_roi = {}

    for block in blocks:
        roi_id = (
            f"ROI_{block[0]['cell']}_"
            f"JPS_{block[0]['id']:03d}"
        )

        midlat = sum(r["lat"] for r in block) / len(block)

        dy = PAD_M / 111320
        dx = dy / math.cos(math.radians(midlat))

        west = min(r["lon"] for r in block) - dx
        east = max(r["lon"] for r in block) + dx
        south = min(r["lat"] for r in block) - dy
        north = max(r["lat"] for r in block) + dy

        # Approximate spherical area, for planning only.
        area = (
            6371008.8 ** 2
            * math.radians(east - west)
            * (
                math.sin(math.radians(north))
                - math.sin(math.radians(south))
            )
            / 1e6
        )

        if area >= 100:
            raise ValueError(
                "Draft ROI is too large; reduce grouping limits."
            )

        for r in block:
            station_roi[r["id"]] = roi_id

        roi_features.append({
            "type": "Feature",
            "properties": {
                "roi_id": roi_id,
                "coastal_cell": block[0]["cell"],
                "district": block[0]["district"],
                "station_ids": [r["id"] for r in block],
                "approx_area_km2": round(area, 3),
                "status": "draft_requires_image_review",
                "download_enabled": False,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [west, south],
                    [east, south],
                    [east, north],
                    [west, north],
                    [west, south],
                ]],
            },
        })

    catalog = []
    station_site = {}

    for (cell, district, name), group in named.items():
        site_id = f"JPS_{group[0]['id']:03d}"

        for r in group:
            station_site[r["id"]] = site_id

        catalog.append({
            "site_id": site_id,
            "name": name,
            "district": district,
            "coastal_cell": cell,
            "station_ids": [r["id"] for r in group],
            "risk_counts_original_jps": dict(
                Counter(r["risk"] for r in group)
            ),
            "roi_ids": sorted({
                station_roi[r["id"]] for r in group
            }),
            "center_lat": (
                sum(r["lat"] for r in group) / len(group)
            ),
            "center_lon": (
                sum(r["lon"] for r in group) / len(group)
            ),
            "catalog_status": "draft_name_and_location_review",
            "lr_link_status": "not_yet_matched_to_existing_models",
        })

    points = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "station_id": r["id"],
                    "site_id": station_site[r["id"]],
                    "name": r["name"],
                    "district": r["district"],
                    "coastal_cell": r["cell"],
                    "risk_label": r["risk"],
                    "roi_id": station_roi[r["id"]],
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [r["lon"], r["lat"]],
                },
            }
            for r in rows
        ],
    }

    rois = {
        "type": "FeatureCollection",
        "features": roi_features,
    }

    args.out.mkdir(parents=True, exist_ok=True)

    dump_json(args.out / "catalog.json", catalog)
    dump_json(args.out / "jps_original_points.geojson", points)
    dump_json(args.out / "roi_draft.geojson", rois)

    with (args.out / "catalog.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(catalog[0])
        )
        writer.writeheader()

        for item in catalog:
            writer.writerow({
                key: (
                    json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (list, dict))
                    else value
                )
                for key, value in item.items()
            })

    payload = json.dumps(
        {
            "catalog": catalog,
            "points": points,
            "rois": rois,
        },
        ensure_ascii=False,
        allow_nan=False,
    ).replace("<", "\\u003c")

    preview = args.out / "preview.html"

    preview.write_text(
        HTML.replace("__PAYLOAD__", payload),
        encoding="utf-8",
    )

    print("Original JPS stations:", len(rows))
    print("Draft location groups:", len(catalog))
    print("Draft ROIs:", len(roi_features))

    print(
        "Max approximate ROI area (km2):",
        max(
            f["properties"]["approx_area_km2"]
            for f in roi_features
        ),
    )

    print("No satellite images downloaded.")
    print("Existing models are not modified.")
    print("Drafts need review; LR links have not been inferred.")
    print("Preview:", preview.resolve())


if __name__ == "__main__":
    main()