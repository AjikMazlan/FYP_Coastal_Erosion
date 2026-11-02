from pathlib import Path
import argparse
import json

from pilot_site import load_config, run_coastsat


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "configs" / "coastsat"
COASTSAT_ROOT = Path(r"D:\CoastSat-master")

parser = argparse.ArgumentParser()
parser.add_argument("action", choices=["check", "download"])
args = parser.parse_args()

base_path = CONFIG_DIR / "bukit_keluang_2024.json"
base = json.loads(base_path.read_text(encoding="utf-8-sig"))

if base["site_id"] != "BUKIT_KELUANG":
    raise ValueError("Expected the Bukit Keluang configuration.")

# 2024 is already downloaded.
# The full 2025 dataset is separate from the March-April pilot.
years = list(range(2013, 2024)) + [2025]

for year in years:
    config = dict(base)

    config["sitename"] = f"BUKIT_KELUANG_{year}"
    config["dates"] = [
        f"{year}-01-01",
        f"{year + 1}-01-01",
    ]

    # Use Landsat 8 throughout, adding Sentinel-2 from 2015.
    config["sat_list"] = (
        ["L8"] if year < 2015 else ["L8", "S2"]
    )

    config["status"] = "historical_imagery_requires_review"
    config["notes"] = (
        f"Calendar-year request for {year}. "
        "Actual image availability and quality require review."
    )

    config_path = CONFIG_DIR / f"bukit_keluang_{year}.json"

    if config_path.exists():
        existing = json.loads(
            config_path.read_text(encoding="utf-8-sig")
        )
        if existing != config:
            raise ValueError(
                f"Existing configuration differs: {config_path}. "
                "Review it before continuing."
            )
    else:
        config_path.write_text(
            json.dumps(config, indent=2) + "\n",
            encoding="utf-8",
        )

    validated, polygon = load_config(config_path)

    print(f"\n===== BUKIT KELUANG: {year} =====", flush=True)

    run_coastsat(
        args.action,
        validated,
        polygon,
        COASTSAT_ROOT,
    )

print("\nAll requested years completed.")