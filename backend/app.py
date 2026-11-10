from database import db, CoastalPoint, configure_database
from flask import Flask, jsonify, request
from pathlib import Path
from flask import send_from_directory
import pandas as pd
import joblib
import json
import math
from pyproj import Transformer

app = Flask(__name__)
configure_database(app)

# Main FYP folder
BASE_DIR = Path(__file__).resolve().parent.parent

# Existing files from our previous notebooks
DATA_PATH = BASE_DIR / "data" / "processed" / "coastal_app_locations.csv"

LR_MODEL_PATH = (
    BASE_DIR / "models" /
    "jps_multilocation_linear_regression.joblib"
)

# Load existing coastal dataset and model
lr_model = joblib.load(LR_MODEL_PATH)

# Shoreline prediction assets
# Shoreline prediction assets for each supported location
SHORELINE_SITES = {
    "kuala_merang": {
        "site": "Kuala Merang",
        "model": (
            BASE_DIR / "models"
            / "kuala_merang_shoreline_lr.joblib"
        ),
        "geometry": (
            BASE_DIR / "data" / "coastsat"
            / "KUALA_MERANG_2019_transects.geojson"
        ),
        "transect_ids": {1, 2, 3, 4},
    },
    "bukit_keluang": {
        "site": "Bukit Keluang",
        "model": (
            BASE_DIR / "models"
            / "bukit_keluang_shoreline_lr.joblib"
        ),
        "geometry": (
            BASE_DIR / "data" / "coastsat"
            / "BUKIT_KELUANG_transects_300m.geojson"
        ),
        "transect_ids": {1, 2, 3, 4, 5},
    },
}

shoreline_assets = {}
shoreline_load_errors = {}


def load_shoreline_site(config):
    bundle = joblib.load(config["model"])
    model_ids = set(bundle["models"])

    if (
        bundle["site"] != config["site"]
        or model_ids != config["transect_ids"]
    ):
        raise ValueError(
            "Model site or transect IDs do not match configuration."
        )

    reference_year = int(bundle["reference_year"])

    if not 1900 <= reference_year <= 2200:
        raise ValueError("Invalid reference year.")

    geometry = json.loads(
        config["geometry"].read_text(encoding="utf-8-sig")
    )

    crs = (
        geometry.get("crs", {})
        .get("properties", {})
        .get("name", "")
    )

    if crs not in (
        "EPSG:32648",
        "urn:ogc:def:crs:EPSG::32648",
    ):
        raise ValueError(
            "Transect geometry must use EPSG:32648."
        )

    transects = {}

    for feature in geometry["features"]:
        transect_id = int(feature["properties"]["name"])

        if transect_id not in model_ids:
            continue

        coords = feature["geometry"]["coordinates"]

        if (
            feature["geometry"]["type"] != "LineString"
            or len(coords) != 2
            or any(len(point) != 2 for point in coords)
            or not all(
                math.isfinite(float(value))
                for point in coords
                for value in point
            )
            or transect_id in transects
        ):
            raise ValueError(
                "Invalid or duplicate transect geometry."
            )

        coords = [
            [float(value) for value in point]
            for point in coords
        ]

        length = math.dist(coords[0], coords[-1])

        reference = float(
            bundle["reference_positions_m"][transect_id]
        )

        if (
            length <= 0
            or not math.isfinite(reference)
            or not 0 <= reference <= length
        ):
            raise ValueError(
                "Invalid transect length or reference position."
            )

        transects[transect_id] = coords

    if set(transects) != model_ids:
        raise ValueError(
            "Matching transect geometry is missing."
        )

    return {
        "bundle": bundle,
        "transects": transects,
    }


for site_id, config in SHORELINE_SITES.items():
    try:
        shoreline_assets[site_id] = load_shoreline_site(config)
        print(f"Shoreline ready: {config['site']}")

    except Exception as error:
        shoreline_load_errors[site_id] = str(error)

        app.logger.warning(
            "Shoreline unavailable: %s: %s",
            site_id,
            error,
        )

SHORELINE_IMAGERY_DIR = BASE_DIR / "data" / "coastsat" / "imagery"


