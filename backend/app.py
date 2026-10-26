
from flask import Flask, jsonify, request
from pathlib import Path
import pandas as pd
import joblib
import json
import math
from pyproj import Transformer

app = Flask(__name__)

# Main FYP folder
BASE_DIR = Path(__file__).resolve().parent.parent

# Existing files from our previous notebooks
DATA_PATH = BASE_DIR / "data" / "processed" / "coastal_app_locations.csv"

LR_MODEL_PATH = (
    BASE_DIR / "models" /
    "jps_multilocation_linear_regression.joblib"
)

# Load existing coastal dataset and model
points = pd.read_csv(DATA_PATH)
lr_model = joblib.load(LR_MODEL_PATH)

# Shoreline prediction assets
SHORELINE_MODEL_PATH = (
    BASE_DIR / "models" /
    "kuala_merang_shoreline_lr.joblib"
)

SHORELINE_GEOMETRY_PATH = (
    BASE_DIR / "data" / "coastsat" /
    "KUALA_MERANG_2019_transects.geojson"
)

shoreline_bundle = (
    joblib.load(SHORELINE_MODEL_PATH)
    if SHORELINE_MODEL_PATH.exists()
    else None
)

shoreline_transects = {}

if SHORELINE_GEOMETRY_PATH.exists():
    shoreline_geo = json.loads(
        SHORELINE_GEOMETRY_PATH.read_text(
            encoding="utf-8-sig"
        )
    )

    for feature in shoreline_geo["features"]:
        transect_id = int(
            feature["properties"]["name"]
        )

        if transect_id in (1, 2, 3, 4):
            shoreline_transects[transect_id] = (
                feature["geometry"]["coordinates"]
            )

shoreline_transformer = Transformer.from_crs(
    "EPSG:32648",
    "EPSG:4326",
    always_xy=True
)

print("=== COASTAL EROSION BACKEND ===")
print("Coastal points:", len(points))
print("K-Means results: Loaded from CSV")
print("Linear Regression model: Loaded")


# API 1: Test backend connection
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "total_locations": len(points),
        "kmeans_ready": True,
        "linear_regression_ready": True
    })


# API 2: Get K-Means and LR results
@app.route("/assessment", methods=["GET"])
def assessment():

    transect_id = request.args.get(
        "transect_id", type=int
    )

    years = request.args.get(
        "years", default=10, type=int
    )

    if transect_id is None or years is None:
        return jsonify({
            "error": "Valid transect_id and years required"
        }), 400

    if not 1 <= years <= 10:
        return jsonify({
            "error": "Years must be between 1 and 10"
        }), 400

    selected = points[
        points["Transect_ID"] == transect_id
    ]

    if selected.empty:
        return jsonify({
            "error": "Location not found"
        }), 404

    row = selected.iloc[0]

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
    locations_data = []

    for row in points.itertuples(index=False):
        rate = row.Primary_Rate_m_yr

        locations_data.append({
            "transect_id": int(row.Transect_ID),
            "location": str(row.Area_Location),
            "district": str(row.District),
            "coastal_cell": str(row.Coastal_Cell),
            "latitude": float(row.Latitude_DD),
            "longitude": float(row.Longitude_DD),
            "risk_label": str(row.Risk_Label),
            "source_type": str(row.Source_Type),
            "projection_source": str(row.Projection_Source),
            "primary_rate_m_yr": (
                float(rate) if pd.notna(rate) else None
            )
        })

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


# API 4: Temporal shoreline prediction for Kuala Merang
@app.route("/shoreline-prediction", methods=["GET"])
def shoreline_prediction():

    if shoreline_bundle is None:
        return jsonify({
            "error": (
                "Export the shoreline model "
                "in Notebook 09 Step 9 first"
            )
        }), 503

    reference_year = int(
        shoreline_bundle["reference_year"]
    )

    first_year = reference_year + 1
    last_year = reference_year + 10

    error_message = (
        f"Year must be between "
        f"{first_year} and {last_year}"
    )

    try:
        forecast_year = int(
            request.args.get(
                "year",
                str(first_year)
            )
        )
    except (TypeError, ValueError):
        return jsonify({
            "error": error_message
        }), 400

    if not first_year <= forecast_year <= last_year:
        return jsonify({
            "error": error_message
        }), 400

    model_ids = set(
        shoreline_bundle["models"]
    )

    if (
        not model_ids
        or not model_ids.issubset(shoreline_transects)
    ):
        return jsonify({
            "error": (
                "Matching shoreline transect "
                "geometry is missing"
            )
        }), 503

    results = []

    for transect_id in sorted(model_ids):

        model = shoreline_bundle[
            "models"
        ][transect_id]

        reference = float(
            shoreline_bundle[
                "reference_positions_m"
            ][transect_id]
        )

        predicted = float(
            model.predict(
                pd.DataFrame({
                    "Year": [forecast_year]
                })
            )[0]
        )

        coords = shoreline_transects[transect_id]

        results.append({
            "transect_id": int(transect_id),
            "reference_position_m": round(
                reference, 4
            ),
            "predicted_position_m": round(
                predicted, 4
            ),
            "change_from_reference_m": round(
                predicted - reference, 4
            ),
            "reference_point": shoreline_map_point(
                coords, reference
            ),
            "predicted_point": shoreline_map_point(
                coords, predicted
            )
        })

    return jsonify({
        "site": "Kuala Merang",
        "reference_year": reference_year,
        "forecast_year": forecast_year,
        "years_ahead": forecast_year - reference_year,
        "model_status": "Experimental",
        "transects": results
    })

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )
