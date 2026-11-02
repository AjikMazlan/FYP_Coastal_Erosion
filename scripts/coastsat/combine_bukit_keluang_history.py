from pathlib import Path
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
COASTSAT_DATA = Path(r"D:\CoastSat-master\data")
OUTPUT_DIR = PROJECT_ROOT / "data" / "coastsat"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

years = list(range(2013, 2026))
combined = {}

for kind in ["annual_summary", "measurements"]:
    frames = []

    for year in years:
        sitename = f"BUKIT_KELUANG_{year}"
        path = COASTSAT_DATA / sitename / f"{sitename}_{kind}.csv"

        if not path.exists():
            raise FileNotFoundError(f"Missing file: {path}")

        frame = pd.read_csv(
            path,
            dtype={"Transect_ID": "string"},
        )

        if frame.empty:
            raise ValueError(f"Empty file: {path}")

        if kind == "annual_summary":
            actual_years = pd.to_numeric(
                frame["Year"], errors="raise"
            )
        else:
            actual_years = pd.to_datetime(
                frame["Date"], errors="raise"
            ).dt.year

        if not actual_years.eq(year).all():
            raise ValueError(f"Unexpected year in: {path}")

        frame["Source_Sitename"] = sitename
        frames.append(frame)

    result = pd.concat(frames, ignore_index=True)

    if kind == "annual_summary":
        if result.duplicated(["Year", "Transect_ID"]).any():
            raise ValueError("Duplicate annual transect records.")

        result = result.sort_values(["Year", "Transect_ID"])
    else:
        result = result.sort_values(["Date", "Transect_ID"])

    output_path = OUTPUT_DIR / (
        f"BUKIT_KELUANG_{kind}_2013_2025_UNVALIDATED.csv"
    )
    result.to_csv(output_path, index=False, float_format="%.3f")

    combined[kind] = result
    print(f"Saved {len(result)} rows: {output_path}")

annual = combined["annual_summary"]

print("\nObservation days per year and transect:")
print(
    annual.pivot(
        index="Year",
        columns="Transect_ID",
        values="Count_Days",
    ).to_string()
)

expected = pd.MultiIndex.from_product(
    [years, ["1", "2", "3", "4", "5"]],
    names=["Year", "Transect_ID"],
)
available = pd.MultiIndex.from_frame(
    annual[["Year", "Transect_ID"]]
)
missing = expected.difference(available)

print("\nMissing annual records:", list(missing))
print("\nCombined data is ready for review, not yet model training.")