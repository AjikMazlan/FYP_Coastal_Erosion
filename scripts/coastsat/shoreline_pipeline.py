"""Reusable CoastSat processing, monthly summaries and annual LR testing."""

from pathlib import Path
import argparse
import hashlib
import json
import math
import os
import pickle
import re
import sys

from pilot_site import load_config, run_coastsat

ROOT = Path(__file__).resolve().parents[2]
VERSION = "monthly_v1"

QC = dict(
    along_dist=25,
    min_points=3,
    max_std=15,
    max_range=40,
    min_chainage=0,
    multiple_inter="nan",
    auto_prc=0.1,
)


def path(value):
    value = Path(value)
    return value if value.is_absolute() else ROOT / value


def read_json(filename):
    return json.loads(
        Path(filename).read_text(encoding="utf-8-sig")
    )


def sha(filename):
    return hashlib.sha256(
        Path(filename).read_bytes()
    ).hexdigest()


def write_json(filename, value):
    filename = Path(filename)
    filename.parent.mkdir(parents=True, exist_ok=True)
    temporary = filename.with_suffix(filename.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(filename)


def write_csv(frame, filename):
    filename = Path(filename)
    filename.parent.mkdir(parents=True, exist_ok=True)
    temporary = filename.with_suffix(".tmp.csv")
    frame.to_csv(
        temporary,
        index=False,
        float_format="%.6f",
    )
    temporary.replace(filename)


def lines(filename, epsg):
    data = read_json(filename)
    crs = (
        data.get("crs", {})
        .get("properties", {})
        .get("name", "")
    )

    if not re.search(
        r"EPSG(?:::|:)" + str(epsg) + r"$",
        crs,
        re.I,
    ):
        raise ValueError(f"Wrong or missing CRS: {filename}")

    features = data.get("features", [])
    if not features:
        raise ValueError(f"No geometry: {filename}")

    for feature in features:
        geometry = feature["geometry"]
        coords = geometry["coordinates"]

        if (
            geometry["type"] != "LineString"
            or len(coords) < 2
            or any(len(p) != 2 for p in coords)
            or not all(
                math.isfinite(float(v))
                for p in coords
                for v in p
            )
        ):
            raise ValueError(f"Invalid LineString: {filename}")

    return features


def prepare_job(batch, site):
    years = batch["years"]

    if (
        len(years) < 6
        or any(type(y) is not int for y in years)
        or years != list(range(min(years), max(years) + 1))
    ):
        raise ValueError(
            "Use at least six consecutive years; "
            "the last is held out."
        )

    if not re.fullmatch(r"[a-z][a-z0-9_]*", site["id"]):
        raise ValueError("Invalid site ID.")

    if (
        not isinstance(site["name"], str)
        or not site["name"].strip()
    ):
        raise ValueError("Site name is required.")

    if not re.fullmatch(
        r"[A-Z][A-Z0-9_]*",
        site["input_prefix"],
    ):
        raise ValueError("Invalid input_prefix.")

    minimum = batch["min_months_per_year"]
    if type(minimum) is not int or not 1 <= minimum <= 12:
        raise ValueError("min_months_per_year must be 1..12.")

    if not 0 < float(batch["jump_flag_m"]) < 10000:
        raise ValueError("Invalid jump flag threshold.")

    base, polygon = load_config(path(site["base_config"]))
    epsg = base["output_epsg"]

    if epsg != 32648:
        raise ValueError(
            "This application's shoreline geometry "
            "uses EPSG:32648."
        )

    reference = lines(path(site["reference"]), epsg)
    if len(reference) != 1:
        raise ValueError(
            "Use one reference LineString per site."
        )

    transects = {}

    for feature in lines(path(site["transects"]), epsg):
        name = str(feature["properties"]["name"])

        if (
            not name.isdigit()
            or int(name) < 1
            or name != str(int(name))
            or name in transects
        ):
            raise ValueError(
                "Transect names must be unique positive integers."
            )

        coords = feature["geometry"]["coordinates"]

        if len(coords) != 2 or math.dist(*coords) < 1:
            raise ValueError(
                "Use fixed, straight, two-point transects."
            )

        transects[name] = coords

    return dict(
        batch=batch,
        site=site,
        base=base,
        polygon=polygon,
        reference=reference[0]["geometry"]["coordinates"],
        transects=transects,
        work=(
            ROOT / "results" / "shoreline_pipeline"
            / VERSION / site["id"]
        ),
    )


def year_paths(job, year):
    site = job["site"]
    folder = (
        path(job["batch"]["coastsat_root"])
        / "data"
        / f"{site['input_prefix']}_{year}"
    )
    cached = job["work"] / str(year) / "measurements.csv"
    imported = (
        site.get("existing_measurements", {})
        .get(str(year))
    )

    return (
        folder,
        cached,
        path(imported) if imported else None,
    )


def freeze_protocol(job):
    protocol = {
        "version": VERSION,
        "batch": {
            k: v
            for k, v in job["batch"].items()
            if k != "sites"
        },
        "site": job["site"],
        "base_config": job["base"],
        "intersection_qc": QC,
        "reference_sha256": sha(
            path(job["site"]["reference"])
        ),
        "transects_sha256": sha(
            path(job["site"]["transects"])
        ),
    }

    filename = job["work"] / "protocol.json"

    if filename.exists() and read_json(filename) != protocol:
        raise ValueError(
            "Protocol changed. Use a new site ID/input_prefix "
            "for the new run."
        )

    write_json(filename, protocol)


def process_year(job, year):
    import numpy as np
    import pandas as pd

    folder, cached, imported = year_paths(job, year)

    if imported:
        if not imported.is_file():
            raise FileNotFoundError(imported)
        print(f"{year}: reuse {imported}", flush=True)
        return

    if cached.exists():
        print(
            f"{year}: reuse pipeline measurements",
            flush=True,
        )
        return

    coast = path(job["batch"]["coastsat_root"]).resolve()

    if not (coast / "coastsat/SDS_download.py").is_file():
        raise FileNotFoundError(
            "Check coastsat_root in the batch JSON."
        )

    config = dict(
        job["base"],
        site_id=job["site"]["input_prefix"],
        sitename=folder.name,
        dates=[f"{year}-01-01", f"{year + 1}-01-01"],
    )

    raw_path = folder / f"{folder.name}_output.pkl"
    completed = cached.parent / "extraction_complete.json"

    if not raw_path.exists():
        run_coastsat(
            "download",
            config,
            job["polygon"],
            coast,
        )

    sys.path.insert(0, str(coast))

    import matplotlib
    matplotlib.use("Agg")

    from coastsat import (
        SDS_download,
        SDS_shoreline,
        SDS_transects,
    )

    if raw_path.exists() and not completed.exists():
        raise ValueError(
            f"Unfinished/unowned extraction: {raw_path}. "
            "Review or rename it before retrying."
        )

    if not raw_path.exists():
        points = np.asarray(job["reference"], dtype=float)
        distances = np.r_[
            0,
            np.cumsum(
                np.linalg.norm(
                    np.diff(points, axis=0),
                    axis=1,
                )
            ),
        ]

        if distances[-1] < 200:
            raise ValueError(
                "Reference shoreline must be at least 200 m."
            )

        samples = np.r_[
            np.arange(0, distances[-1], 1),
            distances[-1],
        ]
        reference = np.column_stack([
            np.interp(samples, distances, points[:, i])
            for i in (0, 1)
        ])

        inputs = dict(
            sitename=folder.name,
            filepath=str(coast / "data"),
            polygon=job["polygon"],
            dates=config["dates"],
            sat_list=config["sat_list"],
        )

        settings = dict(
            inputs=inputs,
            output_epsg=config["output_epsg"],
            reference_shoreline=reference,
            max_dist_ref=100,
            cloud_thresh=0.30,
            dist_clouds=300,
            check_detection=False,
            adjust_detection=False,
            save_figure=False,
            min_beach_area=1000,
            min_length_sl=200,
            cloud_mask_issue=False,
            sand_color="default",
            pan_off=False,
            s2cloudless_prob=40,
        )

        metadata = SDS_download.get_metadata(inputs)
        previous = Path.cwd()

        try:
            os.chdir(coast)
            SDS_shoreline.extract_shorelines(
                metadata,
                settings,
            )
        finally:
            os.chdir(previous)

        if not raw_path.is_file():
            raise FileNotFoundError(raw_path)

        write_json(
            completed,
            {"output_sha256": sha(raw_path)},
        )

    if (
        read_json(completed)["output_sha256"]
        != sha(raw_path)
    ):
        raise ValueError(
            "Extraction file changed after its completion marker."
        )

    with raw_path.open("rb") as stream:
        raw = pickle.load(stream)

    keep = [
        i
        for i, points in enumerate(raw["shorelines"])
        if len(points)
    ]

    if not keep:
        raise ValueError(
            f"{year}: no non-empty shorelines."
        )

    selected = {
        key: [raw[key][i] for i in keep]
        for key in ("dates", "shorelines")
    }
    transects = {
        key: np.asarray(value, dtype=float)
        for key, value in job["transects"].items()
    }

    intersections = SDS_transects.compute_intersection_QC(
        selected,
        transects,
        QC,
    )

    rows = []

    for name, values in intersections.items():
        length = float(
            np.linalg.norm(
                transects[name][1] - transects[name][0]
            )
        )

        for i, distance in enumerate(values):
            source = keep[i]
            valid = bool(
                np.isfinite(distance)
                and 0 <= distance <= length
            )

            rows.append(dict(
                Date=str(raw["dates"][source])[:10],
                Transect_ID=name,
                Satellite=raw["satname"][source],
                Source_File=raw["filename"][source],
                Cross_Shore_Distance_m=(
                    float(distance) if valid else np.nan
                ),
                Valid=valid,
                Tide_Corrected=False,
            ))

    write_csv(pd.DataFrame(rows), cached)


def read_year(job, year):
    import numpy as np
    import pandas as pd

    _, cached, imported = year_paths(job, year)
    source = imported or cached

    data = pd.read_csv(
        source,
        dtype={"Transect_ID": str},
    )

    needed = {
        "Date",
        "Transect_ID",
        "Satellite",
        "Source_File",
        "Cross_Shore_Distance_m",
        "Valid",
        "Tide_Corrected",
    }

    if not needed.issubset(data):
        raise ValueError(
            f"Missing columns in {source}: "
            f"{needed - set(data)}"
        )

    data["Date"] = pd.to_datetime(
        data["Date"],
        errors="raise",
        utc=True,
    ).dt.strftime("%Y-%m-%d")

    data = data.loc[
        data["Date"].str.startswith(f"{year}-")
    ].copy()

    if (
        data.empty
        or set(data["Transect_ID"])
        != set(job["transects"])
    ):
        raise ValueError(
            f"Missing year/transects in {source}"
        )

    if not (
        data["Tide_Corrected"]
        .astype(str)
        .str.lower()
        .eq("false")
        .all()
    ):
        raise ValueError(
            "Do not mix tide-corrected and "
            "uncorrected datasets."
        )

    if not set(data["Satellite"]).issubset(
        set(job["base"]["sat_list"])
    ):
        raise ValueError(
            "Unexpected sensor in measurements."
        )

    names = (
        data["Source_File"]
        .fillna("")
        .astype(str)
    )
    belongs = (
        names.str.contains(
            job["base"]["site_id"],
            regex=False,
        )
        | names.str.contains(
            job["site"]["input_prefix"],
            regex=False,
        )
    )

    if not belongs.all():
        raise ValueError(
            f"Source filenames do not match this site: {source}"
        )

    keys = ["Transect_ID", "Source_File"]
    data["Flagged"] = (
        data.get(
            "Review_Flag",
            pd.Series("", index=data.index),
        )
        .fillna("")
        .astype(str)
        .ne("")
    )

    duplicate = data.duplicated(keys, keep=False)

    if duplicate.any():
        for _, group in data.loc[duplicate].groupby(keys):
            unique = group.drop_duplicates([
                "Date",
                "Satellite",
                "Cross_Shore_Distance_m",
                "Valid",
            ])

            if len(unique) != 1:
                raise ValueError(
                    f"Conflicting repeated observations: {source}"
                )

        data["Flagged"] = (
            data.groupby(keys)["Flagged"]
            .transform("max")
        )
        data = data.drop_duplicates(keys)

    validity = (
        data["Valid"]
        .astype(str)
        .str.lower()
    )

    if not validity.isin(["true", "false"]).all():
        raise ValueError(
            "Valid must contain True/False."
        )

    data["Cross_Shore_Distance_m"] = pd.to_numeric(
        data["Cross_Shore_Distance_m"],
        errors="coerce",
    )

    limits = data["Transect_ID"].map({
        key: math.dist(*coords)
        for key, coords in job["transects"].items()
    })

    finite = np.isfinite(
        data["Cross_Shore_Distance_m"]
    )
    data["Valid"] = (
        validity.eq("true")
        & finite
        & data["Cross_Shore_Distance_m"].between(0, limits)
    )

    return data, {
        "year": year,
        "file": str(source),
        "sha256": sha(source),
        "rows": len(data),
        "valid_rows": int(data["Valid"].sum()),
    }


def build(job):
    import numpy as np
    import pandas as pd
    import joblib
    from sklearn.linear_model import LinearRegression

    write_json(
        job["work"] / "build_status.json",
        {"status": "building"},
    )

    years = job["batch"]["years"]
    frames, sources = [], []

    for year in years:
        frame, source = read_year(job, year)
        frames.append(frame)
        sources.append(source)

    raw = pd.concat(frames, ignore_index=True)
    write_csv(
        raw,
        job["work"] / "observations_QC.csv",
    )

    valid = raw.loc[raw["Valid"]].copy()

    if valid.empty:
        raise ValueError("No usable measurements.")

    daily = valid.groupby(
        ["Transect_ID", "Date"],
        as_index=False,
    ).agg(
        Median_m=("Cross_Shore_Distance_m", "median"),
        Flagged=("Flagged", "max"),
    )

    daily = daily.sort_values(
        ["Transect_ID", "Date"]
    ).reset_index(drop=True)

    changes = (
        daily.groupby("Transect_ID")["Median_m"]
        .diff()
        .abs()
    )

    daily["Large_Change_Flag"] = changes.gt(
        float(job["batch"]["jump_flag_m"])
    )
    daily["Flagged"] = (
        daily["Flagged"]
        | daily["Large_Change_Flag"]
    )
    daily["Year"] = daily["Date"].str[:4].astype(int)
    daily["Month"] = daily["Date"].str[5:7].astype(int)

    monthly = daily.groupby(
        ["Year", "Transect_ID", "Month"],
        as_index=False,
    ).agg(
        Median_m=("Median_m", "median"),
        Count_Days=("Date", "size"),
        Flagged_Days=("Flagged", "sum"),
    )

    annual = monthly.groupby(
        ["Year", "Transect_ID"],
        as_index=False,
    ).agg(
        Median_m=("Median_m", "median"),
        Months_Covered=("Month", "nunique"),
        Count_Days=("Count_Days", "sum"),
        Flagged_Days=("Flagged_Days", "sum"),
    )

    expected = pd.MultiIndex.from_product(
        [years, sorted(job["transects"])],
        names=["Year", "Transect_ID"],
    )
    annual = (
        annual.set_index(["Year", "Transect_ID"])
        .reindex(expected)
        .reset_index()
    )

    for column in [
        "Months_Covered",
        "Count_Days",
        "Flagged_Days",
    ]:
        annual[column] = (
            annual[column]
            .fillna(0)
            .astype(int)
        )

    annual["Use_For_Model"] = (
        annual["Median_m"].notna()
        & annual["Months_Covered"].ge(
            job["batch"]["min_months_per_year"]
        )
    )
    annual["QC_Status"] = "UNVALIDATED"
    annual["Tide_Corrected"] = False
    annual["Aggregation"] = "median_of_monthly_daily_medians"

    for frame, filename in [
        (daily, "daily.csv"),
        (monthly, "monthly.csv"),
        (annual, "annual_UNVALIDATED.csv"),
    ]:
        write_csv(frame, job["work"] / filename)

    write_json(
        job["work"] / "sources.json",
        sources,
    )

    if not annual["Use_For_Model"].all():
        blocked = annual.loc[
            ~annual["Use_For_Model"],
            ["Year", "Transect_ID", "Months_Covered"],
        ]
        raise ValueError(
            "Model blocked by missing/insufficient "
            "monthly coverage:\n"
            + blocked.to_string(index=False)
        )

    holdout_year = years[-1]
    reference_year = years[-2]

    models, references, tests, forecasts = {}, {}, [], []

    for name, group in annual.groupby("Transect_ID"):
        train = group.loc[
            group["Year"] < holdout_year
        ].sort_values("Year")

        target = group.loc[
            group["Year"] == holdout_year
        ].iloc[0]

        model = LinearRegression().fit(
            train[["Year"]],
            train["Median_m"],
        )

        reference = float(
            train.loc[
                train["Year"] == reference_year,
                "Median_m",
            ].iloc[0]
        )

        prediction = float(
            model.predict(
                pd.DataFrame({"Year": [holdout_year]})
            )[0]
        )

        models[int(name)] = model
        references[int(name)] = reference

        tests.append(dict(
            Transect_ID=int(name),
            Actual_m=float(target["Median_m"]),
            LR_m=prediction,
            Baseline_m=reference,
        ))

        for year in range(
            reference_year + 1,
            reference_year + 11,
        ):
            value = float(
                model.predict(
                    pd.DataFrame({"Year": [year]})
                )[0]
            )

            if not math.isfinite(value):
                raise ValueError(
                    "Non-finite prediction."
                )

            forecasts.append(dict(
                Transect_ID=int(name),
                Reference_Year=reference_year,
                Forecast_Year=year,
                Reference_Position_m=reference,
                Predicted_Position_m=value,
                Change_From_Reference_m=value - reference,
                QC_Status="UNVALIDATED",
                Tide_Corrected=False,
                Outside_Transect=not (
                    0 <= value
                    <= math.dist(*job["transects"][name])
                ),
            ))

    tests = pd.DataFrame(tests)
    scores = {}

    for label, column in [
        ("LinearRegression", "LR_m"),
        ("NoChangeBaseline", "Baseline_m"),
    ]:
        error = (
            tests[column].to_numpy()
            - tests["Actual_m"].to_numpy()
        )
        scores[label] = dict(
            N=len(error),
            MAE_m=float(np.abs(error).mean()),
            MSE_m2=float((error ** 2).mean()),
            RMSE_m=float(
                np.sqrt((error ** 2).mean())
            ),
        )

    worse = (
        scores["LinearRegression"]["MAE_m"]
        > scores["NoChangeBaseline"]["MAE_m"]
    )

    warning = (
        "Unvalidated observations; no tidal correction. "
        "Only a one-year holdout was evaluated; "
        "longer horizons are unvalidated."
    )

    if worse:
        warning += (
            " Linear Regression performed worse than "
            "the no-change baseline in the holdout test."
        )

    bundle = dict(
        site=job["site"]["name"],
        reference_year=reference_year,
        trained_through_year=reference_year,
        models=models,
        reference_positions_m=references,
        output_epsg=32648,
        axis_direction="unverified",
        target="shoreline_position_along_transect_m",
        model_status="Experimental",
        qc_status="UNVALIDATED",
        tide_corrected=False,
        quality_warning=warning,
        aggregation="median_of_monthly_daily_medians",
        training_start_year=years[0],
        training_rows=int(
            (annual["Year"] < holdout_year).sum()
        ),
        evaluation=dict(
            name=f"Holdout_{holdout_year}",
            scores=scores,
            lr_worse_than_baseline=worse,
        ),
    )

    model_path = job["work"] / "candidate_model.joblib"
    temporary = model_path.with_suffix(".tmp.joblib")

    joblib.dump(bundle, temporary)
    temporary.replace(model_path)

    geometry_path = job["work"] / "transects.geojson"

    write_json(
        geometry_path,
        read_json(path(job["site"]["transects"])),
    )
    write_json(
        job["work"] / "evaluation.json",
        bundle["evaluation"],
    )
    write_csv(
        tests,
        job["work"] / "holdout_predictions.csv",
    )
    write_csv(
        pd.DataFrame(forecasts),
        job["work"] / "forecasts_UNVALIDATED.csv",
    )

    write_json(
        job["work"] / "build_status.json",
        {
            "status": "ready",
            "model_sha256": sha(model_path),
            "reference_year": reference_year,
            "holdout_year": holdout_year,
            "qc_status": "UNVALIDATED",
            "sources": sources,
            "site_id": job["site"]["id"],
            "site": job["site"]["name"],
            "model": model_path.relative_to(ROOT).as_posix(),
            "geometry": geometry_path.relative_to(ROOT).as_posix(),
            "geometry_sha256": sha(geometry_path),
            "transect_ids": sorted(models),
        },
    )

    print(
        f"READY: {job['site']['name']} "
        f"| training through {reference_year} "
        f"| holdout {holdout_year}",
        flush=True,
    )
    print(json.dumps(scores, indent=2), flush=True)
    print("Model:", model_path, flush=True)
    print(
        "Restart Flask with the pipeline loader "
        "to list this experimental site.",
        flush=True,
    )

    return bundle


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__
    )
    parser.add_argument(
        "action",
        choices=["status", "run", "build"],
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=(
            ROOT / "configs/coastsat/shoreline_batch.json"
        ),
    )
    parser.add_argument("--site", nargs="+")

    args = parser.parse_args(argv)
    batch = read_json(path(args.config))
    sites = batch["sites"]
    ids = [site["id"] for site in sites]

    if (
        len(ids) != len(set(ids))
        or (
            args.site
            and not set(args.site).issubset(ids)
        )
    ):
        raise ValueError(
            "Duplicate or unknown site IDs."
        )

    jobs = [
        prepare_job(batch, site)
        for site in sites
        if not args.site or site["id"] in args.site
    ]

    if not jobs:
        raise ValueError("No sites selected.")

    failed = []

    for job in jobs:
        print(
            f"\n=== {job['site']['name']} ===",
            flush=True,
        )

        if args.action == "status":
            for year in batch["years"]:
                _, cached, imported = year_paths(job, year)
                available = imported or cached

                print(
                    year,
                    (
                        "CSV ready"
                        if available.is_file()
                        else "needs processing"
                    ),
                    available,
                    flush=True,
                )
            continue

        try:
            freeze_protocol(job)
            errors = []

            if args.action == "run":
                # Validate existing CSVs before network work.
                for year in batch["years"]:
                    _, cached, imported = year_paths(job, year)

                    if imported or cached.exists():
                        read_year(job, year)

                for year in batch["years"]:
                    try:
                        process_year(job, year)
                    except Exception as error:
                        errors.append(dict(
                            year=year,
                            error=str(error),
                        ))
                        print(
                            f"YEAR FAILED {year}: {error}",
                            flush=True,
                        )

                write_json(
                    job["work"] / "processing_errors.json",
                    errors,
                )

            if errors:
                raise ValueError(
                    "Some years failed. Rerun the same "
                    "command to reuse completed years."
                )

            if args.action == "build":
                build(job)
            else:
                print(
                    "PROCESSING COMPLETE. "
                    "Run build with the backend .venv "
                    "Python to export compatible models.",
                    flush=True,
                )

        except Exception as error:
            failed.append(job["site"]["id"])

            if args.action == "build":
                write_json(
                    job["work"] / "build_status.json",
                    {
                        "status": "blocked",
                        "error": str(error),
                    },
                )

            print(
                f"SITE BLOCKED: {error}",
                flush=True,
            )

    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        ValueError,
        FileNotFoundError,
        KeyError,
    ) as error:
        print("STOP:", error, file=sys.stderr)
        raise SystemExit(1)