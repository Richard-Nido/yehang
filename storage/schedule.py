"""Profile-scoped schedule, daily context history and combined demo transactions."""
import json
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from core.demo import FIXTURE, fingerprint, read_selected
from core.features import midnight
from core.planner import interval
from core.sleep import utc_time
from storage import workspace as ws

CONTEXTS = ("unknown", "night", "recovery", "day", "rest")
KINDS = ("caffeine", "exercise", "fatigue")
BLOCK_TABLE = {"night": "schedule_blocks", "day": "schedule_blocks",
               "available": "planning_blocks", "commute": "planning_blocks",
               "course": "planning_blocks", "work": "planning_blocks"}
TABLES = ("context_history", "schedule_blocks", "events", "primary_sources")
DEMO_DAY = date(2026, 11, 3)


def initialize(db):
    db.execute("""CREATE TABLE primary_sources (profile_id TEXT NOT NULL REFERENCES profiles,
        metric TEXT NOT NULL, source TEXT NOT NULL, PRIMARY KEY(profile_id,metric))""")
    db.execute("""CREATE TABLE context_history (
        seq INTEGER PRIMARY KEY, profile_id TEXT NOT NULL REFERENCES profiles,
        day TEXT NOT NULL, context TEXT, origin TEXT NOT NULL,
        changed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))""")
    db.execute("""CREATE TABLE schedule_blocks (
        profile_id TEXT NOT NULL REFERENCES profiles, id TEXT NOT NULL, kind TEXT NOT NULL,
        start TEXT NOT NULL, end TEXT NOT NULL, PRIMARY KEY(profile_id,id))""")
    db.execute("""CREATE TABLE events (
        profile_id TEXT NOT NULL REFERENCES profiles, id TEXT NOT NULL, kind TEXT NOT NULL,
        at TEXT NOT NULL, note TEXT NOT NULL, value INTEGER, PRIMARY KEY(profile_id,id))""")


@contextmanager
def locked_profile(db, profile, mode):
    with db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT INTO profiles(profile_id,mode) VALUES (?,?) ON CONFLICT DO NOTHING", (profile, mode))
        if db.execute("SELECT mode FROM profiles WHERE profile_id=?", (profile,)).fetchone()[0] != mode:
            raise ValueError("档案模式不一致")
        yield ws.revision(db, profile)


@contextmanager
def edit(db, profile, mode, expected):
    with locked_profile(db, profile, mode) as revision:
        if revision != expected:
            raise ValueError("档案已更新，请刷新后核对")
        yield
        db.execute("UPDATE profiles SET revision=revision+1 WHERE profile_id=?", (profile,))


def set_source(db, profile, mode, expected, metric, source):
    with edit(db, profile, mode, expected):
        if not db.execute("SELECT 1 FROM samples WHERE profile_id=? AND metric=? AND source=?",
                          (profile, metric, source)).fetchone():
            raise ValueError("该来源没有已确认样本")
        db.execute("""INSERT INTO primary_sources VALUES (?,?,?) ON CONFLICT(profile_id,metric)
            DO UPDATE SET source=excluded.source""", (profile, metric, source))


def event_values(kind, at, note="", value=None):
    utc_time(at)
    if kind not in KINDS or not isinstance(note, str):
        raise ValueError("事件类型或备注无效")
    if kind == "fatigue" and (type(value) is not int or not 1 <= value <= 5):
        raise ValueError("疲劳只接受自评整数 1–5")
    if kind != "fatigue" and value is not None:
        raise ValueError("只有疲劳事件可以填写自评分数")
    return kind, at, note, value


def save_item(db, profile, mode, expected, kind, start, *, end=None, note="", value=None, item_id=None):
    block = kind in BLOCK_TABLE
    if block:
        interval(start, end)
        values = (kind, start, end)
    else:
        values = event_values(kind, start, note, value)
    table = BLOCK_TABLE.get(kind, "events")
    with edit(db, profile, mode, expected):
        if item_id is None:
            db.execute(f"INSERT INTO {table} VALUES ({','.join('?' for _ in range(2 + len(values)))})",
                       (profile, uuid4().hex, *values))
        else:
            assignments = "kind=?,start=?,end=?" if block else "kind=?,at=?,note=?,value=?"
            if not db.execute(f"UPDATE {table} SET {assignments} WHERE profile_id=? AND id=?",
                              (*values, profile, item_id)).rowcount:
                raise ValueError("目标记录已变化")


def delete_item(db, profile, mode, expected, table, item_id):
    if table not in ("events", "schedule_blocks", "planning_blocks"):
        raise ValueError("未知记录类型")
    with edit(db, profile, mode, expected):
        db.execute(f"DELETE FROM {table} WHERE profile_id=? AND id=?", (profile, item_id))


