from pathlib import Path
import argparse

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

parser = argparse.ArgumentParser()
parser.add_argument(
    "--data",
    type=Path,
    default=(
        PROJECT_ROOT / "data" / "coastsat"
        / "BUKIT_KELUANG_annual_summary_2013_2025_UNVALIDATED.csv"
    ),
)
parser.add_argument(
    "--out",
    type=Path,
    default=PROJECT_ROOT / "results" / "bukit_keluang_lr_evaluation",
)
args = parser.parse_args()

MIN_TRAIN_YEARS = 5
HORIZONS = range(1, 11)


def scores(actual, predicted):
    if len(actual) == 0:
        return {
            "N": 0,
            "MSE_m2": np.nan,
            "MAE_m": np.nan,
            "RMSE_m": np.nan,
            "R2": np.nan,
        }

    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)

    mse = mean_squared_error(actual, predicted)
    r2 = np.nan

    if len(actual) >= 2 and np.ptp(actual) > 0:
        r2 = r2_score(actual, predicted)

    return {
        "N": len(actual),
        "MSE_m2": mse,
        "MAE_m": mean_absolute_error(actual, predicted),
        "RMSE_m": np.sqrt(mse),
        "R2": r2,
    }


def forecast(train, target, evaluation):
    train = train.sort_values("Year")

    model = LinearRegression()
    model.fit(train[["Year"]], train["Median_m"])

    predicted = float(
        model.predict(
            pd.DataFrame({"Year": [int(target["Year"])]})
        )[0]
    )
    last = train.iloc[-1]

    return {
        "Evaluation": evaluation,
        "Transect_ID": str(target["Transect_ID"]),
        "Train_Start": int(train["Year"].min()),
        "Train_End": int(last["Year"]),
        "N_Train_Years": len(train),
        "Target_Year": int(target["Year"]),
        "Horizon_Years": int(target["Year"] - last["Year"]),
        "Actual_m": float(target["Median_m"]),
        "LR_m": predicted,
        "Baseline_m": float(last["Median_m"]),
        "LR_Outside_Transect": not 0 <= predicted <= 300,
        "Tide_Corrected": False,
    }


data = pd.read_csv(args.data, dtype={"Transect_ID": "string"})

required = {"Year", "Transect_ID", "Median_m", "Tide_Corrected"}

if not required.issubset(data.columns):
    raise ValueError(f"Missing columns: {required - set(data.columns)}")

if data.duplicated(["Year", "Transect_ID"]).any():
    raise ValueError("Duplicate transect-year records.")

if data[list(required)].isna().any().any():
    raise ValueError("Missing required values.")

if not np.isfinite(data[["Year", "Median_m"]].to_numpy(float)).all():
    raise ValueError("Non-finite year or shoreline position.")

if not data["Tide_Corrected"].eq(False).all():
    raise ValueError("This protocol expects the uncorrected dataset only.")

if set(data["Year"].unique()) != set(range(2013, 2026)):
    raise ValueError("Expected annual data from 2013 through 2025.")

history = data[data["Year"] <= 2024]
records = []

# Historical evaluation: use only information available before each target.
for transect_id, group in history.groupby("Transect_ID"):
    for horizon in HORIZONS:
        for _, target in group.sort_values("Year").iterrows():
            cutoff = int(target["Year"]) - horizon
            train = group[group["Year"] <= cutoff]

            if len(train) < MIN_TRAIN_YEARS:
                continue

            if int(train["Year"].max()) != cutoff:
                continue

            records.append(
                forecast(train, target, "WalkForward_to_2024")
            )

# Separate test: train through 2024 and predict 2025.
for _, target in data[data["Year"] == 2025].iterrows():
    train = history[
        history["Transect_ID"] == target["Transect_ID"]
    ]

    if len(train) < MIN_TRAIN_YEARS:
        raise ValueError(
            f"Insufficient history for T{target['Transect_ID']}."
        )

    records.append(forecast(train, target, "Holdout_2025"))

predictions = pd.DataFrame(records)

overall_rows = []
transect_rows = []

for evaluation, horizons in [
    ("WalkForward_to_2024", HORIZONS),
    ("Holdout_2025", [1]),
]:
    for horizon in horizons:
        cases = predictions[
            predictions["Evaluation"].eq(evaluation)
            & predictions["Horizon_Years"].eq(horizon)
        ]

        for name, column in [
            ("LinearRegression", "LR_m"),
            ("NoChangeBaseline", "Baseline_m"),
        ]:
            result = scores(cases["Actual_m"], cases[column])
            result["R2_Pooled"] = result.pop("R2")

            overall_rows.append({
                "Evaluation": evaluation,
                "Horizon_Years": horizon,
                "Model": name,
                **result,
            })

            for transect_id, subset in cases.groupby("Transect_ID"):
                transect_rows.append({
                    "Evaluation": evaluation,
                    "Horizon_Years": horizon,
                    "Transect_ID": transect_id,
                    "Model": name,
                    **scores(subset["Actual_m"], subset[column]),
                })

overall = pd.DataFrame(overall_rows)
per_transect = pd.DataFrame(transect_rows)

args.out.mkdir(parents=True, exist_ok=True)

predictions.to_csv(args.out / "predictions.csv", index=False)
overall.to_csv(args.out / "metrics_overall.csv", index=False)
per_transect.to_csv(
    args.out / "metrics_per_transect.csv",
    index=False,
)

print("\nOVERALL EVALUATION:")
print(overall.round(4).to_string(index=False))

print("\nPER-TRANSECT ONE-YEAR WALK-FORWARD:")
print(
    per_transect[
        per_transect["Evaluation"].eq("WalkForward_to_2024")
        & per_transect["Horizon_Years"].eq(1)
    ].round(4).to_string(index=False)
)

print("\nN=0: no eligible tests; not zero error.")
print("R2_Pooled combines transects; also inspect per-transect R2.")
print("One 2025 observation per transect cannot define per-transect R2.")
print("Results use uncorrected annual medians. 2013 remains included.")
print("Saved evaluation files:", args.out)