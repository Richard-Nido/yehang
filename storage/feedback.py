"""Version-bound, self-reported execution and seven-local-day review."""
from datetime import timedelta
from zoneinfo import ZoneInfo

from core import planner
from storage import schedule

STATES = ("未反馈", "完成", "部分完成", "跳过")
TABLES = ("feedback", "explanation_replays")


def initialize(db):
    db.execute("""CREATE TABLE feedback (
        profile_id TEXT NOT NULL, plan_id TEXT NOT NULL, version INTEGER NOT NULL,
        revision INTEGER NOT NULL, status TEXT NOT NULL CHECK(status IN ('未反馈','完成','部分完成','跳过')),
        actual_start TEXT, actual_end TEXT, fatigue INTEGER CHECK(fatigue BETWEEN 1 AND 5),
        note TEXT NOT NULL, PRIMARY KEY(profile_id,plan_id),
        CHECK ((actual_start IS NULL) = (actual_end IS NULL)),
        FOREIGN KEY(profile_id,plan_id,version) REFERENCES plans(profile_id,plan_id,version))""")
    db.execute("""CREATE TABLE explanation_replays (
        profile_id TEXT PRIMARY KEY REFERENCES profiles, payload TEXT NOT NULL)""")


def get(db, profile, plan_id):
    row = db.execute("SELECT * FROM feedback WHERE profile_id=? AND plan_id=?", (profile, plan_id)).fetchone()
    return dict(row) if row else {}


def save(db, profile, mode, plan_id, displayed_version, version, expected, status,
         actual_start=None, actual_end=None, fatigue=None, note=""):
    if status not in STATES:
        raise ValueError("请选择执行状态")
    start, end = actual_start or None, actual_end or None
    if bool(start) != bool(end):
        raise ValueError("实际开始和实际结束须成对填写或同时留空")
    if start:
        planner.interval(start, end)
    if fatigue is not None and (type(fatigue) is not int or not 1 <= fatigue <= 5):
        raise ValueError("自报疲劳须为空或 1–5 的整数")
    if status == "未反馈" and (start or fatigue is not None or note.strip()):
        raise ValueError("请选择执行状态，或清空实际时间、疲劳及备注以恢复未反馈")
    fields = ("version", "status", "actual_start", "actual_end", "fatigue", "note")
    values = (version, status, start, end, fatigue, note.strip())
    with schedule.locked_profile(db, profile, mode):
        current = db.execute("SELECT max(version) FROM plans WHERE profile_id=? AND plan_id=?",
                             (profile, plan_id)).fetchone()[0]
        if current is None or current != displayed_version:
            raise ValueError("计划版本已变化，请重新核对计划与反馈")
        old = get(db, profile, plan_id)
        if version not in (current, old.get("version", current)):
            raise ValueError("请选择已核对的反馈基准版本")
        if old and tuple(old[k] for k in fields) == values:
            return
        if old.get("revision", 0) != expected:
            raise ValueError("另一会话已更正反馈，请重新核对后保存")
        if not old and status == "未反馈":
            return
        db.execute("""INSERT INTO feedback
            (profile_id,plan_id,revision,version,status,actual_start,actual_end,fatigue,note)
            VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(profile_id,plan_id) DO UPDATE SET
            revision=excluded.revision,version=excluded.version,status=excluded.status,
            actual_start=excluded.actual_start,actual_end=excluded.actual_end,
            fatigue=excluded.fatigue,note=excluded.note""", (profile, plan_id, expected + 1, *values))
        db.execute("UPDATE profiles SET revision=revision+1 WHERE profile_id=?", (profile,))


def week(db, profile, end_day, zone_name):
    zone = ZoneInfo(zone_name)
    first = end_day - timedelta(days=6)
    records = db.execute("""WITH latest AS (
        SELECT plan_id,max(version) AS version FROM plans WHERE profile_id=? GROUP BY plan_id)
        SELECT p.*,coalesce(f.status,'未反馈') AS status,f.actual_start,f.actual_end,f.fatigue,f.note
        FROM latest l LEFT JOIN feedback f ON f.profile_id=? AND f.plan_id=l.plan_id
        JOIN plans p ON p.profile_id=? AND p.plan_id=l.plan_id AND p.version=CASE
            WHEN f.status!='未反馈' THEN f.version ELSE l.version END""", (profile, profile, profile))
    rows = []
    counts = dict.fromkeys(STATES, 0)
    for record in records:
        row = dict(record)
        start, end = planner.interval(row["start"], row["end"])
        if not first <= start.astimezone(zone).date() <= end_day:
            continue
        actual = difference = None
        if row["actual_start"]:
            left, right = planner.interval(row["actual_start"], row["actual_end"])
            actual = (right-left) / timedelta(minutes=1)
            difference = actual - (end-start) / timedelta(minutes=1)
        rows.append(dict(row, actual_minutes=actual, difference=difference))
        counts[row["status"]] += 1
    rows.sort(key=lambda r: (planner.endpoint(r["start"], "计划开始"), r["plan_id"]))
    return rows, counts