def set_context(db, profile, mode, expected, day, context):
    if context not in (*CONTEXTS, None):
        raise ValueError("未知情境")
    with edit(db, profile, mode, expected):
        db.execute("INSERT INTO context_history(profile_id,day,context,origin) VALUES (?,?,?,'manual')",
                   (profile, day.isoformat(), context))


def records(db, profile, table):
    if table not in TABLES:
        raise ValueError("未知数据表")
    return [dict(r) for r in db.execute(f"SELECT * FROM {table} WHERE profile_id=? ORDER BY rowid", (profile,))]


def contexts(db, profile, zone_name):
    seeds, manual = {}, {}
    for r in records(db, profile, "context_history"):
        (seeds if r["origin"] == "fixture" else manual)[date.fromisoformat(r["day"])] = r["context"]
    zone = ZoneInfo(zone_name)
    derived = {}
    for r in records(db, profile, "schedule_blocks"):
        start = utc_time(r["start"]).astimezone(zone).date()
        end = utc_time(r["end"]).astimezone(zone).date()
        if r["kind"] == "night":
            derived[start] = "night"
            if end > start and derived.get(end) != "night":
                derived[end] = "recovery"
        elif r["kind"] == "day":
            derived.setdefault(start, "day")
    return {**seeds, **derived, **{d: c for d, c in manual.items() if c is not None}}


def prepare_demo():
    schedule_path = FIXTURE.with_name("demo-schedule.json")
    plan = json.loads(schedule_path.read_text(encoding="utf8"))
    if (plan["schema_version"], plan["mode"], plan["analysis_tz"]) != ("1.0", "synthetic", "Asia/Shanghai"):
        raise ValueError("演示排班格式无效")
    utc_time(plan["demo_clock"])
    for day, kind in plan["contexts"].items():
        date.fromisoformat(day)
        if kind not in CONTEXTS:
            raise ValueError("演示情境无效")
    for event in plan["events"]:
        event_values(**event)
    for start, end in plan["available"]:
        interval(start, end)
    for block in plan["busy"]:
        interval(block["start"], block["end"])
    if type(plan["requested_minutes"]) is not int or plan["requested_minutes"] <= 0:
        raise ValueError("演示时长无效")
    settings = dict(mode="synthetic", format="JSON", file="demo-records.json", analysis_tz=plan["analysis_tz"],
                    date_from=str(DEMO_DAY - timedelta(days=28)), date_to=str(DEMO_DAY))
    output, digest = read_selected(settings["file"], **{k: settings[k] for k in ("analysis_tz","date_from","date_to")})
    if output["report"]["invalid"] or output["report"]["duplicate"] or output["report"]["mode"] != "synthetic":
        raise ValueError("完整演示健康记录校验失败")
    settings.update(sha256=digest, schedule_sha256=fingerprint(schedule_path),
                    planning={k: plan[k] for k in ("available","busy","requested_minutes","demo_clock")})
    return output["records"], plan, settings


def load_demo(db, profile, expected, token, prepared):
    rows, plan, settings = prepared
    # A second click with a different ticket still has the original revision.
    with edit(db, profile, "synthetic", expected):
        ws.delete_data(db, profile)
        ws._insert_batch(db, profile, token, rows, settings)
        from storage.planning import seed
        seed(db, profile, settings["planning"])
        db.executemany("INSERT INTO context_history(profile_id,day,context,origin) VALUES (?,?,?,'fixture')",
                       [(profile, day, kind) for day, kind in plan["contexts"].items()])
        for e in plan["events"]:
            db.execute("INSERT INTO events VALUES (?,?,?,?,?,?)", (profile, uuid4().hex, *event_values(**e)))


def import_bounds(db, profile):
    # Re-importing a wider window of the identical file fills in a former boundary.
    batches = defaultdict(list)
    for token, raw in db.execute("SELECT token,settings FROM imports WHERE profile_id=?", (profile,)):
        s = json.loads(raw)
        if not all(s.get(k) for k in ("date_from","date_to","analysis_tz")):
            continue
        zone = ZoneInfo(s["analysis_tz"])
        lo = midnight(date.fromisoformat(s["date_from"]) - timedelta(days=1), zone)
        hi = midnight(date.fromisoformat(s["date_to"]) + timedelta(days=1), zone)
        identity = (s.get("sha256", token), tuple(sorted(s.get("aliases", {}).items())))
        batches[identity].append((lo, hi, token))
    result = {}
    for windows in batches.values():
        merged = []
        for lo, hi, token in sorted(windows):
            if merged and lo <= merged[-1][1]:
                left, right, tokens = merged[-1]
                tokens.append(token)
                merged[-1] = left, max(hi, right), tokens
            else:
                merged.append((lo, hi, [token]))
        for lo, hi, tokens in merged:
            result.update({token: (lo, hi) for token in tokens})
    return result
