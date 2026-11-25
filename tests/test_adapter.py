"""B2 独立验算：python -m unittest -v qa.test_b2_import。"""

from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as ET

from adapters.health import METRICS, read_export, record_key
from adapters.field_mapping import normalize_value
from core.sleep import sleep_segments


FIXTURES = Path(__file__).resolve().parents[1] / "yehang-week" / "fixtures"


class ImportTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.mapping = self.tmp / ".local" / "sources.json"
        self.base = json.loads((FIXTURES / "crossnight.json").read_text(encoding="utf-8"))

    def read(self, path, **kwargs):
        return read_export(path, date_from=kwargs.pop("date_from", "2026-11-03"),
                           date_to=kwargs.pop("date_to", "2026-11-03"),
                           source_map_path=self.mapping, **kwargs)

    def json_file(self, records=None, **top):
        data = deepcopy(self.base)
        if records is not None:
            data["records"] = records
        data.update(top)
        p = self.tmp / "input.json"
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return p

    def xml_file(self, rows, *, name="input.xml", trailer=""):
        root = ET.Element("HealthData")
        for attrs in rows:
            ET.SubElement(root, "Record", attrs)
        p = self.tmp / name
        p.write_text(ET.tostring(root, encoding="unicode") + trailer, encoding="utf-8")
        return p

    def assert_counts(self, report):
        self.assertEqual(report["read_target"], report["accepted"] + report["duplicate"] + report["invalid"])
        self.assertEqual(sum(report["by_metric"].values()), report["accepted"])

    def test_crossnight_equivalence_and_a1_integration(self):
        x = self.read(FIXTURES / "crossnight.xml")
        j = self.read(FIXTURES / "crossnight.json")
        self.assertEqual({record_key(r) for r in x["records"]}, {record_key(r) for r in j["records"]})
        for result in (x, j):
            self.assertEqual(result["report"]["accepted"], 4)
            segments = sleep_segments(result["records"], source="watch_1")
            self.assertEqual([(s.duration / timedelta(minutes=1), str(s.wake_date)) for s in segments], [(105, "2026-11-03")])
            self.assert_counts(result["report"])
        self.assertIsNone(x["report"]["mode"])
        self.assertEqual(j["report"]["mode"], "synthetic")

    def test_six_metrics_and_unit_conversion(self):
        x = self.read(FIXTURES / "b2-six-metrics.xml")
        j = self.read(FIXTURES / "b2-six-metrics.json")
        self.assertEqual({record_key(r) for r in x["records"]}, {record_key(r) for r in j["records"]})
        self.assertEqual(x["report"]["accepted"], 9)
        self.assertFalse(x["report"]["missing_metrics"])
        values = {r["metric"]: (r["value"], r["unit"]) for r in x["records"]}
        self.assertEqual(values["hrv_sdnn"], (50, "ms"))
        self.assertEqual(values["active_energy"], (10, "kcal"))
        self.assertEqual(values["heart_rate"], (60, "bpm"))

    def test_content_duplicates_and_same_id_conflict(self):
        first = deepcopy(self.base["records"][1])
        rows = [first, dict(first, id="another"), dict(first, value="deep"), dict(first)]
        r = self.read(self.json_file(rows))
        self.assertEqual((r["report"]["accepted"], r["report"]["duplicate"], r["report"]["invalid"]), (1, 2, 1))
        self.assertEqual(r["report"]["id_conflict"], 1)
        self.assertEqual(r["records"][0]["value"], "core")
        self.assert_counts(r["report"])

    def test_energy_calorie_case_and_joule_conversions(self):
        for value, unit in [(1, "Cal"), (1, "kcal"), (1000, "cal"), (4.184, "kJ"), (4184, "J")]:
            with self.subTest(unit=unit):
                self.assertEqual(normalize_value("active_energy", value, unit), (1, "kcal"))

    def test_equivalent_utc_offsets_deduplicate(self):
        row = deepcopy(self.base["records"][1])
        equivalent = dict(row, id="utc", start="2026-11-02T15:30:00Z", end="2026-11-02T17:30:00Z")
        r = self.read(self.json_file([row, equivalent]))
        self.assertEqual((r["report"]["accepted"], r["report"]["duplicate"]), (1, 1))
        self.assertEqual(r["records"][0]["start"], row["start"])

    def test_date_window_context_and_half_open_edges(self):
        template = self.base["records"][1]
        rows = [
            dict(template, id="old", start="2026-11-01T22:00:00+08:00", end="2026-11-01T23:00:00+08:00"),
            dict(template, id="ends_at_lower", start="2026-11-01T23:00:00+08:00", end="2026-11-02T00:00:00+08:00"),
            dict(template, id="context", start="2026-11-02T10:00:00+08:00", end="2026-11-02T11:00:00+08:00"),
            dict(template, id="full_interval", start="2026-11-01T23:00:00+08:00", end="2026-11-03T01:00:00+08:00"),
            dict(template, id="future", start="2026-11-04T00:00:00+08:00", end="2026-11-04T01:00:00+08:00"),
        ]
        r = self.read(self.json_file(rows))
        self.assertEqual({row["id"] for row in r["records"]}, {"context", "full_interval"})
        self.assertEqual(r["report"]["out_of_range"], 3)
        self.assertEqual(r["report"]["read_target"], 2)
        self.assertEqual(r["report"]["coverage"]["sleep"]["watch_1"]["days_with_records"], 1)

    def test_dst_time_and_zero_numeric_samples(self):
        row = dict(self.base["records"][1], start="2026-11-01T01:30:00-04:00", end="2026-11-01T01:30:00-05:00")
        r = self.read(self.json_file([row]), analysis_tz="America/New_York", date_from="2026-11-01", date_to="2026-11-01")
        segment = sleep_segments(r["records"], source="watch_1", analysis_tz="America/New_York")[0]
        self.assertEqual(segment.duration, timedelta(hours=1))
        instant = dict(row, id="steps", metric="steps", value=0, unit="count", start="2026-11-03T12:00:00+08:00", end="2026-11-03T12:00:00+08:00")
        r = self.read(self.json_file([instant]))
        self.assertEqual(r["report"]["accepted"], 1)
        self.assertEqual(r["records"][0]["value"], 0)

    def test_bad_rows_isolated_and_counts_conserved(self):
        good = dict(self.base["records"][1], metric="heart_rate", value=60, unit="bpm")
        bad = [dict(good, id="boolean", value=True), dict(good, id="negative", value=-1),
               dict(good, id="nan", value=float("nan")), dict(good, id="zero", value=0),
               dict(good, id="unit", unit="unknown"), dict(good, id="naive", start="2026-11-02T23:30:00"),
               dict(good, id="backwards", end="2026-11-02T22:00:00+08:00"),
               dict(good, id="source", source="Unmapped device name"), dict(good, id=""),
               dict(good, id="invalid_metric", metric=[]), None]
        r = self.read(self.json_file([good, *bad, dict(good, metric="body_mass")]))
        self.assertEqual((r["report"]["accepted"], r["report"]["invalid"], r["report"]["ignored_type"]), (1, len(bad), 1))
        self.assert_counts(r["report"])

    def test_out_of_range_bad_value_is_not_counted_invalid(self):
        row = dict(self.base["records"][1], value="bad", start="2026-10-01T00:00:00+08:00", end="2026-10-01T01:00:00+08:00")
        report = self.read(self.json_file([row]))["report"]
        self.assertEqual((report["read_target"], report["invalid"], report["out_of_range"]), (0, 0, 1))

    def test_xml_sources_and_ids_stay_stable(self):
        attrs = dict(ET.parse(FIXTURES / "crossnight.xml").getroot().findall("Record")[1].attrib)
        attrs.update(sourceName="Synthetic Watch B", device="<<HKDevice: 0x123>, model:Watch, hardware:Watch7,7, software:11.0>")
        one = self.read(self.xml_file([attrs]))
        updated = dict(attrs, sourceVersion="99", device=attrs["device"].replace("0x123", "0x456").replace("11.0", "12.0"))
        two = self.read(self.xml_file([dict(attrs, sourceName="Synthetic Watch C"), updated]))
        original = next(r for r in two["records"] if r["source"] == one["records"][0]["source"])
        self.assertEqual(one["records"][0], original)
        contents = self.mapping.read_text(encoding="utf-8")
        self.assertNotIn("Synthetic", contents)
        self.assertNotIn("HKDevice", contents)
        self.assertEqual(two["report"]["sources_needing_confirmation"], ["watch_1", "watch_2"])

    def test_xml_offsets_do_not_change_generated_id(self):
        attrs = dict(ET.parse(FIXTURES / "crossnight.xml").getroot().findall("Record")[1].attrib)
        one = self.read(self.xml_file([attrs]))
        attrs.update(startDate="2026-11-02T15:30:00Z", endDate="2026-11-02T17:30:00Z")
        two = self.read(self.xml_file([attrs]))
        self.assertEqual(one["records"][0]["id"], two["records"][0]["id"])

    def test_malformed_xml_returns_no_partial_result_or_alias_update(self):
        attrs = dict(ET.parse(FIXTURES / "crossnight.xml").getroot().findall("Record")[1].attrib)
        attrs["sourceName"] = "Synthetic Watch pending"
        with self.assertRaises(ValueError):
            self.read(self.xml_file([attrs], trailer="<broken"))
        self.assertFalse(self.mapping.exists())
        wrong = self.tmp / "clinical.xml"
        wrong.write_text("<ClinicalDocument/>", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.read(wrong)

    def test_version_envelope_and_broken_json_rejected(self):
        for changes in [{"schema_version": 1}, {"schema_version": "2.0"}, {"mode": []},
                        {"records": {}}, {"name": "synthetic-person"}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.read(self.json_file(**changes))
        p = self.tmp / "broken.json"
        p.write_text('{"records":', encoding="utf-8")
        with self.assertRaises(ValueError):
            self.read(p)

    def test_bed_only_and_source_selection(self):
        bed = deepcopy(self.base["records"][0])
        r = self.read(self.json_file([bed, dict(bed, source="phone_1")]))
        self.assertEqual(r["report"]["suggested_sources"]["sleep"], "phone_1")
        self.assertEqual(sleep_segments(r["records"], source="watch_1"), [])
        self.assertEqual(r["report"]["sleep_stage_counts"]["watch_1"], {"in_bed": 1})
        self.assertIsNone(r["report"]["suggested_sources"]["hrv_sdnn"])
        self.assertIn("hrv_sdnn", r["report"]["missing_metrics"])

    def test_corrupt_source_map_and_bad_dates_rejected(self):
        self.mapping.parent.mkdir()
        self.mapping.write_text("[]", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.read(FIXTURES / "crossnight.xml")
        for params in [{"date_from": "invalid"}, {"date_from": "2026-12-01"}, {"analysis_tz": "NoSuch/Timezone"}]:
            with self.subTest(params=params), self.assertRaises(ValueError):
                self.read(FIXTURES / "crossnight.json", **params)

    def test_json_roundtrip_preserves_content(self):
        original = self.read(FIXTURES / "b2-six-metrics.xml")
        p = self.json_file(original["records"], mode="personal")
        converted = self.read(p)
        self.assertEqual(original["records"], converted["records"])
        for row in converted["records"]:
            self.assertEqual(set(row), {"id", "metric", "start", "end", "source", "value", "unit"})


if __name__ == "__main__":
    unittest.main()
