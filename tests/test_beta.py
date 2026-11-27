"""Regression coverage for user-facing Beta flows. All records here are synthetic."""

from datetime import timedelta
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from beta import provider, service
from beta.rest import recommend
from beta.timebase import local
from core.features import Feature
from studio import app


class BetaFlow(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        env = patch.dict(
            os.environ, {"YEHANG_DB_PATH": str(Path(folder.name) / "db.sqlite3")}
        )
        env.start()
        self.addCleanup(env.stop)
        self.client = TestClient(
            app, base_url="http://localhost", headers={"X-Yehang": "1"}
        )
        self.p = service.PERSON
        self.state()

    def state(self, **extra):
        r = self.client.get("/api/state", params={"profile": self.p, **extra})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def post(self, path, **kwargs):
        return self.client.post(
            "/api/" + path,
            json={"profile": self.p, "revision": self.state()["revision"], **kwargs},
        )

    def test_schedule_conversion_atomicity_and_dedup(self):
        ev = dict(
            kind="night",
            start="2026-11-03T06:00:00-05:00",
            end="2026-11-03T18:00:00-05:00",
            title="夜班",
        )
        self.assertEqual(self.post("events", events=[ev, ev]).json()["added"], 1)
        self.assertEqual(self.post("events", events=[ev]).json()["added"], 0)
        block = self.state(scheduleStart="2026-11-03")["blocks"][0]
        self.assertEqual(
            (block["start"], block["end"]),
            ("2026-11-03T19:00+08:00", "2026-11-04T07:00+08:00"),
        )
        r = self.post("events", events=[dict(ev, title="X"), dict(ev, end=ev["start"])])
        self.assertEqual(r.status_code, 400)
        self.assertEqual(len(self.state(scheduleStart="2026-11-03")["blocks"]), 1)

    def test_large_user_override_edit_and_retry(self):
        params = dict(start="2026-11-03T15:00", end="2026-11-07T03:00")
        key = self.post("plans", **params).json()["id"]
        self.assertEqual(self.post("plans", **params).json()["id"], key)
        self.assertEqual(
            self.post("plans", id=key, **dict(params, end="2026-11-04T12:00")).json()[
                "id"
            ],
            key,
        )
        r = self.state(week="2026-11-07")["reviews"]
        self.assertEqual((len(r), r[0]["version"], r[0]["minutes"]), (1, 2, 1260))

    def test_photo_order_default_online_and_fallback(self):
        self.p = service.DEMO
        self.state()
        with patch.object(provider, "complete", return_value="合成资料解释") as model:
            self.assertEqual(
                self.post("explanation", day="2026-11-03", rewrite=True).json()["source"], "api"
            )
            prompt = model.call_args.args[0]
            self.assertNotIn("watch_1", prompt)
        with patch.object(provider, "complete", side_effect=ValueError("offline")):
            r = self.post("explanation", day="2026-11-03", rewrite=True).json()
            self.assertEqual((r["message"], r["source"]), ("模型调用失败", "offline"))

    def test_health_import_duplicate_rollback_and_followup(self):
        body = dict(start="2026-11-03T12:00", end="2026-11-03T12:30")
        key = self.post("plans", **body).json()["id"]
        url = "/api/upload/health?ext=xml"
        xml = """<HealthData><Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="watch_1"
          startDate="2026-11-03 04:00:00 +0000" endDate="2026-11-03 04:30:00 +0000"
          value="HKCategoryValueSleepAnalysisAsleep"/></HealthData>"""
        self.assertEqual(self.client.post(url, content=xml).json()["added"], 1)
        self.assertEqual(self.client.post(url, content=xml).json()["duplicate"], 1)
        rev = self.state()["revision"]
        self.assertEqual(self.client.post(url, content=xml[:-8]).status_code, 400)
        self.assertEqual(self.state()["revision"], rev)
        item = self.state(week="2026-11-03")["reviews"][0]
        self.assertIn("30 分钟", item["evidence"]["details"][0])
        self.assertEqual(
            self.post(
                "feedback", id=key, version=1, feedbackRev=0, status="完成", fatigue=1
            ).status_code,
            200,
        )
        self.assertEqual(self.state(week="2026-11-03")["reviews"][0]["fatigue"], 1)

    def test_physiology_changes_recommendation_and_busy_buffer(self):
        now = local("2026-11-03T12:00")
        data = {m: {} for m in ("sleep", "sleep_hrv", "hrv_sdnn", "resting_hr")}
        busy = [dict(kind="work", start="2026-11-03T14:00", end="2026-11-03T22:00")]
        basic = recommend(now, busy, [], data, {})
        self.assertEqual(basic["minutes"], 20)
        data["sleep"][now.date()] = Feature(310, 1)
        short = recommend(now, busy, [], data, {})
        self.assertEqual(short["minutes"], 30)
        self.assertLessEqual(
            local(short["end"]) + timedelta(minutes=15), local(busy[0]["start"])
        )

    def test_protocols_have_native_images_and_read_text(self):
        examples = {
            "chat": {"choices": [{"message": {"content": "yes"}}]},
            "responses": {
                "output": [{"content": [{"type": "output_text", "text": "yes"}]}]
            },
            "anthropic": {"content": [{"type": "text", "text": "yes"}]},
            "gemini": {"candidates": [{"content": {"parts": [{"text": "yes"}]}}]},
        }
        for protocol, response in examples.items():
            cfg = dict(
                base="https://example.invalid/v1", model="fixture", protocol=protocol
            )
            with (
                self.subTest(protocol=protocol),
                patch.object(provider, "saved", return_value=cfg),
                patch.object(provider, "secret", return_value="fixture"),
                patch.object(provider, "request", return_value=response) as call,
            ):
                self.assertEqual(provider.complete("read", ["aGVsbG8="]), "yes")
                self.assertIn("aGVsbG8=", json.dumps(call.call_args.args[-1]))


if __name__ == "__main__":
    unittest.main()
