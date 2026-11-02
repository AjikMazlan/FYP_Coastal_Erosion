from pathlib import Path
import os
import sys
import numpy as np
import geopandas as gpd
import matplotlib

matplotlib.use("QtAgg")

from pilot_site import DEFAULT_CONFIG, load_config

COASTSAT_ROOT = Path(r"D:\CoastSat-master")
sys.path.insert(0, str(COASTSAT_ROOT))

from coastsat import SDS_download, SDS_shoreline


config, polygon = load_config(DEFAULT_CONFIG)

inputs = {
    "sitename": config["sitename"],
    "filepath": str(COASTSAT_ROOT / "data"),
    "polygon": polygon,
    "dates": config["dates"],
    "sat_list": config["sat_list"],
}

folder = COASTSAT_ROOT / "data" / config["sitename"]
reference_path = (
    folder / f"{config['sitename']}_reference_shoreline.geojson"
)

reference_gdf = gpd.read_file(reference_path)
reference_gdf = reference_gdf.to_crs(
    epsg=config["output_epsg"]
)
line = reference_gdf.geometry.iloc[0]

# Use the first 600 metres of the reviewed reference.
# The original reference file remains unchanged.
if line.geom_type != "LineString" or line.length < 600:
    raise ValueError("Expected a reference LineString at least 600 m long.")

sampled = [line.interpolate(distance) for distance in range(601)]
reference = np.array([[point.x, point.y] for point in sampled])

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

# CoastSat versions may locate classification models via cwd.
os.chdir(COASTSAT_ROOT)

output = SDS_shoreline.extract_shorelines(metadata, settings)

accepted = sum(
    len(shoreline) > 0
    for shoreline in output.get("shorelines", [])
)

print("\nPilot extraction completed.")
print("Accepted non-empty shorelines:", accepted)
print("Detection images:", folder / "jpg_files" / "detection")