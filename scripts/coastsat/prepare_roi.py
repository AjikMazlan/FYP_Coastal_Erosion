"""Draw reference/transects once and register a pipeline site."""

from pathlib import Path
from datetime import datetime
import argparse
import json
import re
import sys

import numpy as np

import shoreline_pipeline as pipeline
from pilot_site import load_config


def centre_transects(reference, drawn):
    from osgeo import ogr

    ogr.UseExceptions()

    shoreline = ogr.CreateGeometryFromJson(json.dumps({
        "type": "LineString",
        "coordinates": np.asarray(reference).tolist(),
    }))

    extended = {}

    for name, points in drawn.items():
        points = np.asarray(points, dtype=float)

        if points.shape != (2, 2) or not np.isfinite(points).all():
            raise ValueError(f"T{name}: expected two finite endpoints.")

        direction = points[1] - points[0]
        length = np.linalg.norm(direction)

        if length < 1:
            raise ValueError(f"T{name}: transect is too short.")

        crossing = ogr.CreateGeometryFromJson(json.dumps({
            "type": "LineString",
            "coordinates": points.tolist(),
        })).Intersection(shoreline)

        if crossing.IsEmpty() or crossing.GetGeometryType() != ogr.wkbPoint:
            raise ValueError(
                f"T{name}: draw across the reference exactly once."
            )

        centre = np.array([crossing.GetX(), crossing.GetY()])
        direction /= length

        extended[str(name)] = [
            (centre - 150 * direction).tolist(),
            (centre + 150 * direction).tolist(),
        ]

    return extended


def collection(features, epsg):
    return {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": f"EPSG:{epsg}"},
        },
        "features": features,
    }


