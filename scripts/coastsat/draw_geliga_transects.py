from pathlib import Path
import pickle
import sys
import matplotlib

matplotlib.use("QtAgg")

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
folder = COASTSAT_ROOT / "data" / config["sitename"]

output_path = folder / f"{config['sitename']}_output.pkl"
transects_path = folder / f"{config['sitename']}_transects.geojson"

if transects_path.exists():
    raise FileExistsError(
        "Transects already exist. Review or back them up before redrawing."
    )

with output_path.open("rb") as file:
    raw = pickle.load(file)

# Use only non-empty shorelines for the drawing window.
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

settings = {
    "inputs": {
        "sitename": config["sitename"],
        "filepath": str(COASTSAT_ROOT / "data"),
    },
    "output_epsg": config["output_epsg"],
}

transects = SDS_transects.draw_transects(output, settings)

print("Transects created:", len(transects))
print("Saved:", transects_path)