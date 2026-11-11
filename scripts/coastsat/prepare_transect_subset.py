"""Prepare a documented coverage subset without rerunning CoastSat."""

import argparse
import copy
import re

import shoreline_pipeline as p


def prepare(site_id, new_id, keep, name):
    keep = set(map(str, keep))

    if len(keep) < 3 or not all(
        t.isdigit() and int(t) > 0 for t in keep
    ):
        raise ValueError(
            "Keep at least three distinct positive transect IDs."
        )

    if (
        not re.fullmatch(r"[a-z][a-z0-9_]*", new_id)
        or not name.strip()
    ):
        raise ValueError(
            "Use a valid new site ID and a non-empty name."
        )

    config = p.ROOT / "configs/coastsat/shoreline_batch.json"
    batch = p.read_json(config)

    if any(s["id"] == new_id for s in batch["sites"]):
        print("Site already registered. Run its build command.")
        return

    matches = [
        s for s in batch["sites"] if s["id"] == site_id
    ]

    if len(matches) != 1:
        raise ValueError("Expected exactly one parent site.")

    old = matches[0]
    job = p.prepare_job(batch, old)
    all_ids = set(job["transects"])

    if not keep < all_ids:
        raise ValueError(
            "Keep must be a smaller subset of the parent transects."
        )

    minimum = batch["min_months_per_year"]
    frames, sources, coverage = {}, [], []

    for year in batch["years"]:
        frame, info = p.read_year(job, year)

        good = frame.loc[frame["Valid"]].copy()
        good["Month"] = good["Date"].str[5:7]

        counts = (
            good.groupby("Transect_ID")["Month"]
            .nunique()
            .to_dict()
        )

        for transect in sorted(all_ids, key=int):
            months = int(counts.get(transect, 0))

            coverage.append({
                "Year": year,
                "Transect_ID": transect,
                "Months_Covered": months,
            })

            if transect in keep and months < minimum:
                raise ValueError(
                    f"{year} T{transect}: "
                    f"only {months} covered months."
                )

        frames[year] = frame.loc[
            frame["Transect_ID"].isin(keep)
        ].copy()

        sources.append(info)

    excluded = all_ids - keep

    for transect in excluded:
        has_missing_coverage = any(
            row["Transect_ID"] == transect
            and row["Months_Covered"] < minimum
            for row in coverage
        )

        if not has_missing_coverage:
            raise ValueError(
                f"T{transect} has complete coverage; "
                "exclusion is not justified by this rule."
            )

    directory = p.ROOT / "data/coastsat" / new_id

    if directory.exists():
        raise ValueError(
            "Subset folder already exists without registration; "
            "inspect it first."
        )

    geometry = copy.deepcopy(
        p.read_json(p.path(old["transects"]))
    )

    geometry["features"] = [
        feature
        for feature in geometry["features"]
        if str(feature["properties"]["name"]) in keep
    ]

    geometry_path = directory / "transects_300m.geojson"
    p.write_json(geometry_path, geometry)

    imports = {}

    for year, frame in frames.items():
        filename = directory / f"measurements_{year}.csv"
        p.write_csv(frame, filename)

        imports[str(year)] = filename.relative_to(
            p.ROOT
        ).as_posix()

    reason = (
        f"Excluded transects fail the existing {minimum}-month "
        "coverage rule in at least one required year. "
        "Selection uses coverage, not prediction error."
    )

    site = copy.deepcopy(old)

    site.update(
        id=new_id,
        name=name,
        transects=geometry_path.relative_to(p.ROOT).as_posix(),
        existing_measurements=imports,
        subset_reason=reason,
    )

    new_job = p.prepare_job(batch, site)

    for year in batch["years"]:
        p.read_year(new_job, year)

    p.write_json(
        directory / "subset_record.json",
        {
            "parent_site": site_id,
            "kept_transects": sorted(keep, key=int),
            "excluded_transects": sorted(excluded, key=int),
            "reason": reason,
            "min_months_per_year": minimum,
            "parent_coverage": coverage,
            "source_measurements": sources,
            "source_geometry_sha256": p.sha(
                p.path(old["transects"])
            ),
            "scope_note": (
                "Spatial coverage is limited to retained transects. "
                "The original site remains available for review."
            ),
        },
    )

    batch["sites"].append(site)
    p.write_json(config, batch)

    print(
        "SUBSET READY:",
        new_id,
        "| transects:",
        ", ".join(sorted(keep, key=int)),
    )
    print(
        "Original files preserved. "
        "No download or extraction required."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument("--site", required=True)
    parser.add_argument("--new-id", required=True)
    parser.add_argument("--keep", nargs="+", required=True)
    parser.add_argument("--name", required=True)

    args = parser.parse_args()

    try:
        prepare(
            args.site,
            args.new_id,
            args.keep,
            args.name,
        )
    except (ValueError, FileNotFoundError, KeyError) as error:
        parser.exit(1, f"STOP: {error}\n")