def prepare(args):
    if not re.fullmatch(r"[a-z][a-z0-9_]*", args.site):
        raise ValueError(
            "Use a lowercase site ID such as beting_lintang."
        )

    if not args.name.strip():
        raise ValueError("A site name is required.")

    batch_path = pipeline.path(args.batch).resolve()
    batch = pipeline.read_json(batch_path)

    if any(s["id"] == args.site for s in batch["sites"]):
        print(
            "Site already configured. "
            "Use shoreline_pipeline.py status/run/build."
        )
        return

    base_path = pipeline.path(args.config).resolve()
    base, polygon = load_config(base_path)
    epsg = base["output_epsg"]

    if epsg != 32648:
        raise ValueError("The app requires EPSG:32648.")

    coast = pipeline.path(batch["coastsat_root"]).resolve()
    folder = coast / "data" / base["sitename"]

    if (
        not (coast / "coastsat/SDS_download.py").is_file()
        or not folder.is_dir()
    ):
        raise FileNotFoundError(
            "Check CoastSat path and download this ROI first."
        )

    sys.path.insert(0, str(coast))

    import matplotlib
    matplotlib.use("QtAgg")

    from coastsat import SDS_download, SDS_preprocess, SDS_transects

    inputs = dict(
        sitename=base["sitename"],
        filepath=str(coast / "data"),
        polygon=polygon,
        dates=base["dates"],
        sat_list=base["sat_list"],
    )

    metadata = SDS_download.get_metadata(inputs)
    satellite = metadata.get(args.sat, {})

    matches = [
        i
        for i, filename in enumerate(satellite.get("filenames", []))
        if filename.startswith(args.image)
    ]

    if len(matches) != 1:
        raise ValueError(
            f"Expected one {args.sat} image matching "
            f"{args.image}; found {len(matches)}."
        )

    index = matches[0]

    selected = {
        args.sat: {
            key: [satellite[key][index]]
            for key in ("filenames", "dates", "epsg")
        }
    }

    date = satellite["dates"][index]

    if not hasattr(date, "strftime"):
        date = datetime.fromisoformat(
            str(date).replace("Z", "+00:00")
        )

    year = date.year

    if year not in batch["years"]:
        raise ValueError(
            "Selected image year is outside the configured batch years."
        )

    seed_dir = (
        pipeline.ROOT
        / "data/coastsat"
        / f"{args.site}_seed_{year}"
    )

    request = dict(
        base_config=str(base_path),
        image=satellite["filenames"][index],
        satellite=args.sat,
    )
    request_path = seed_dir / "seed_request.json"

    if (
        request_path.exists()
        and pipeline.read_json(request_path) != request
    ):
        raise ValueError(
            "This seed folder belongs to another image/configuration; "
            "use a new site ID."
        )

    if (
        seed_dir.exists()
        and not request_path.exists()
        and any(seed_dir.iterdir())
    ):
        raise ValueError(
            "Existing seed folder has no request record; "
            "use a new site ID."
        )

    pipeline.write_json(request_path, request)
    reference_path = seed_dir / "reference.geojson"

    if reference_path.exists():
        features = pipeline.lines(reference_path, epsg)
        reference = np.asarray(
            features[0]["geometry"]["coordinates"],
            dtype=float,
        )
    else:
        settings = dict(
            inputs=inputs,
            cloud_thresh=0.30,
            cloud_mask_issue=False,
            pan_off=False,
            s2cloudless_prob=40,
            output_epsg=epsg,
        )

        digitize = getattr(
            SDS_preprocess,
            "get_reference_sl_manual",
            None,
        )

        if digitize is None:
            digitize = SDS_preprocess.get_reference_sl

        reference = np.asarray(
            digitize(selected, settings),
            dtype=float,
        )

        if (
            reference.ndim != 2
            or reference.shape[1] != 2
            or len(reference) < 2
            or not np.isfinite(reference).all()
        ):
            raise ValueError(
                "Draw one continuous, finite reference shoreline."
            )

        pipeline.write_json(
            reference_path,
            collection([{
                "type": "Feature",
                "properties": {"name": "reference"},
                "geometry": {
                    "type": "LineString",
                    "coordinates": reference.tolist(),
                },
            }], epsg),
        )

    (seed_dir / "jpg_files").mkdir(exist_ok=True)

    print(
        "Draw FIVE transects: first point LAND, "
        "second point SEA; then press Enter.",
        flush=True,
    )

    drawn = SDS_transects.draw_transects(
        {"dates": [date], "shorelines": [reference]},
        {
            "inputs": {
                "sitename": seed_dir.name,
                "filepath": str(seed_dir.parent),
            },
            "output_epsg": epsg,
        },
    )

    if set(map(str, drawn)) != {"1", "2", "3", "4", "5"}:
        raise ValueError(
            "Exactly five transects are needed. "
            "Rerun to draw them again; the reference is saved."
        )

    extended = centre_transects(reference, drawn)
    geometry_path = seed_dir / "transects_300m.geojson"

    pipeline.write_json(
        geometry_path,
        collection([
            {
                "type": "Feature",
                "properties": {"name": name},
                "geometry": {
                    "type": "LineString",
                    "coordinates": coordinates,
                },
            }
            for name, coordinates in extended.items()
        ], epsg),
    )

    site = dict(
        id=args.site,
        name=args.name,
        input_prefix=args.site.upper() + "_FAST_V1",
        base_config=base_path.relative_to(pipeline.ROOT).as_posix(),
        reference=reference_path.relative_to(pipeline.ROOT).as_posix(),
        transects=geometry_path.relative_to(pipeline.ROOT).as_posix(),
        existing_inputs={str(year): base["sitename"]},
    )

    pipeline.prepare_job(batch, site)

    batch["sites"].append(site)
    pipeline.write_json(batch_path, batch)

    print("ROI READY:", args.name, "| fixed transects:", len(extended))
    print("Saved:", seed_dir)
    print("Cached imagery reused for:", year)
    print(
        "Next: python scripts\\coastsat\\shoreline_pipeline.py "
        "run --site",
        args.site,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--site", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--sat", choices=["S2", "L8"], default="S2")
    parser.add_argument(
        "--batch",
        type=Path,
        default=(
            pipeline.ROOT
            / "configs/coastsat/shoreline_batch.json"
        ),
    )

    prepare(parser.parse_args(argv))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, FileNotFoundError, KeyError) as error:
        print("STOP:", error, file=sys.stderr)
        raise SystemExit(1)