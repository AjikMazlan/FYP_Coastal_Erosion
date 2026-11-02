"""Prepare JPS ROI configurations and check imagery availability."""

import argparse
import csv
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from pilot_site import load_config, run_coastsat

ROOT = Path(__file__).resolve().parents[2]

DEFAULT_BATCH = (
    ROOT
    / "configs/coastsat/jps_batch_2024_v1/batch_manifest.json"
)


def read_json(path):
    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def save_config(path, value):
    # Preserve existing configurations if their contents differ.
    if path.exists():
        if read_json(path) != value:
            raise ValueError(
                f"Existing file differs: {path}. "
                "Use a new --out folder."
            )
        return

    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(
            value,
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )


def prepare(args):
    source = read_json(args.roi)

    if (
        source.get("type") != "FeatureCollection"
        or not source.get("features")
    ):
        raise ValueError(
            "Expected a non-empty ROI FeatureCollection."
        )

    start = date(args.year, 1, 1).isoformat()
    end = date(args.year + 1, 1, 1).isoformat()

    folder = args.out or (
        ROOT / f"configs/coastsat/jps_batch_{args.year}_v1"
    )

    entries = []
    seen = set()

    for feature in source["features"]:
        props = feature["properties"]
        roi_id = props["roi_id"]

        if (
            not re.fullmatch(r"[A-Z0-9_]+", roi_id)
            or roi_id in seen
        ):
            raise ValueError("Invalid or duplicate ROI ID.")

        seen.add(roi_id)

        if not 0 < float(props["approx_area_km2"]) < 100:
            raise ValueError(
                f"Invalid approximate area: {roi_id}"
            )

        roi_file = f"{roi_id.lower()}.geojson"
        config_file = f"{roi_id.lower()}.json"

        # Separate names from existing Merang/Bukit Keluang data.
        site_id = f"JPS_BATCH_{roi_id}"

        save_config(
            folder / roi_file,
            {
                "type": "FeatureCollection",
                "features": [feature],
            },
        )

        save_config(
            folder / config_file,
            {
                "site_id": site_id,
                "site_name": (
                    f"{roi_id} - {props['district']}"
                ),
                "sitename": (
                    f"{site_id}_{args.year}_V1"
                ),
                "earth_engine_project": args.project,
                "roi_file": roi_file,
                "dates": [start, end],
                "sat_list": ["L8", "S2"],
                "output_epsg": 32648,
                "jps_station_ids": props["station_ids"],
                "source_roi_id": roi_id,
                "status": (
                    "draft_roi_requires_satellite_image_review"
                ),
                "download_enabled": False,
                "notes": (
                    "Availability check only. "
                    "ROI geometry remains a draft. "
                    "JPS stations locate the area; "
                    "they are not CoastSat transects. "
                    "This batch does not reuse or overwrite "
                    "existing Merang/Bukit Keluang folders."
                ),
            },
        )

        # Validate using the existing pilot script.
        load_config(folder / config_file)

        entries.append({
            "roi_id": roi_id,
            "config_file": config_file,
        })

    manifest = folder / "batch_manifest.json"

    save_config(
        manifest,
        {
            "year": args.year,
            "dates": [start, end],
            "status": "draft_availability_check",
            "sites": entries,
        },
    )

    print("Configurations ready:", len(entries))
    print(
        "Dates (end exclusive):",
        start, "to", end,
    )
    print("Satellites: L8, S2")
    print("Manifest:", manifest.resolve())
    print(
        "No imagery downloaded; "
        "no model training performed."
    )


def check(args):
    manifest = read_json(args.batch)
    entries = manifest["sites"]

    if args.roi_ids:
        requested = set(args.roi_ids)

        unknown = requested - {
            item["roi_id"] for item in entries
        }

        if unknown:
            raise ValueError(
                f"Unknown ROI IDs: {sorted(unknown)}"
            )

        entries = [
            item for item in entries
            if item["roi_id"] in requested
        ]

    if args.limit is not None:
        if args.limit < 1:
            raise ValueError("--limit must be positive.")

        entries = entries[:args.limit]

    if not entries:
        raise ValueError("No ROIs selected.")

    if not (
        args.coastsat_root / "coastsat/SDS_download.py"
    ).is_file():
        raise ValueError(
            "--coastsat-root must point "
            "to the CoastSat source folder."
        )

    report_dir = ROOT / "results/coastsat_batch_checks"
    report_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )

    report = report_dir / f"check_{stamp}.csv"

    columns = [
        "roi_id",
        "sitename",
        "start_date",
        "end_date_exclusive",
        "L8_local",
        "L8_new",
        "S2_local",
        "S2_new",
        "status",
        "error",
    ]

    completed = 0

    with report.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=columns,
        )
        writer.writeheader()
        stream.flush()

        for index, item in enumerate(entries, 1):
            print(
                f"\n=== [{index}/{len(entries)}] "
                f"{item['roi_id']} ===",
                flush=True,
            )

            row = dict.fromkeys(columns, "")
            row["roi_id"] = item["roi_id"]

            try:
                config, polygon = load_config(
                    args.batch.parent / item["config_file"]
                )

                row.update(
                    sitename=config["sitename"],
                    start_date=config["dates"][0],
                    end_date_exclusive=config["dates"][1],
                )

                # Check only: retrieve_images is not called.
                result = run_coastsat(
                    "check",
                    config,
                    polygon,
                    args.coastsat_root,
                )

                for satellite in ["L8", "S2"]:
                    row[f"{satellite}_local"] = (
                        result["local"].get(satellite, 0)
                    )
                    row[f"{satellite}_new"] = (
                        result["new"].get(satellite, 0)
                    )

                count = (
                    sum(result["local"].values())
                    + sum(result["new"].values())
                )

                row["status"] = (
                    "available" if count else "no_images"
                )

                completed += 1

            except Exception as error:
                row.update(
                    status="failed",
                    error=str(error),
                )

                print(
                    "CHECK FAILED:",
                    error,
                    flush=True,
                )

            # Preserve each completed result immediately.
            writer.writerow(row)
            stream.flush()

    print(
        "\nAvailability checks completed:",
        completed, "/", len(entries),
    )
    print("Report:", report.resolve())
    print(
        "Counts are per ROI; overlapping ROIs "
        "may use the same satellite scenes."
    )
    print(
        "Image counts do not establish shoreline quality. "
        "No imagery downloaded."
    )


def main():
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    commands = parser.add_subparsers(
        dest="action",
        required=True,
    )

    p = commands.add_parser("prepare")

    p.add_argument(
        "--roi",
        type=Path,
        default=(
            ROOT
            / "results/jps_catalog_draft/roi_draft.geojson"
        ),
    )
    p.add_argument("--year", type=int, default=2024)
    p.add_argument(
        "--project",
        default="coastal-erosion-fyp",
    )
    p.add_argument("--out", type=Path)

    c = commands.add_parser("check")

    c.add_argument(
        "--batch",
        type=Path,
        default=DEFAULT_BATCH,
    )
    c.add_argument(
        "--coastsat-root",
        type=Path,
        required=True,
    )
    c.add_argument("--roi-ids", nargs="+")
    c.add_argument("--limit", type=int)

    args = parser.parse_args()

    if args.action == "prepare":
        prepare(args)
    else:
        check(args)


if __name__ == "__main__":
    main()