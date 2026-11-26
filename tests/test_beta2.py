import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from beta import provider, service
from storage import workspace
from studio import app


class Beta2Flows(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.enterContext(
            patch.dict("os.environ", YEHANG_DB_PATH=str(Path(temp.name) / "qa.db"))
        )
        self.c = self.enterContext(
            TestClient(app, base_url="http://localhost", headers={"X-Yehang": "1"})
        )

    def state(self, p=service.DEMO):
        return self.c.get("/api/state", params={"profile": p}).json()

    def test_demo_scores_migrate_once_without_altering_personal_records(self):
        first = self.state()
        self.assertTrue(
            all(
                isinstance(x, int)
                for x in first["series"]["recovery"] + first["series"]["stress"]
            )
        )
        self.assertEqual(first["revision"], self.state()["revision"])
        self.assertEqual(len(first["reviews"]), 1)
        self.assertIn("20 分钟", first["reviews"][0]["evidence"]["details"][0])
        self.assertIsNone(self.state(service.PERSON)["recovery"])

    def test_early_feedback_draft_is_editable_and_not_saved_by_parsing(self):
        d = self.state()
        inputs = {
            "profile": service.DEMO,
            "revision": d["revision"],
            "start": "2026-11-03T17:00+08:00",
            "end": "2026-11-03T17:20+08:00",
        }
        pid = self.c.post("/api/plans", json=inputs).json()["id"]
        with patch.object(
            provider,
            "complete",
            return_value='{"status":"部分完成","fatigue":2,"note":"休息了一会"}',
        ):
            draft = self.c.post(
                "/api/feedback/draft", json={"text": "休息了一会"}
            ).json()
        r = next(r for r in self.state()["reviews"] if r["id"] == pid)
        self.assertEqual(r["status"], "未反馈")
        res = self.c.post(
            "/api/feedback",
            json={**r, **draft, "profile": service.DEMO, "note": "本人修改过的记录"},
        )
        self.assertEqual(res.status_code, 200)
        r = next(r for r in self.state()["reviews"] if r["id"] == pid)
        self.assertEqual(
            (r["note"], r["status"], r["fatigue"]), ("本人修改过的记录", "部分完成", 2)
        )
        self.assertFalse(r["evidence"]["details"])

    def test_bad_model_draft_keeps_history(self):
        d = self.state()
        with patch.object(
            provider,
            "complete",
            return_value='{"status":"完成","fatigue":99,"note":""}',
        ):
            self.assertEqual(
                self.c.post(
                    "/api/feedback/draft", json={"text": "还算可以"}
                ).status_code,
                400,
            )
        self.assertEqual(self.state()["revision"], d["revision"])

    def test_clear_uses_profile_revision_and_keeps_other_categories(self):
        d = self.state()
        for group in ("health", "schedule", "feedback", "plans"):
            info = self.c.get(
                "/api/history", params={"profile": service.DEMO, "group": group}
            ).json()
            req = {
                "profile": service.DEMO,
                "group": group,
                "revision": info["revision"],
            }
            self.assertEqual(
                self.c.post("/api/history/clear", json=req).status_code, 200
            )
            self.assertEqual(
                self.c.post("/api/history/clear", json=req).status_code, 400
            )
            if group == "health":
                now = self.state()
                self.assertIsNone(now["recovery"])
                self.assertEqual(len(now["reviews"]), len(d["reviews"]))
        with workspace.open_workspace() as db:
            self.assertFalse(db.execute("PRAGMA foreign_key_check").fetchall())
        self.assertEqual(self.state(service.PERSON)["revision"], 0)
