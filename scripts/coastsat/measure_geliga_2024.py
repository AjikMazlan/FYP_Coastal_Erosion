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


PROJECT_ROOT = Path(__file__).resolve().parents[2]

config_path = (
    PROJECT_ROOT
    / "configs"
    / "coastsat"
    / "jps_batch_2024_v1"
    / "roi_c12_jps_144.json"
)

config, _ = load_config(config_path)
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

        # Extend the search along the original transect direction.
    search_line = LineString([
        coordinates[0] - 50 * direction,
        coordinates[-1] + 50 * direction,
    ])

    crossing = search_line.intersection(reference)
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

review_dates = {"2024-08-02", "2024-08-03"}

for name, values in distances.items():
    for index, (date, value) in enumerate(
        zip(output["dates"], values)
    ):
        source_index = keep[index]
        date_text = str(date)[:10]

        valid = bool(
            np.isfinite(value) and 0 <= value <= 300
        )

        records.append({
            "Date": date_text,
            "Acquisition_Time": str(date),
            "Transect_ID": name,
            "Satellite": raw["satname"][source_index],
            "Source_File": raw["filename"][source_index],
            "Cross_Shore_Distance_m": (
                value if valid else np.nan
            ),
            "Valid": valid,
            "Tide_Corrected": False,
            "QC_Status": "UNVALIDATED",
            "Review_Flag": (
                "CROSS_SENSOR_PAIR_REVIEW"
                if date_text in review_dates
                else ""
            ),
        })

results = pd.DataFrame(records)
csv_path = folder / f"{sitename}_measurements.csv"
results.to_csv(csv_path, index=False, float_format="%.3f")

print(results.to_string(index=False))
print("\nExtended transects:", extended_path)
print("Measurements:", csv_path)

# Provisional summaries: retain observations flagged for review.
data = results.loc[results["Valid"].eq(True)].copy()

data["Date"] = pd.to_datetime(data["Date"], errors="raise")
data["Year"] = data["Date"].dt.year
data["Month"] = data["Date"].dt.month
data["Flagged"] = data["Review_Flag"].fillna("").ne("")

if data.duplicated(["Date", "Transect_ID"]).any():
    raise ValueError(
        "Multiple observations per transect/date: "
        "prepare daily medians before summarizing."
    )

annual = data.groupby(
    ["Year", "Transect_ID"], as_index=False
).agg(
    Count_Days=("Date", "nunique"),
    Months_Covered=("Month", "nunique"),
    Median_m=("Cross_Shore_Distance_m", "median"),
    Min_m=("Cross_Shore_Distance_m", "min"),
    Max_m=("Cross_Shore_Distance_m", "max"),
    Std_m=("Cross_Shore_Distance_m", "std"),
    Flagged_Days=("Flagged", "sum"),
)

annual["Range_m"] = annual["Max_m"] - annual["Min_m"]

by_sensor = data.groupby(
    ["Year", "Transect_ID", "Satellite"], as_index=False
).agg(
    Count_Days=("Date", "nunique"),
    Months_Covered=("Month", "nunique"),
    Median_m=("Cross_Shore_Distance_m", "median"),
    Min_m=("Cross_Shore_Distance_m", "min"),
    Max_m=("Cross_Shore_Distance_m", "max"),
    Std_m=("Cross_Shore_Distance_m", "std"),
    Flagged_Days=("Flagged", "sum"),
)

for summary in [annual, by_sensor]:
    summary["QC_Status"] = "UNVALIDATED"
    summary["Tide_Corrected"] = False
    summary["Flagged_Observations_Included"] = True

summary_dir = PROJECT_ROOT / "results" / "geliga_2024_review"
summary_dir.mkdir(parents=True, exist_ok=True)

annual.to_csv(
    summary_dir / "annual_summary_UNVALIDATED.csv",
    index=False,
    float_format="%.3f",
)

by_sensor.to_csv(
    summary_dir / "sensor_summary_UNVALIDATED.csv",
    index=False,
    float_format="%.3f",
)

print("\nPROVISIONAL 2024 SUMMARY:")
print(annual.round(3).to_string(index=False))

print("\nSUMMARY BY SENSOR:")
print(by_sensor.round(3).to_string(index=False))

print("\nSummary folder:", summary_dir)