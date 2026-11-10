from pathlib import Path
from datetime import date
import argparse
import hashlib
import json
import re

import numpy as np
from osgeo import gdal, osr
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--date", required=True)
    args = parser.parse_args()

    if not re.fullmatch(r"[a-z0-9_]+", args.site):
        raise ValueError(
            "Use a site ID such as bukit_keluang."
        )

    acquisition_date = date.fromisoformat(args.date).isoformat()

    source = (
        args.image
        if args.image.is_absolute()
        else ROOT / args.image
    )

    if (
        "S2" not in source.name
        or not source.name.startswith(acquisition_date)
    ):
        raise ValueError(
            "Expected a CoastSat S2 ms GeoTIFF matching the date."
        )

    gdal.UseExceptions()

    src = gdal.Open(str(source), gdal.GA_ReadOnly)

    if (
        src is None
        or src.RasterCount < 3
        or not src.GetProjection()
    ):
        raise ValueError(
            "The GeoTIFF needs a CRS and at least three bands."
        )

    source_srs = osr.SpatialReference()
    source_srs.ImportFromWkt(src.GetProjection())

    code = source_srs.GetAuthorityCode(None)
    authority = source_srs.GetAuthorityName(None)

    source_crs = (
        f"{authority}:{code}"
        if authority and code
        else source_srs.ExportToWkt()
    )

    original_transform = src.GetGeoTransform()

    native_resolution = [
        abs(original_transform[1]),
        abs(original_transform[5]),
    ]

    # CoastSat Sentinel-2 RGB: bands 3, 2, 1.
    rgb = gdal.Translate(
        "",
        src,
        format="MEM",
        bandList=[3, 2, 1],
        outputType=gdal.GDT_Float32,
    )

    # Match the Web Mercator projection used by the map.
    warped = gdal.Warp(
        "",
        rgb,
        format="MEM",
        dstSRS="EPSG:3857",
        outputType=gdal.GDT_Float32,
        resampleAlg="near",
        srcAlpha=False,
        dstAlpha=True,
        srcNodata=0,
        dstNodata=0,
        warpOptions=["UNIFIED_SRC_NODATA=YES"],
    )

    if warped is None or warped.RasterCount != 4:
        raise ValueError(
            "Could not prepare the satellite image."
        )

    array = warped.ReadAsArray().astype("float32")

    visible = (
        (array[3] > 0)
        & np.all(np.isfinite(array[:3]), axis=0)
    )

    if not visible.any():
        raise ValueError("No valid image pixels.")

    height, width = visible.shape

    rgba = np.zeros(
        (height, width, 4),
        dtype="uint8",
    )

    # Stretch RGB contrast for display.
    for band in range(3):
        low, high = np.percentile(
            array[band][visible],
            [2, 98],
        )

        if high <= low:
            raise ValueError(
                "Insufficient image contrast."
            )

        stretched = np.clip(
            (array[band] - low) / (high - low),
            0,
            1,
        )

        rgba[:, :, band] = (
            np.nan_to_num(stretched) * 255
        ).astype("uint8")

    # Make no-data areas transparent.
    rgba[:, :, 3] = visible.astype("uint8") * 255

    transform = warped.GetGeoTransform()

    if (
        abs(transform[2]) > 1e-10
        or abs(transform[4]) > 1e-10
    ):
        raise ValueError(
            "Expected a north-up display image."
        )

    left = transform[0]
    top = transform[3]
    right = left + width * transform[1]
    bottom = top + height * transform[5]

    mercator = osr.SpatialReference()
    mercator.ImportFromEPSG(3857)

    geographic = osr.SpatialReference()
    geographic.ImportFromEPSG(4326)

    # Keep longitude/latitude axis order explicit.
    for srs in (mercator, geographic):
        srs.SetAxisMappingStrategy(
            osr.OAMS_TRADITIONAL_GIS_ORDER
        )

    converter = osr.CoordinateTransformation(
        mercator,
        geographic,
    )

    west, south, _ = converter.TransformPoint(left, bottom)
    east, north, _ = converter.TransformPoint(right, top)

    if not all(
        np.isfinite(value)
        for value in (west, south, east, north)
    ):
        raise ValueError("Invalid image bounds.")

    warped = None
    rgb = None
    src = None

    output = ROOT / "data" / "coastsat" / "imagery"
    output.mkdir(parents=True, exist_ok=True)

    image_path = output / f"{args.site}.png"
    metadata_path = output / f"{args.site}.json"

    Image.fromarray(rgba).save(image_path)

    version = hashlib.sha256(
        image_path.read_bytes()
    ).hexdigest()[:16]

    metadata = {
        "site_id": args.site,
        "acquisition_date": acquisition_date,
        "source": (
            "Copernicus Sentinel-2 / ESA; "
            "processed with CoastSat"
        ),
        "source_file": source.name,
        "source_crs": source_crs,
        "source_pixel_size": native_resolution,
        "display_crs": "EPSG:3857",
        "bounds": {
            "south": south,
            "west": west,
            "north": north,
            "east": east,
        },
        "version": version,
        "note": (
            "Historical image for visual context; "
            "not a live shoreline or independent validation."
        ),
    }

    metadata_path.write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    print("Site:", args.site)
    print("Image date:", acquisition_date)
    print("Source CRS:", source_crs)
    print("Display CRS: EPSG:3857")
    print("PNG:", image_path)
    print("Metadata:", metadata_path)
    print("Image preparation completed.")


if __name__ == "__main__":
    main()