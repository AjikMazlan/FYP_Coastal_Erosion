import copy
import csv
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("coastsat_pilot", ROOT / "scripts" / "coastsat" / "pilot_site.py")
PILOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PILOT)


class FakeDownloader:
    def __init__(self, new_count=2):
        self.new_count = new_count
        self.auth_calls = []
        self.download_calls = []
        self.local = {}

    def authenticate_and_initialize(self, project):
        self.auth_calls.append(project)

    def get_metadata(self, inputs):
        return self.local

    def check_images_available(self, inputs):
        return {"S2": [{} for _ in range(self.new_count)]}, {}

    def retrieve_images(self, inputs):
        self.download_calls.append(copy.deepcopy(inputs))
        return {"S2": {"filenames": ["pilot.tif"], "dates": ["2025-03-15"]}}


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.config, self.polygon = PILOT.load_config(PILOT.DEFAULT_CONFIG)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.coastsat = Path(self.temp.name)
        (self.coastsat / "coastsat").mkdir()
        (self.coastsat / "coastsat" / "SDS_download.py").write_text("", encoding="utf-8")

    def run_action(self, action, backend):
        with redirect_stdout(io.StringIO()):
            return PILOT.run_coastsat(action, self.config, self.polygon, self.coastsat, backend)

    def test_preview_works_without_coastsat_or_authentication(self):
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(PILOT.main(["preview"]), 0)
        self.assertIn("BUKIT_KELUANG_2025_PILOT", output.getvalue())

    def test_roi_contains_the_three_named_jps_stations(self):
        with (ROOT / "data" / "raw" / "jps_coastal_erosion_full.csv").open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        selected = [r for r in rows if int(r["No"]) in self.config["jps_station_ids"]]
        self.assertEqual(len(selected), 3)
        ring = self.polygon[0]
        for row in selected:
            self.assertIn("Bukit Keluang", row["Area_Location"])
            self.assertLess(min(p[0] for p in ring), float(row["Longitude_DD"]))
            self.assertGreater(max(p[0] for p in ring), float(row["Longitude_DD"]))
            self.assertLess(min(p[1] for p in ring), float(row["Latitude_DD"]))
            self.assertGreater(max(p[1] for p in ring), float(row["Latitude_DD"]))

    def test_check_queries_without_downloading_or_creating_pilot(self):
        backend = FakeDownloader()
        result = self.run_action("check", backend)
        self.assertEqual(result["new"], {"S2": 2})
        self.assertEqual(backend.auth_calls, ["coastal-erosion-fyp"])
        self.assertEqual(backend.download_calls, [])
        self.assertFalse((self.coastsat / "data" / self.config["sitename"]).exists())

    def test_download_uses_a_separate_site_and_records_request(self):
        backend = FakeDownloader()
        self.run_action("download", backend)
        request = backend.download_calls[0]
        self.assertEqual(request["sitename"], "BUKIT_KELUANG_2025_PILOT")
        self.assertEqual(request["polygon"], self.polygon)
        self.assertEqual(request["dates"], ["2025-03-01", "2025-05-01"])
        folder = self.coastsat / "data" / request["sitename"]
        self.assertEqual(json.loads((folder / "pilot_request.json").read_text()), PILOT.request_manifest(self.config, self.polygon))

    def test_changed_roi_cannot_reuse_existing_pilot_cache(self):
        self.run_action("download", FakeDownloader())
        changed = copy.deepcopy(self.polygon)
        changed[0][1][0] += 0.001
        backend = FakeDownloader()
        with self.assertRaisesRegex(ValueError, "different ROI/date"):
            PILOT.run_coastsat("check", self.config, changed, self.coastsat, backend)
        self.assertEqual(backend.auth_calls, [])

    def test_cached_matching_images_do_not_trigger_another_download(self):
        self.run_action("download", FakeDownloader())
        backend = FakeDownloader(new_count=0)
        backend.local = {"S2": {"dates": ["2025-03-15", "2024-03-15"]}}
        self.run_action("download", backend)
        self.assertEqual(backend.download_calls, [])

    def test_no_images_does_not_create_a_pilot_dataset(self):
        backend = FakeDownloader(new_count=0)
        with self.assertRaisesRegex(ValueError, "No matching images"):
            self.run_action("download", backend)
        self.assertFalse((self.coastsat / "data" / self.config["sitename"]).exists())


if __name__ == "__main__":
    unittest.main()
