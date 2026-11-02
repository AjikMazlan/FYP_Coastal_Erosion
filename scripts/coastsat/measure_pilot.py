from pathlib import Path
import pickle
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString

from pilot_site import DEFAULT_CONFIG, load_config

COASTSAT_ROOT = Path(r"D:\CoastSat-master")
sys.path.insert(0, str(COASTSAT_ROOT))

from coastsat import SDS_transects


config, _ = load_config(DEFAULT_CONFIG)
sitename = config["sitename"]
epsg = config["output_epsg"]
folder = COASTSAT_ROOT / "data" / sitename

# Read the reference and the newly drawn transects.
reference_gdf = gpd.read_file(
    folder / f"{sitename}_reference_shoreline.geojson"
).to_crs(epsg=epsg)
reference = reference_gdf.geometry.iloc[0]

original = gpd.read_file(
    folder / f"{sitename}_transects.geojson"
).to_crs(epsg=epsg)

transects = {}
geometries = []
names = []

for _, row in original.iterrows():
    name = str(row["name"])
    line = row.geometry
    coordinates = np.asarray(line.coords)

    if line.length < 1:
        raise ValueError(f"Transect {name} is too short.")

    # Preserve the drawn land-to-sea direction.
    direction = coordinates[-1] - coordinates[0]
    direction = direction / np.linalg.norm(direction)

    crossing = line.intersection(reference)
    if crossing.geom_type != "Point" or crossing.is_empty:
        raise ValueError(
            f"Transect {name} must cross the reference once."
        )

    centre = np.array([crossing.x, crossing.y])
    endpoints = np.array([
        centre - 150 * direction,
        centre + 150 * direction,
    ])

    transects[name] = endpoints
    names.append(name)
    geometries.append(LineString(endpoints))

# Save the extended geometry in a separate file.
extended = gpd.GeoDataFrame(
    {"name": names},
    geometry=geometries,
    crs=f"EPSG:{epsg}",
)
extended_path = folder / f"{sitename}_transects_300m.geojson"
extended.to_file(extended_path, driver="GeoJSON")

with (folder / f"{sitename}_output.pkl").open("rb") as file:
    raw = pickle.load(file)

# Exclude empty shoreline records.
keep = [
    i for i, shoreline in enumerate(raw["shorelines"])
    if len(shoreline) > 0
]
if not keep:
    raise ValueError("No non-empty shorelines available.")

output = {
    "dates": [raw["dates"][i] for i in keep],
    "shorelines": [raw["shorelines"][i] for i in keep],
}

qc_settings = {
    "along_dist": 25,
    "min_points": 3,
    "max_std": 15,
    "max_range": 40,
    "min_chainage": 0,
    "multiple_inter": "nan",
    "auto_prc": 0.1,
}

distances = SDS_transects.compute_intersection_QC(
    output, transects, qc_settings
)

records = []
for name, values in distances.items():
    for date, value in zip(output["dates"], values):
        valid = bool(np.isfinite(value) and 0 <= value <= 300)

        records.append({
            "Date": str(date)[:10],
            "Transect_ID": name,
            "Cross_Shore_Distance_m": value if valid else np.nan,
            "Valid": valid,
            "Tide_Corrected": False,
        })

results = pd.DataFrame(records)
csv_path = folder / f"{sitename}_pilot_measurements.csv"
results.to_csv(csv_path, index=False, float_format="%.3f")

print(results.to_string(index=False))
print("\nExtended transects:", extended_path)
print("Measurements:", csv_path)