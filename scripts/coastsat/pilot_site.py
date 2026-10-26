"""Preview a site, check available images, or download a separate CoastSat pilot."""

import argparse
from datetime import date
import importlib
import json
from pathlib import Path
import re
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "coastsat" / "bukit_keluang_pilot.json"


def load_config(config_path):
    """Validate the sampling request and its WGS84 rectangular study area."""
    config_path = Path(config_path).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    site_id = config["site_id"]
    sitename = config["sitename"]
    if not re.fullmatch(r"[A-Z0-9_]+", site_id):
        raise ValueError("site_id must contain only uppercase letters, digits and underscores")
    if not re.fullmatch(r"[A-Z0-9_]+", sitename) or not sitename.startswith(site_id + "_"):
        raise ValueError("sitename must begin with site_id followed by an underscore")
    if not config["earth_engine_project"]:
        raise ValueError("An Earth Engine project is required")

    start, end = [date.fromisoformat(value) for value in config["dates"]]
    if start >= end:
        raise ValueError("The date range must have a start before its exclusive end")
    if not config["sat_list"] or not set(config["sat_list"]).issubset({"L5", "L7", "L8", "L9", "S2"}):
        raise ValueError("Choose supported CoastSat satellites")

    roi_path = config_path.parent / config["roi_file"]
    geojson = json.loads(roi_path.read_text(encoding="utf-8-sig"))
    if geojson.get("type") != "FeatureCollection" or len(geojson["features"]) != 1:
        raise ValueError("The ROI must contain one GeoJSON feature")
    geometry = geojson["features"][0]["geometry"]
    if geometry["type"] != "Polygon" or len(geometry["coordinates"]) != 1:
        raise ValueError("The ROI must be a single Polygon without holes")
    ring = geometry["coordinates"][0]
    if len(ring) != 5 or ring[0] != ring[-1]:
        raise ValueError("The pilot ROI must be a closed four-corner rectangle")
    if any(len(point) != 2 or not (-180 <= point[0] <= 180 and -90 <= point[1] <= 90) for point in ring):
        raise ValueError("ROI coordinates must be WGS84 longitude, latitude pairs")
    west, east = min(p[0] for p in ring), max(p[0] for p in ring)
    south, north = min(p[1] for p in ring), max(p[1] for p in ring)
    expected = {(west, south), (east, south), (east, north), (west, north)}
    if west == east or south == north or set(map(tuple, ring[:-1])) != expected:
        raise ValueError("The pilot ROI must be a non-empty axis-aligned rectangle")
    if any(a[0] != b[0] and a[1] != b[1] for a, b in zip(ring, ring[1:])):
        raise ValueError("ROI edges must not cross")
    return config, geometry["coordinates"]


def request_manifest(config, polygon):
    return {
        "site_id": config["site_id"],
        "sitename": config["sitename"],
        "dates": config["dates"],
        "sat_list": config["sat_list"],
        "polygon": polygon,
    }


def run_coastsat(action, config, polygon, coastsat_root, backend=None):
    """Use the existing CoastSat checkout; check never calls retrieve_images."""
    coastsat_root = Path(coastsat_root).resolve()
    if not (coastsat_root / "coastsat" / "SDS_download.py").is_file():
        raise ValueError("--coastsat-root must point to the CoastSat source folder")
    inputs = {
        "polygon": polygon,
        "dates": config["dates"],
        "sat_list": config["sat_list"],
        "sitename": config["sitename"],
        "filepath": str(coastsat_root / "data"),
    }
    folder = coastsat_root / "data" / config["sitename"]
    manifest_path = folder / "pilot_request.json"
    manifest = request_manifest(config, polygon)
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        if previous != manifest:
            raise ValueError("This pilot folder belongs to a different ROI/date request; use a new sitename")
    elif folder.exists() and any(folder.iterdir()):
        raise ValueError("Existing pilot folder has no request manifest; inspect it or use a new sitename")

    if backend is None:
        sys.path.insert(0, str(coastsat_root))
        backend = importlib.import_module("coastsat.SDS_download")
    backend.authenticate_and_initialize(config["earth_engine_project"])

    local = backend.get_metadata(inputs) if folder.exists() and any(folder.iterdir()) else {}
    local_counts = {
        satellite: sum(
            config["dates"][0] <= str(value)[:10] < config["dates"][1]
            for value in local.get(satellite, {}).get("dates", [])
        )
        for satellite in config["sat_list"]
    }
    tier1, _ = backend.check_images_available(inputs)
    new_counts = {satellite: len(tier1.get(satellite, [])) for satellite in config["sat_list"]}
    print("\nMatching local images:", local_counts)
    print("New images available to download:", new_counts)
    print("Image counts do not establish shoreline detection quality.")

    if action == "check":
        return {"local": local_counts, "new": new_counts}
    if not sum(new_counts.values()):
        if sum(local_counts.values()):
            print("The matching images are already cached.")
            return local
        raise ValueError("No matching images were found for this pilot request")

    folder.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    metadata = backend.retrieve_images(inputs)
    counts = {satellite: len(metadata.get(satellite, {}).get("filenames", [])) for satellite in config["sat_list"]}
    print("\nDownloaded/cached image counts:", counts)
    print("Pilot folder:", folder)
    print("Next: inspect the pilot imagery, then define this site's reference shoreline and transects.")
    return metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["preview", "check", "download"])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--coastsat-root", type=Path)
    args = parser.parse_args(argv)
    config, polygon = load_config(args.config)
    print("Site:", config["site_name"])
    print("CoastSat sitename:", config["sitename"])
    print("Date range (end exclusive):", " to ".join(config["dates"]))
    print("Satellites:", ", ".join(config["sat_list"]))
    print("ROI status:", config["status"])
    print("JPS stations locating the study area:", config["jps_station_ids"])
    print("Projected CRS for later extraction:", config["output_epsg"])
    print("Notes:", config["notes"])
    if args.action == "preview":
        print("ROI coordinates (longitude, latitude):", json.dumps(polygon))
        return 0
    if args.coastsat_root is None:
        parser.error("--coastsat-root is required for check and download")
    run_coastsat(args.action, config, polygon, args.coastsat_root)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Pilot failed: {error}", file=sys.stderr)
        print("Run check/download in the existing coastsat Conda environment.", file=sys.stderr)
        raise SystemExit(1)