def shoreline_imagery_info(site_id):
    metadata_path = SHORELINE_IMAGERY_DIR / f"{site_id}.json"
    image_path = SHORELINE_IMAGERY_DIR / f"{site_id}.png"

    if not metadata_path.is_file() or not image_path.is_file():
        return None

    try:
        metadata = json.loads(
            metadata_path.read_text(encoding="utf-8")
        )
        bounds = metadata["bounds"]

        south, west, north, east = [
            float(bounds[key])
            for key in ("south", "west", "north", "east")
        ]

        if (
            metadata["site_id"] != site_id
            or metadata["display_crs"] != "EPSG:3857"
            or not all(
                math.isfinite(value)
                for value in (south, west, north, east)
            )
            or not -90 <= south < north <= 90
            or not -180 <= west < east <= 180
        ):
            raise ValueError("Invalid satellite overlay metadata.")

        return {
            "image_url": (
                f"/shoreline-imagery/{site_id}.png"
                f"?v={metadata['version']}"
            ),
            "acquisition_date": metadata["acquisition_date"],
            "source": metadata["source"],
            "source_pixel_size": metadata.get("source_pixel_size"),
            "bounds": {
                "south": south,
                "west": west,
                "north": north,
                "east": east,
            },
            "note": metadata["note"],
        }

    except (KeyError, ValueError, TypeError, OSError) as error:
        app.logger.warning(
            "Satellite overlay unavailable for %s: %s",
            site_id,
            error,
        )
        return None


@app.route("/shoreline-imagery/<site_id>.png", methods=["GET"])
def shoreline_imagery(site_id):
    if (
        site_id not in SHORELINE_SITES
        or shoreline_imagery_info(site_id) is None
    ):
        return jsonify({"error": "Satellite image unavailable."}), 404

    return send_from_directory(
        str(SHORELINE_IMAGERY_DIR),
        f"{site_id}.png",
        mimetype="image/png",
        max_age=3600,
    )

def shoreline_site_info(site_id):
    bundle = shoreline_assets[site_id]["bundle"]
    reference_year = int(bundle["reference_year"])

    return {
        "site_id": site_id,
        "imagery": shoreline_imagery_info(site_id),
        "site": SHORELINE_SITES[site_id]["site"],
        "reference_year": reference_year,
        "first_forecast_year": reference_year + 1,
        "last_forecast_year": reference_year + 10,
        "transect_count": len(bundle["models"]),
        "model_status": bundle.get(
            "model_status",
            "Experimental",
        ),
        "qc_status": bundle.get(
            "qc_status",
            "UNVALIDATED",
        ),
        "tide_corrected": bundle.get(
            "tide_corrected",
            False,
        ),
        "quality_warning": bundle.get(
            "quality_warning",
            "Experimental forecast based on unvalidated, "
            "tide-uncorrected observations.",
        ),
        "evaluation": bundle.get("evaluation"),
    }


shoreline_transformer = Transformer.from_crs(
    "EPSG:32648",
    "EPSG:4326",
    always_xy=True,
)

print("=== COASTAL EROSION BACKEND ===")
print("Coastal data source: SQLite")
print("K-Means results: Loaded from database")
print("Linear Regression model: Loaded")


# API 1: Test backend connection
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
         "total_locations": db.session.scalar(
            db.select(db.func.count()).select_from(CoastalPoint)
        ),
        "kmeans_ready": True,
        "linear_regression_ready": True
    })


# API 2: Get K-Means and LR results
@app.route("/assessment", methods=["GET"])
def assessment():
    transect_id = request.args.get("transect_id", type=int)
    years = request.args.get("years", default=10, type=int)

    if transect_id is None or years is None:
        return jsonify({
            "error": "Valid transect_id and years required"
        }), 400

    if not 1 <= years <= 10:
        return jsonify({
            "error": "Years must be between 1 and 10"
        }), 400

    point = db.session.get(CoastalPoint, transect_id)

    if point is None:
        return jsonify({
            "error": "Location not found"
        }), 404

    row = {
        "Risk_Label": point.risk_label,
        "Projection_Source": point.projection_source,
        "Primary_Rate_m_yr": point.primary_rate_m_yr,
        "Source_Type": point.source_type,
        "Longitude_DD": point.longitude,
        "Latitude_DD": point.latitude,
        "Coastal_Cell": point.coastal_cell,
        "Area_Location": point.location,
    }

    # Previously generated K-Means classification
    risk = str(row["Risk_Label"])

    # Primary JPS / interpolation projection
    source = str(row["Projection_Source"])
    rate = row["Primary_Rate_m_yr"]

    primary_rate = None
    primary_retreat = None

    if pd.notna(rate) and float(rate) >= 0:
        primary_rate = round(float(rate), 4)
        primary_retreat = round(
            float(rate) * years, 2
        )

    # Linear Regression: experimental prediction
    lr_rate = None
    lr_retreat = None

    if (
        row["Source_Type"] == "Interpolated"
        and risk != "Protected"
    ):
        features = pd.DataFrame([{
            "Longitude_DD": row["Longitude_DD"],
            "Latitude_DD": row["Latitude_DD"],
            "Coastal_Cell": row["Coastal_Cell"]
        }])

        prediction = float(
            lr_model.predict(features)[0]
        )

        lr_rate = round(prediction, 4)

        if prediction >= 0:
            lr_retreat = round(
                prediction * years, 2
            )

    return jsonify({
        "transect_id": transect_id,
        "location": str(row["Area_Location"]),
        "coastal_cell": str(row["Coastal_Cell"]),
        "risk_label": risk,
        "source_type": str(row["Source_Type"]),
        "projection_source": source,
        "years_ahead": years,
        "primary_rate_m_yr": primary_rate,
        "primary_retreat_m": primary_retreat,
        "lr_experimental_rate_m_yr": lr_rate,
        "lr_experimental_retreat_m": lr_retreat
    })

