from pathlib import Path
import argparse
import sys
import matplotlib

matplotlib.use("Agg")

from pilot_site import DEFAULT_CONFIG, load_config

COASTSAT_ROOT = Path(r"D:\CoastSat-master")
sys.path.insert(0, str(COASTSAT_ROOT))

from coastsat import SDS_download, SDS_preprocess


parser = argparse.ArgumentParser()
parser.add_argument(
    "--config",
    type=Path,
    default=DEFAULT_CONFIG,
)
args = parser.parse_args()

config, polygon = load_config(args.config)

inputs = {
    "sitename": config["sitename"],
    "filepath": str(COASTSAT_ROOT / "data"),
    "polygon": polygon,
    "dates": config["dates"],
    "sat_list": config["sat_list"],
}

metadata = SDS_download.get_metadata(inputs)

settings = {
    "inputs": inputs,
    "cloud_thresh": 0.99,
    "cloud_mask_issue": False,
    "pan_off": False,
    "s2cloudless_prob": 40,
}

# Save image files directly for visual inspection.
SDS_preprocess.save_jpg(
    metadata,
    settings,
    use_matplotlib=False,
)

rgb_folder = (
    COASTSAT_ROOT / "data" / config["sitename"]
    / "jpg_files" / "preprocessed" / "RGB"
)

print("\nRGB preview folder:", rgb_folder)
print("Total RGB JPG:", len(list(rgb_folder.glob("*.jpg"))))