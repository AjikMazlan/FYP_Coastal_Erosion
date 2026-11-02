from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
COASTSAT_ROOT = Path(r"D:\CoastSat-master")

# 2024 has already been processed.
YEARS = list(range(2013, 2024)) + [2025]

for year in YEARS:
    sitename = f"BUKIT_KELUANG_{year}"
    folder = COASTSAT_ROOT / "data" / sitename
    config = PROJECT_ROOT / "configs" / "coastsat" / (
        f"bukit_keluang_{year}.json"
    )

    output_path = folder / f"{sitename}_output.pkl"
    completed = folder / "extraction_completed.flag"

    print(f"\n===== PROCESSING {year} =====", flush=True)

    if completed.exists() and not output_path.exists():
        raise FileNotFoundError(
            f"Completion marker exists but output is missing: {folder}"
        )

    if not completed.exists():
        if output_path.exists():
            raise RuntimeError(
                f"Existing output needs review before continuing: "
                f"{output_path}"
            )

        subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / "scripts" / "coastsat"
                    / "extract_bukit_keluang.py"),
                "--config", str(config),
            ],
            cwd=PROJECT_ROOT,
            check=True,
        )

        if not output_path.exists():
            raise FileNotFoundError(
                f"Extraction did not create {output_path}"
            )

        completed.write_text(
            "Extraction finished successfully.\n",
            encoding="utf-8",
        )
    else:
        print("Extraction already completed; using saved output.")

    subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "coastsat"
                / "measure_bukit_keluang.py"),
            "--config", str(config),
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )

    print(f"===== YEAR {year} COMPLETED =====", flush=True)

print("\nAll historical extraction and measurement steps completed.")