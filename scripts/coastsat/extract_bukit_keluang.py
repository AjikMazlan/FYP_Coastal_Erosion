from pathlib import Path
import argparse
import os
import sys

import geopandas as gpd
import numpy as np
import matplotlib

matplotlib.use("QtAgg")

from pilot_site import load_config

COASTSAT_ROOT = Path(r"D:\CoastSat-master")
sys.path.insert(0, str(COASTSAT_ROOT))

from coastsat import SDS_download, SDS_shoreline


parser = argparse.ArgumentParser()
parser.add_argument("--config", type=Path, required=True)
args = parser.parse_args()

config, polygon = load_config(args.config)

if config["site_id"] != "BUKIT_KELUANG":
    raise ValueError("This script uses the Bukit Keluang reference.")

folder = COASTSAT_ROOT / "data" / config["sitename"]
output_path = folder / f"{config['sitename']}_output.pkl"

if output_path.exists():
    raise FileExistsError(
        "Extraction output already exists. Back it up before rerunning."
    )

reference_path = (
    COASTSAT_ROOT / "data" / "BUKIT_KELUANG_2025_PILOT"
    / "BUKIT_KELUANG_2025_PILOT_reference_shoreline.geojson"
)

reference_gdf = gpd.read_file(reference_path)
reference_gdf = reference_gdf.to_crs(
    epsg=config["output_epsg"]
)
line = reference_gdf.geometry.iloc[0]

if line.geom_type != "LineString" or line.length < 600:
    raise ValueError("Expected a reference LineString at least 600 m long.")

sampled = [line.interpolate(distance) for distance in range(601)]
reference = np.array([[point.x, point.y] for point in sampled])

inputs = {
    "sitename": config["sitename"],
    "filepath": str(COASTSAT_ROOT / "data"),
    "polygon": polygon,
    "dates": config["dates"],
    "sat_list": config["sat_list"],
}

settings = {
    "inputs": inputs,
    "output_epsg": config["output_epsg"],
    "reference_shoreline": reference,
    "max_dist_ref": 100,
    "cloud_thresh": 0.30,
    "dist_clouds": 300,
    "check_detection": True,
    "adjust_detection": False,
    "save_figure": True,
    "min_beach_area": 1000,
    "min_length_sl": 200,
    "cloud_mask_issue": False,
    "sand_color": "default",
    "pan_off": False,
    "s2cloudless_prob": 40,
}

metadata = SDS_download.get_metadata(inputs)

# Required by CoastSat versions using relative classifier paths.
os.chdir(COASTSAT_ROOT)

output = SDS_shoreline.extract_shorelines(metadata, settings)

print("\nNon-empty shoreline results:")
accepted = 0

for date, shoreline in zip(output["dates"], output["shorelines"]):
    if len(shoreline) > 0:
        accepted += 1
        print(str(date)[:10], "| points:", len(shoreline))

print("\nAccepted non-empty shorelines:", accepted)
print("Detection images:", folder / "jpg_files" / "detection")