"""Download JPS ROIs sequentially using matching CoastSat caches."""

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from pilot_site import load_config, run_coastsat

ROOT = Path(__file__).resolve().parents[2]

DEFAULT_BATCH = (
    ROOT
    / "configs/coastsat/jps_batch_2024_v1/batch_manifest.json"
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--batch",
        type=Path,
        default=DEFAULT_BATCH,
    )
    parser.add_argument(
        "--coastsat-root",
        type=Path,
        required=True,
    )
    parser.add_argument("--roi-ids", nargs="+")
    parser.add_argument("--limit", type=int)

    args = parser.parse_args()
    args.batch = args.batch.resolve()
    args.coastsat_root = args.coastsat_root.resolve()

    if not (
        args.coastsat_root / "coastsat/SDS_download.py"
    ).is_file():
        raise ValueError("Invalid CoastSat source folder.")

    manifest = json.loads(
        args.batch.read_text(encoding="utf-8-sig")
    )
    entries = manifest["sites"]

    if len({e["roi_id"] for e in entries}) != len(entries):
        raise ValueError("Duplicate ROI IDs in the manifest.")

    if args.roi_ids:
        requested = set(args.roi_ids)

        unknown = requested - {
            e["roi_id"] for e in entries
        }

        if unknown:
            raise ValueError(
                f"Unknown ROI IDs: {sorted(unknown)}"
            )

        entries = [
            e for e in entries
            if e["roi_id"] in requested
        ]

    if args.limit is not None:
        if args.limit < 1:
            raise ValueError("--limit must be positive.")

        entries = entries[:args.limit]

    if not entries:
        raise ValueError("No ROIs selected.")

    # Validate selected configurations before downloading.
    tasks = []

    for entry in entries:
        config, polygon = load_config(
            args.batch.parent / entry["config_file"]
        )

        if config["dates"] != manifest["dates"]:
            raise ValueError(
                "Dates differ from manifest: "
                + entry["roi_id"]
            )

        if config["source_roi_id"] != entry["roi_id"]:
            raise ValueError(
                "ROI/configuration mismatch."
            )

        # Advance the working configuration to imagery download.
        # The source configuration remains a draft for review.
        job = dict(
            config,
            download_enabled=True,
            status="imagery_download_for_review",
            notes=(
                "Download imagery for review; "
                "no extraction or model training."
            ),
        )

        tasks.append(
            (entry["roi_id"], job, polygon)
        )

    if len({
        config["sitename"]
        for _, config, _ in tasks
    }) != len(tasks):
        raise ValueError(
            "Different ROIs must use different sitenames."
        )

    output_dir = ROOT / "results/coastsat_batch_downloads"
    output_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )
    report = output_dir / f"download_{stamp}.csv"

    fields = [
        "roi_id",
        "sitename",
        "L8_local",
        "S2_local",
        "L8_remaining",
        "S2_remaining",
        "status",
        "error",
    ]

    print("Selected ROIs:", len(tasks), flush=True)
    print(
        "Images folder:",
        args.coastsat_root / "data",
        flush=True,
    )
    print("Report:", report, flush=True)

    with report.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=fields,
        )
        writer.writeheader()
        stream.flush()

        for index, task in enumerate(tasks, 1):
            roi_id, config, polygon = task

            print(
                f"\n=== [{index}/{len(tasks)}] "
                f"{roi_id} ===",
                flush=True,
            )

            row = dict.fromkeys(fields, "")
            row.update(
                roi_id=roi_id,
                sitename=config["sitename"],
            )
            interrupted = False

            try:
                run_coastsat(
                    "download",
                    config,
                    polygon,
                    args.coastsat_root,
                )

                # Check whether any matching images remain.
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
                    row[f"{satellite}_remaining"] = (
                        result["new"].get(satellite, 0)
                    )

                remaining = sum(
                    result["new"].values()
                )
                local = sum(
                    result["local"].values()
                )

                if remaining:
                    row["status"] = "incomplete"
                elif local:
                    row["status"] = "cached_complete"
                else:
                    row["status"] = "empty"

            except KeyboardInterrupt:
                row.update(
                    status="interrupted",
                    error="Stopped by user.",
                )
                interrupted = True

            except Exception as error:
                row.update(
                    status="failed",
                    error=str(error),
                )

                print(
                    "DOWNLOAD FAILED:",
                    error,
                    flush=True,
                )

            writer.writerow(row)
            stream.flush()

            print(
                "ROI status:",
                row["status"],
                flush=True,
            )

            if interrupted:
                print(
                    "Stopped. Rerun the same command "
                    "to reuse matching caches."
                )
                break

    print("\nReport saved:", report.resolve())
    print(
        "cached_complete means no new images "
        "remain in the current query."
    )
    print(
        "Image quality has not been validated; "
        "no extraction or training performed."
    )


if __name__ == "__main__":
    main()