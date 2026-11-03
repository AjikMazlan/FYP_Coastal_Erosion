from pathlib import Path
import sys
import matplotlib

# Interactive window for drawing.
matplotlib.use("QtAgg")

from pilot_site import DEFAULT_CONFIG, load_config

COASTSAT_ROOT = Path(r"D:\CoastSat-master")
sys.path.insert(0, str(COASTSAT_ROOT))

from coastsat import SDS_download, SDS_preprocess


PROJECT_ROOT = Path(__file__).resolve().parents[2]

config_path = (
    PROJECT_ROOT
    / "configs"
    / "coastsat"
    / "jps_batch_2024_v1"
    / "roi_c12_jps_144.json"
)

config, polygon = load_config(config_path)

inputs = {
    "sitename": config["sitename"],
    "filepath": str(COASTSAT_ROOT / "data"),
    "polygon": polygon,
    "dates": config["dates"],
    "sat_list": config["sat_list"],
}

metadata = SDS_download.get_metadata(inputs)
s2 = metadata["S2"]

# Use the image reviewed together.
selected_date = "2024-04-09"
matches = [
    i for i, filename in enumerate(s2["filenames"])
    if filename.startswith(selected_date)
]

if len(matches) != 1:
    raise ValueError(
        f"Expected one image for {selected_date}, found {len(matches)}"
    )

index = matches[0]

selected_metadata = {
    "S2": {
        key: [s2[key][index]]
        for key in ("filenames", "dates", "epsg")
    }
}

settings = {
    "inputs": inputs,
    "cloud_thresh": 0.30,
    "cloud_mask_issue": False,
    "pan_off": False,
    "s2cloudless_prob": 40,
    "output_epsg": config["output_epsg"],
}

# Support the manual function name in different CoastSat versions.
digitize = getattr(SDS_preprocess, "get_reference_sl_manual", None)
if digitize is None:
    digitize = SDS_preprocess.get_reference_sl

reference = digitize(selected_metadata, settings)

print("Reference shoreline completed.")
print("Image used:", s2["filenames"][index])
print("Reference points:", len(reference))