# API 3: Coastal locations for map markers
@app.route("/locations", methods=["GET"])
def locations():
    coastal_points = db.session.scalars(
        db.select(CoastalPoint).order_by(CoastalPoint.point_id)
    ).all()

    locations_data = [
        {
            "transect_id": point.point_id,
            "location": point.location,
            "district": point.district,
            "coastal_cell": point.coastal_cell,
            "latitude": point.latitude,
            "longitude": point.longitude,
            "risk_label": point.risk_label,
            "source_type": point.source_type,
            "projection_source": point.projection_source,
            "primary_rate_m_yr": point.primary_rate_m_yr,
        }
        for point in coastal_points
    ]

    return jsonify({
        "total_locations": len(locations_data),
        "locations": locations_data
    })

# Convert a distance along a transect into map coordinates
def shoreline_map_point(coords, position_m):
    x0, y0 = coords[0]
    x1, y1 = coords[-1]

    length = math.hypot(x1 - x0, y1 - y0)
    fraction = position_m / length

    x = x0 + fraction * (x1 - x0)
    y = y0 + fraction * (y1 - y0)

    longitude, latitude = (
        shoreline_transformer.transform(x, y)
    )

    return {
        "latitude": round(latitude, 8),
        "longitude": round(longitude, 8),
        "outside_transect": not (
            0 <= position_m <= length
        )
    }


# API 4: Available shoreline prediction locations
@app.route("/shoreline-sites", methods=["GET"])
def shoreline_sites():
    sites = [
        shoreline_site_info(site_id)
        for site_id in SHORELINE_SITES
        if site_id in shoreline_assets
    ]

    unavailable = [
        {
            "site_id": site_id,
            "site": SHORELINE_SITES[site_id]["site"],
            "reason": (
                "Model or geometry unavailable. "
                "Check Flask startup output."
            ),
        }
        for site_id in shoreline_load_errors
    ]

    return jsonify({
        "total_sites": len(sites),
        "sites": sites,
        "unavailable_sites": unavailable,
    })


# API 5: Temporal shoreline prediction for the selected location
@app.route("/shoreline-prediction", methods=["GET"])
def shoreline_prediction():
    site_id = (
        request.args.get("site", "kuala_merang")
        .strip()
        .lower()
        .replace(" ", "_")
    )

    if site_id not in SHORELINE_SITES:
        return jsonify({
            "error": "Unknown shoreline location."
        }), 400

    if site_id not in shoreline_assets:
        return jsonify({
            "error": (
                "The model or geometry for this "
                "location is unavailable."
            )
        }), 503

    asset = shoreline_assets[site_id]
    bundle = asset["bundle"]
    info = shoreline_site_info(site_id)

    first_year = info["first_forecast_year"]
    last_year = info["last_forecast_year"]

    error_message = (
        f"Year must be between {first_year} and {last_year}"
    )

    try:
        forecast_year = int(
            request.args.get("year", str(first_year))
        )
    except (TypeError, ValueError):
        return jsonify({
            "error": error_message
        }), 400

    if not first_year <= forecast_year <= last_year:
        return jsonify({
            "error": error_message
        }), 400

    results = []

    try:
        for transect_id in sorted(bundle["models"]):
            reference = float(
                bundle["reference_positions_m"][transect_id]
            )

            predicted = float(
                bundle["models"][transect_id].predict(
                    pd.DataFrame({
                        "Year": [forecast_year]
                    })
                )[0]
            )

            if not math.isfinite(predicted):
                raise ValueError(
                    "Non-finite predicted position."
                )

            coords = asset["transects"][transect_id]

            results.append({
                "transect_id": int(transect_id),
                "reference_position_m": round(reference, 4),
                "predicted_position_m": round(predicted, 4),
                "change_from_reference_m": round(
                    predicted - reference,
                    4,
                ),
                "reference_point": shoreline_map_point(
                    coords,
                    reference,
                ),
                "predicted_point": shoreline_map_point(
                    coords,
                    predicted,
                ),
            })

    except Exception:
        app.logger.exception(
            "Shoreline prediction failed for %s",
            site_id,
        )

        return jsonify({
            "error": "Unable to generate this forecast."
        }), 503

    return jsonify({
        **info,
        "forecast_year": forecast_year,
        "years_ahead": (
            forecast_year - info["reference_year"]
        ),
        "transects": results,
    })

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )
