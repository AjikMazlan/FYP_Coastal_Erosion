import json
import math
import sys
from pathlib import Path

root = Path.cwd()
sys.path.insert(0, str(root / "backend"))
from app import app

site = "roi_c8_jps_082_contour_review"
with app.test_client() as client:
    listed = client.get("/shoreline-sites")
    assert listed.status_code == 200
    matches = [item for item in listed.get_json()["sites"] if item["site_id"] == site]
    assert len(matches) == 1, listed.get_json()["unavailable_sites"]
    info = matches[0]
    assert info["transect_count"] == 5
    tests = []
    for year in range(info["first_forecast_year"], info["last_forecast_year"] + 1):
        response = client.get("/shoreline-prediction", query_string={"site": site, "year": year})
        data = response.get_json()
        assert response.status_code == 200, (year, response.status_code, data)
        assert data["forecast_year"] == year and data["site_id"] == site
        transects = data["transects"]
        assert sorted(row["transect_id"] for row in transects) == [1, 2, 3, 4, 5]
        coordinates = set()
        outside = []
        for row in transects:
            point = row["predicted_point"]
            lat, lon = point["latitude"], point["longitude"]
            assert math.isfinite(lat) and -90 <= lat <= 90
            assert math.isfinite(lon) and -180 <= lon <= 180
            assert math.isfinite(row["predicted_position_m"])
            coordinates.add((lat, lon))
            if point["outside_transect"]:
                outside.append(row["transect_id"])
        assert len(coordinates) == 5
        tests.append(dict(year=year, http=response.status_code, points=len(coordinates), outside_transects=outside))

result = dict(site_id=site, site_name=info["site"], listed_http=listed.status_code, tests=tests)
path = root / "results" / "shoreline_pipeline" / "monthly_v1" / site / "api_test_results.json"
path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result), flush=True)

