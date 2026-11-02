from pathlib import Path
import argparse
import pickle
import sys

import geopandas as gpd
import numpy as np
import pandas as pd

from pilot_site import load_config

COASTSAT_ROOT = Path(r"D:\CoastSat-master")
sys.path.insert(0, str(COASTSAT_ROOT))

from coastsat import SDS_transects


parser = argparse.ArgumentParser()
parser.add_argument("--config", type=Path, required=True)
args = parser.parse_args()

config, _ = load_config(args.config)
if config["site_id"] != "BUKIT_KELUANG":
    raise ValueError("This script uses the fixed Bukit Keluang transects.")

sitename = config["sitename"]
folder = COASTSAT_ROOT / "data" / sitename

transects_path = (
    COASTSAT_ROOT / "data" / "BUKIT_KELUANG_2025_PILOT"
    / "BUKIT_KELUANG_2025_PILOT_transects_300m.geojson"
)

gdf = gpd.read_file(transects_path).to_crs(
    epsg=config["output_epsg"]
)

transects = {
    str(row["name"]): np.asarray(row.geometry.coords)
    for _, row in gdf.iterrows()
}

with (folder / f"{sitename}_output.pkl").open("rb") as file:
    raw = pickle.load(file)

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

qc = {
    "along_dist": 25,
    "min_points": 3,
    "max_std": 15,
    "max_range": 40,
    "min_chainage": 0,
    "multiple_inter": "nan",
    "auto_prc": 0.1,
}

distances = SDS_transects.compute_intersection_QC(
    output, transects, qc
)

records = []
for name, values in distances.items():
    length = np.linalg.norm(
        transects[name][-1] - transects[name][0]
    )

    for index, value in enumerate(values):
        source_index = keep[index]
        valid = bool(np.isfinite(value) and 0 <= value <= length)

        records.append({
            "Date": str(output["dates"][index])[:10],
            "Transect_ID": name,
            "Satellite": raw.get(
                "satname", ["unknown"] * len(raw["dates"])
            )[source_index],
            "Source_File": raw.get(
                "filename", ["unknown"] * len(raw["dates"])
            )[source_index],
            "Cross_Shore_Distance_m": value if valid else np.nan,
            "Valid": valid,
            "Tide_Corrected": False,
        })

results = pd.DataFrame(records)
measurements_path = folder / f"{sitename}_measurements.csv"
results.to_csv(measurements_path, index=False, float_format="%.3f")

valid_results = results.loc[results["Valid"]].copy()
if valid_results.empty:
    raise ValueError(
        f"No valid measurements. Inspect {measurements_path}"
    )

# One median position per transect and acquisition date.
daily = valid_results.groupby(
    ["Transect_ID", "Date"], as_index=False
).agg(
    Cross_Shore_Distance_m=("Cross_Shore_Distance_m", "median"),
    Observation_Count=("Cross_Shore_Distance_m", "size"),
)

daily["Year"] = daily["Date"].str[:4].astype(int)
daily["Month"] = daily["Date"].str[5:7].astype(int)
daily.to_csv(
    folder / f"{sitename}_daily_measurements.csv",
    index=False,
    float_format="%.3f",
)

annual = daily.groupby(
    ["Year", "Transect_ID"], as_index=False
).agg(
    Count_Days=("Cross_Shore_Distance_m", "count"),
    Months_Covered=("Month", "nunique"),
    Median_m=("Cross_Shore_Distance_m", "median"),
    Min_m=("Cross_Shore_Distance_m", "min"),
    Max_m=("Cross_Shore_Distance_m", "max"),
    Std_m=("Cross_Shore_Distance_m", "std"),
)

annual["Range_m"] = annual["Max_m"] - annual["Min_m"]
annual["Tide_Corrected"] = False

annual_path = folder / f"{sitename}_annual_summary.csv"
annual.to_csv(annual_path, index=False, float_format="%.3f")

print("\nAnnual summary:")
print(annual.round(3).to_string(index=False))
print("\nValid measurements:", int(results["Valid"].sum()), "/", len(results))
print("Measurements:", measurements_path)
print("Annual summary:", annual_path)