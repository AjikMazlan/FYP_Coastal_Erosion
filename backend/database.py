import csv
import math
from pathlib import Path

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = PROJECT_ROOT / "backend" / "instance" / "coastal_erosion.db"
CSV_PATH = PROJECT_ROOT / "data" / "processed" / "coastal_app_locations.csv"

db = SQLAlchemy()


class CoastalPoint(db.Model):
    __tablename__ = "coastal_points"

    point_id = db.Column(db.Integer, primary_key=True, autoincrement=False)
    jps_no = db.Column(db.Integer, nullable=True)
    coastal_cell = db.Column(db.String(20), nullable=False)
    district = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(255), nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    source_type = db.Column(db.String(40), nullable=False)
    risk_label = db.Column(db.String(20), nullable=False)
    projection_source = db.Column(db.String(40), nullable=False)
    primary_rate_m_yr = db.Column(db.Float, nullable=True)
    lr_experimental_rate_m_yr = db.Column(db.Float, nullable=True)


def configure_database(app, database_path=DATABASE_PATH):
    database_path = Path(database_path).resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)

    app.config["SQLALCHEMY_DATABASE_URI"] = (
        "sqlite:///" + database_path.as_posix()
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)


def number(value, integer=False):
    if not value.strip():
        return None

    result = float(value)

    if not math.isfinite(result):
        raise ValueError("Non-finite number in CSV.")

    if integer:
        if not result.is_integer():
            raise ValueError("Expected a whole-number ID.")
        return int(result)

    return result


def import_coastal_points(csv_path=CSV_PATH):
    records = []

    with Path(csv_path).open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            record = {
                "point_id": number(row["Transect_ID"], integer=True),
                "jps_no": number(row["No"], integer=True),
                "coastal_cell": row["Coastal_Cell"],
                "district": row["District"],
                "location": row["Area_Location"],
                "longitude": number(row["Longitude_DD"]),
                "latitude": number(row["Latitude_DD"]),
                "source_type": row["Source_Type"],
                "risk_label": row["Risk_Label"],
                "projection_source": row["Projection_Source"],
                "primary_rate_m_yr": number(row["Primary_Rate_m_yr"]),
                "lr_experimental_rate_m_yr": number(
                    row["LR_Experimental_Rate_m_yr"]
                ),
            }

            if record["point_id"] is None or record["point_id"] <= 0:
                raise ValueError("Invalid coastal point ID.")

            if record["latitude"] is None or not -90 <= record["latitude"] <= 90:
                raise ValueError("Invalid latitude.")

            if record["longitude"] is None or not -180 <= record["longitude"] <= 180:
                raise ValueError("Invalid longitude.")

            if record["risk_label"] not in {
                "Stable", "Warning", "Critical", "Protected"
            }:
                raise ValueError("Unknown risk category.")

            records.append(record)

    ids = {record["point_id"] for record in records}

    if not records or len(ids) != len(records):
        raise ValueError("CSV is empty or contains duplicate point IDs.")

    existing_ids = set(
        db.session.scalars(db.select(CoastalPoint.point_id))
    )

    if existing_ids - ids:
        raise ValueError(
            "Database contains IDs absent from CSV. Review before importing."
        )

    try:
        for record in records:
            db.session.merge(CoastalPoint(**record))

        db.session.commit()

    except Exception:
        db.session.rollback()
        raise

    return len(records)


if __name__ == "__main__":
    app = Flask(__name__)
    configure_database(app)

    with app.app_context():
        db.create_all()

        imported = import_coastal_points()

        total = db.session.scalar(
            db.select(db.func.count()).select_from(CoastalPoint)
        )

        risks = db.session.execute(
            db.select(CoastalPoint.risk_label, db.func.count())
            .group_by(CoastalPoint.risk_label)
            .order_by(CoastalPoint.risk_label)
        ).all()

        print("Database:", DATABASE_PATH)
        print("Imported/updated:", imported)
        print("Total coastal points:", total)

        for risk, count in risks:
            print(f"{risk}: {count}")