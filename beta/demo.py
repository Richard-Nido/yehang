"""Add explicitly synthetic measurements to existing and new demonstration workspaces."""

import json
from datetime import timedelta
from core.demo import demo_path
from storage import schedule, workspace as ws
from beta.timebase import local, stamp

EDITION = "demo-beta2"


def extend(db, profile):
    with schedule.locked_profile(db, profile, "synthetic"):
        if db.execute(
            "SELECT 1 FROM beta_demo_editions WHERE edition=?", (EDITION,)
        ).fetchone():
            return
        source = json.loads(demo_path("demo-records.json").read_text(encoding="utf8"))
        extras = []
        for index, row in enumerate(
            r for r in source["records"] if r["metric"] == "sleep"
        ):
            for i, shift in enumerate((45, 95)):
                t = stamp(local(row["start"]) + timedelta(minutes=shift))
                extras.append(
                    dict(
                        id=f"demo2-sdnn-{index}-{i}",
                        metric="hrv_sdnn",
                        source=row["source"],
                        start=t,
                        end=t,
                        value=42 + (index * 5 % 17) - 3 * i,
                        unit="ms",
                    )
                )
        start = "2026-11-01T13:00+08:00"
        stop = "2026-11-01T13:20+08:00"
        extras.append(
            dict(
                id="demo2-nap",
                metric="sleep",
                source="watch_1",
                start=start,
                end=stop,
                value="asleep",
                unit="stage",
            )
        )
        ws._insert_batch(
            db, profile, EDITION, extras, {"mode": "synthetic", "file": "夜航示例补充"}
        )
        db.execute(
            "INSERT INTO plans VALUES (?,?,1,?,?,20,?)",
            (
                profile,
                "demo2-short-rest",
                start,
                stop,
                json.dumps({"origin": "example"}),
            ),
        )
        db.execute("INSERT INTO beta_demo_editions VALUES (?)", (EDITION,))
        db.execute(
            "UPDATE profiles SET revision=revision+1 WHERE profile_id=?", (profile,)
        )
