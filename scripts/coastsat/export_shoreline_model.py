from pathlib import Path
import argparse
import json
import re

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression


ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--site", required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--transects", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--reference-year", type=int, default=2024)

    args = parser.parse_args()

    def project_path(path):
        return path if path.is_absolute() else ROOT / path

    # Read and validate annual observations.
    data = pd.read_csv(project_path(args.data))

    required = {
        "Year",
        "Transect_ID",
        "Median_m",
        "Tide_Corrected",
    }

    if not required.issubset(data.columns):
        raise ValueError(
            f"Missing columns: {required - set(data.columns)}"
        )

    if data[list(required)].isna().any().any():
        raise ValueError("Missing model inputs.")

    for column in ["Year", "Transect_ID"]:
        values = pd.to_numeric(data[column], errors="raise")

        if (
            not np.isfinite(values).all()
            or not values.mod(1).eq(0).all()
        ):
            raise ValueError(
                f"{column} must contain finite integers."
            )

        data[column] = values.astype(int)

    data["Median_m"] = pd.to_numeric(
        data["Median_m"],
        errors="raise",
    )

    if not np.isfinite(data["Median_m"]).all():
        raise ValueError("Non-finite shoreline positions.")

    if data.duplicated(["Year", "Transect_ID"]).any():
        raise ValueError("Duplicate transect-year records.")

    if not (
        data["Tide_Corrected"]
        .astype(str)
        .str.lower()
        .eq("false")
        .all()
    ):
        raise ValueError(
            "This export expects tide-uncorrected observations."
        )

    # Read the same transect geometry used for measurement.
    geometry_path = project_path(args.transects)

    geometry = json.loads(
        geometry_path.read_text(encoding="utf-8-sig")
    )

    crs = (
        geometry.get("crs", {})
        .get("properties", {})
        .get("name", "")
    )

    if not re.search(
        r"EPSG(?:::|:)32648$",
        crs,
        flags=re.IGNORECASE,
    ):
        raise ValueError(
            "Expected transect geometry in EPSG:32648."
        )

    lengths = {}

    for feature in geometry["features"]:
        transect_id = int(feature["properties"]["name"])

        coordinates = np.asarray(
            feature["geometry"]["coordinates"],
            dtype=float,
        )

        if (
            feature["geometry"]["type"] != "LineString"
            or coordinates.shape != (2, 2)
            or not np.isfinite(coordinates).all()
        ):
            raise ValueError(
                "Expected straight two-point transects."
            )

        if transect_id in lengths:
            raise ValueError("Duplicate geometry transect ID.")

        length = float(
            np.linalg.norm(coordinates[1] - coordinates[0])
        )

        if length <= 0:
            raise ValueError("Zero-length transect.")

        lengths[transect_id] = length

    # Keep observations after the reference year out of training.
    training = data[
        data["Year"] <= args.reference_year
    ].copy()

    if "Use_For_Model" in training.columns:
        training = training[
            training["Use_For_Model"].eq(1)
        ].copy()

    if set(training["Transect_ID"]) != set(lengths):
        raise ValueError(
            "Training and geometry transect IDs do not match."
        )

    # Read the existing holdout evaluation.
    metrics = pd.read_csv(project_path(args.evaluation))

    evaluation_name = f"Holdout_{args.reference_year + 1}"

    holdout = metrics[
        metrics["Evaluation"].eq(evaluation_name)
        & metrics["Horizon_Years"].eq(1)
    ]

    scores = {}

    for name in ["LinearRegression", "NoChangeBaseline"]:
        rows = holdout[holdout["Model"].eq(name)]

        if (
            len(rows) != 1
            or int(rows.iloc[0]["N"]) != len(lengths)
        ):
            raise ValueError(
                "Expected one holdout test per transect."
            )

        row = rows.iloc[0]

        scores[name] = {
            key: float(row[key])
            for key in ["MSE_m2", "MAE_m", "RMSE_m"]
        }

        if not all(
            np.isfinite(value)
            for value in scores[name].values()
        ):
            raise ValueError("Invalid evaluation metrics.")

    models = {}
    references = {}
    forecasts = []

    # Fit one Linear Regression model per transect.
    for transect_id, records in training.groupby("Transect_ID"):
        transect_id = int(transect_id)
        records = records.sort_values("Year")

        reference = records[
            records["Year"].eq(args.reference_year)
        ]

        if len(records) < 5 or len(reference) != 1:
            raise ValueError(
                f"T{transect_id}: insufficient training/reference data."
            )

        if not records["Median_m"].between(
            0,
            lengths[transect_id],
        ).all():
            raise ValueError(
                "Observed position lies outside its transect."
            )

        model = LinearRegression().fit(
            records[["Year"]],
            records["Median_m"],
        )

        reference_position = float(
            reference["Median_m"].iloc[0]
        )

        models[transect_id] = model
        references[transect_id] = reference_position

        for year in range(
            args.reference_year + 1,
            args.reference_year + 11,
        ):
            predicted = float(
                model.predict(
                    pd.DataFrame({"Year": [year]})
                )[0]
            )

            if not np.isfinite(predicted):
                raise ValueError("Non-finite forecast.")

            forecasts.append({
                "Transect_ID": transect_id,
                "Reference_Year": args.reference_year,
                "Reference_Position_m": reference_position,
                "Forecast_Year": year,
                "Predicted_Position_m": predicted,
                "Change_From_Reference_m": (
                    predicted - reference_position
                ),
                "Outside_Transect": not (
                    0 <= predicted <= lengths[transect_id]
                ),
                "QC_Status": "UNVALIDATED",
                "Tide_Corrected": False,
            })

    # Confirm these exported models reproduce the holdout metrics.
    holdout_data = data[
        data["Year"].eq(args.reference_year + 1)
    ]

    if (
        len(holdout_data) != len(models)
        or set(holdout_data["Transect_ID"]) != set(models)
    ):
        raise ValueError(
            "Holdout observations must match all model transects."
        )

    actual = []
    predicted = []
    baseline = []

    for _, row in holdout_data.iterrows():
        transect_id = int(row["Transect_ID"])

        actual.append(float(row["Median_m"]))

        predicted.append(
            float(
                models[transect_id].predict(
                    pd.DataFrame({
                        "Year": [args.reference_year + 1]
                    })
                )[0]
            )
        )

        baseline.append(references[transect_id])

    for name, values in [
        ("LinearRegression", predicted),
        ("NoChangeBaseline", baseline),
    ]:
        errors = np.asarray(values) - np.asarray(actual)

        fresh = {
            "MSE_m2": float(np.mean(errors ** 2)),
            "MAE_m": float(np.mean(np.abs(errors))),
            "RMSE_m": float(np.sqrt(np.mean(errors ** 2))),
        }

        if not all(
            np.isclose(
                fresh[key],
                scores[name][key],
                rtol=1e-6,
                atol=1e-6,
            )
            for key in fresh
        ):
            raise ValueError(
                "Evaluation metrics do not match this dataset/model."
            )

    worse = (
        scores["LinearRegression"]["MSE_m2"]
        > scores["NoChangeBaseline"]["MSE_m2"]
    )

    warning = "Unvalidated observations; no tidal correction."

    if worse:
        warning += (
            " Linear Regression performed worse than the "
            "no-change baseline in the holdout test."
        )

    bundle = {
        "site": args.site,
        "reference_year": args.reference_year,
        "trained_through_year": args.reference_year,
        "target": "shoreline_position_along_transect_m",
        "axis_direction": "unverified",
        "models": models,
        "reference_positions_m": references,
        "geometry_file": geometry_path.name,
        "output_epsg": 32648,
        "training_start_year": int(training["Year"].min()),
        "training_rows": len(training),
        "model_status": "Experimental",
        "qc_status": "UNVALIDATED",
        "tide_corrected": False,
        "quality_warning": warning,
        "evaluation": {
            "name": evaluation_name,
            "scores": scores,
            "lr_worse_than_baseline": worse,
        },
    }

    slug = re.sub(
        r"[^a-z0-9]+",
        "_",
        args.site.lower(),
    ).strip("_")

    model_path = (
        ROOT / "models" / f"{slug}_shoreline_lr.joblib"
    )

    forecast_path = (
        ROOT / "results"
        / f"{slug}_shoreline_forecasts_UNVALIDATED.csv"
    )

    model_path.parent.mkdir(parents=True, exist_ok=True)
    forecast_path.parent.mkdir(parents=True, exist_ok=True)

    joblib.dump(bundle, model_path)

    pd.DataFrame(forecasts).to_csv(
        forecast_path,
        index=False,
        float_format="%.4f",
    )

    print("Site:", args.site)
    print("Training rows:", len(training))
    print("Models saved:", len(models))
    print("Reference year:", args.reference_year)

    print(
        "Future observations excluded from training:",
        int((data["Year"] > args.reference_year).sum()),
    )

    print("Forecast records:", len(forecasts))
    print("WARNING:", warning)
    print("Model:", model_path)
    print("Forecasts:", forecast_path)


if __name__ == "__main__":
    main()