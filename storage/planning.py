"""A4 schema, local-day horizon, selection validation and immutable plan versions."""
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from core import planner
from core.features import midnight
from storage import schedule, workspace as ws

LABEL = dict(available="可休息区间", commute="通勤", course="固定课程", work="工作", day="日班", night="夜班")
TABLES = ("plans", "planning_blocks", "planning_settings")


def initialize(db):
    db.execute("""CREATE TABLE planning_settings(profile_id TEXT PRIMARY KEY REFERENCES profiles,
        minutes INTEGER NOT NULL CHECK(minutes>0), demo_clock TEXT)""")
    db.execute("""CREATE TABLE planning_blocks(profile_id TEXT NOT NULL REFERENCES profiles,
        id TEXT NOT NULL, kind TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL,
        PRIMARY KEY(profile_id,id))""")
    db.execute("""CREATE TABLE plans(profile_id TEXT NOT NULL REFERENCES profiles, plan_id TEXT NOT NULL,
        version INTEGER NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL, minutes INTEGER NOT NULL,
        basis TEXT NOT NULL, PRIMARY KEY(profile_id,plan_id,version))""")
    for p, raw in db.execute("""SELECT profile_id,settings FROM imports JOIN profiles USING(profile_id)
            WHERE mode='synthetic' AND json_type(settings,'$.planning')='object' ORDER BY imports.rowid DESC"""):
        if not db.execute("SELECT 1 FROM planning_settings WHERE profile_id=?", (p,)).fetchone():
            seed(db, p, json.loads(raw)["planning"])


def seed(db, profile, data):
    planner.check_minutes(data["requested_minutes"])
    planner.endpoint(data["demo_clock"], "演示时钟")
    db.execute("INSERT INTO planning_settings VALUES (?,?,?)", (profile, data["requested_minutes"], data["demo_clock"]))
    entries = [("available", *p) for p in data["available"]]
    entries.extend((b["kind"], b["start"], b["end"]) for b in data["busy"])
    for kind, start, end in entries:
        planner.interval(start, end)
        if kind not in schedule.BLOCK_TABLE:
            raise ValueError("规划类型无效")
        table = schedule.BLOCK_TABLE[kind]
        db.execute(f"INSERT INTO {table} VALUES (?,?,?,?,?)", (profile, uuid4().hex, kind, start, end))


def configure(db, profile, mode, rev, minutes, clock):
    planner.check_minutes(minutes)
    with schedule.edit(db, profile, mode, rev):
        old = db.execute("SELECT demo_clock FROM planning_settings WHERE profile_id=?", (profile,)).fetchone()
        if clock is not None:
            if mode != "synthetic" or not old or not old[0]:
                raise ValueError("仅完整合成演示可调整时钟")
            planner.endpoint(clock, "演示时钟")
        db.execute("""INSERT INTO planning_settings VALUES (?,?,?) ON CONFLICT(profile_id)
            DO UPDATE SET minutes=excluded.minutes,demo_clock=coalesce(excluded.demo_clock,demo_clock)""",
                   (profile, minutes, clock))


@dataclass
class View:
    revision: int
    now: datetime
    limit: datetime
    demo: bool
    minutes: int
    blocks: list
    available: list
    busy: list
    fragments: list
    windows: list
    history: list


def read(db, profile, zone_name):
    zone = ZoneInfo(zone_name)
    prefs = db.execute("""SELECT minutes,demo_clock FROM planning_settings
        WHERE profile_id=?""", (profile,)).fetchone()
    minutes, clock = prefs or (30, None)
    now = planner.endpoint(clock, "演示时钟") if clock else datetime.now(timezone.utc)
    limit = midnight(now.astimezone(zone).date() + timedelta(days=7), zone)
    blocks = []
    available, busy = [], []
    for table in ("schedule_blocks", "planning_blocks"):
        for row in db.execute(f"SELECT * FROM {table} WHERE profile_id=?", (profile,)):
            b = dict(row)
            b["span"] = planner.interval(b["start"], b["end"])
            blocks.append(b)
            (available if b["kind"] == "available" else busy).append(b["span"])
    blocks.sort(key=lambda b: (b["span"], b["id"]))
    def clipped(spans):
        return [(max(s, now), min(e, limit)) for s, e in spans if e > now and s < limit]
    fragments = planner.difference(clipped(available), clipped(busy))
    history = [dict(r) for r in db.execute("SELECT * FROM plans WHERE profile_id=? ORDER BY rowid", (profile,))]
    return View(ws.revision(db, profile), now, limit, bool(clock), minutes, blocks, available, busy,
                fragments, planner.enough(fragments, minutes), history)


def overlaps(a, b):
    return a[0] < b[1] and b[0] < a[1]


def conflicts(view, plan):
    span = planner.interval(plan["start"], plan["end"])
    reasons = [b for b in view.blocks if b["kind"] != "available" and overlaps(b["span"], span)]
    outside = not any(s <= span[0] and span[1] <= e for s, e in planner.merged(view.available))
    return reasons, outside


def placement(view, start, window):
    instant = planner.endpoint(start, "计划起点")
    duration = timedelta(minutes=view.minutes)
    # Re-read the horizon at commit: its left edge may advance with the live clock.
    for s, e in view.windows:
        if max(s, window[0]) <= instant and instant + duration <= min(e, window[1]):
            return instant, instant + duration
    raise ValueError("起点和结束须落在同一当前候选内，请重新选择")


def save(db, profile, mode, revision, zone_name, start, window, plan_id=None):
    with schedule.locked_profile(db, profile, mode) as latest:
        view = read(db, profile, zone_name)
        request = dict(revision=revision, zone=zone_name, selected=[t.isoformat() for t in window],
                       start=planner.endpoint(start, "计划起点").isoformat(), target=plan_id)
        if latest != revision:
            # A committed copy of this exact submission is its own receipt.
            for row in reversed(view.history):
                if json.loads(row["basis"]).get("request") == request:
                    return row["plan_id"]
            raise ValueError("档案已更新，请重新选择")
        s, e = placement(view, start, window)
        current = {r["plan_id"]: r for r in view.history}
        if plan_id is not None and plan_id not in current:
            raise ValueError("原计划已变化，请重新选择")
        for r in current.values():
            if (plan_id is None or r["plan_id"] == plan_id) and planner.interval(r["start"], r["end"]) == (s, e):
                return r["plan_id"]
        version = current[plan_id]["version"] + 1 if plan_id else 1
        plan_id = plan_id or uuid4().hex
        zone = ZoneInfo(zone_name)
        actual = next((l, h) for l, h in view.windows if l <= s and e <= h)
        basis = dict(window=[t.isoformat() for t in actual], zone=zone_name, revision=revision,
                     clock=view.now.isoformat(), minutes=view.minutes, request=request)
        db.execute("INSERT INTO plans VALUES (?,?,?,?,?,?,?)",
                   (profile, plan_id, version, s.astimezone(zone).isoformat(), e.astimezone(zone).isoformat(),
                    view.minutes, json.dumps(basis)))
        db.execute("UPDATE profiles SET revision=revision+1 WHERE profile_id=?", (profile,))
        return plan_id
