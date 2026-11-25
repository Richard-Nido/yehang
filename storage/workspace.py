"""Profile-scoped A2 workspace and transactional upgrade from the A1 schema."""
import json
import os
import sqlite3
from collections import Counter
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path

from core.demo import fixture_family
from core.sleep import utc_time

DEMO_PROFILE = "synthetic-demo"
DEFAULT_DB = Path(__file__).resolve().parents[1] / ".local" / "workspace.sqlite3"
TABLES = ("imports", "samples", "identities", "conflicts", "sample_overrides")
FIELDS = ("id", "metric", "source", "value", "unit", "start", "end")


@contextmanager
def open_workspace():
    path = Path(os.environ.get("YEHANG_DB_PATH", DEFAULT_DB))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    try:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        initialize(db)
        yield db
    finally:
        db.close()


def _legacy_rows(cursor):
    for item in cursor:
        row = dict(item)
        if row["metric"] != "sleep":
            try:
                value = Decimal(row["value"])
                if not value.is_finite():
                    raise ValueError("原库含非有限数值，已停止升级")
                row["value"] = int(value) if value == value.to_integral_value() else float(value)
            except InvalidOperation as error:
                raise ValueError("原库数值无法转换，已停止升级") from error
        yield row


def initialize(db):
    from storage import feedback, planning
    from storage.schedule import initialize as initialize_schedule
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version == 5:
        return
    with db:
        db.execute("BEGIN IMMEDIATE")
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version == 5:
            return
        if version in (2, 3, 4):
            if version == 2:
                initialize_schedule(db)
            if version < 4:
                planning.initialize(db)
            feedback.initialize(db)
            db.execute("PRAGMA user_version = 5")
            return
        if version != 0:
            raise ValueError("未知的数据库版本")
        legacy = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='profiles'").fetchone()
        if legacy:
            if db.execute("PRAGMA foreign_key_check").fetchone():
                raise ValueError("原库含失去关联的样本或批次，已停止升级")
            db.execute("ALTER TABLE profiles ADD COLUMN revision INTEGER NOT NULL DEFAULT 0")
            db.execute("ALTER TABLE samples RENAME TO a1_samples")
            db.execute("ALTER TABLE imports RENAME TO a1_imports")
        else:
            db.execute("""CREATE TABLE profiles (profile_id TEXT PRIMARY KEY, mode TEXT NOT NULL,
                       revision INTEGER NOT NULL DEFAULT 0)""")
        db.execute("""CREATE TABLE imports (
            profile_id TEXT NOT NULL REFERENCES profiles, token TEXT NOT NULL, settings TEXT NOT NULL,
            added INTEGER NOT NULL DEFAULT 0, duplicate INTEGER NOT NULL DEFAULT 0,
            conflict INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(profile_id,token))""")
        db.execute("""CREATE TABLE samples (
            profile_id TEXT NOT NULL, content TEXT NOT NULL, token TEXT NOT NULL, id TEXT NOT NULL,
            metric TEXT NOT NULL, source TEXT NOT NULL, raw_source TEXT NOT NULL, value NOT NULL,
            unit TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL, PRIMARY KEY(profile_id,content),
            FOREIGN KEY(profile_id,token) REFERENCES imports ON DELETE CASCADE)""")
        db.execute("""CREATE TABLE identities (
            profile_id TEXT NOT NULL, source TEXT NOT NULL, id TEXT NOT NULL, content TEXT NOT NULL,
            PRIMARY KEY(profile_id,source,id),
            FOREIGN KEY(profile_id,content) REFERENCES samples ON DELETE CASCADE)""")
        db.execute("""CREATE TABLE conflicts (
            profile_id TEXT NOT NULL, token TEXT NOT NULL, source TEXT NOT NULL,
            id TEXT NOT NULL, incoming TEXT NOT NULL,
            FOREIGN KEY(profile_id,token) REFERENCES imports ON DELETE CASCADE,
            FOREIGN KEY(profile_id,source,id) REFERENCES identities ON DELETE CASCADE)""")
        db.execute("""CREATE TABLE sample_overrides (
            profile_id TEXT NOT NULL, content TEXT NOT NULL, excluded INTEGER NOT NULL,
            reason TEXT NOT NULL, changed_at TEXT NOT NULL, PRIMARY KEY(profile_id,content),
            FOREIGN KEY(profile_id,content) REFERENCES samples ON DELETE CASCADE)""")
        if legacy:
            for profile, batch in db.execute("SELECT profile_id,batch FROM a1_imports"):
                rows = db.execute("SELECT * FROM a1_samples WHERE profile_id=? AND batch=?", (profile, batch))
                _insert_batch(db, profile, batch, _legacy_rows(rows), {"file": batch})
            db.execute("DROP TABLE a1_samples")
            db.execute("DROP TABLE a1_imports")
        db.execute("INSERT INTO profiles(profile_id,mode) VALUES (?, 'synthetic') ON CONFLICT DO NOTHING",
                   (DEMO_PROFILE,))
        if db.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("迁移后的外键校验失败")
        initialize_schedule(db)
        planning.initialize(db)
        feedback.initialize(db)
        db.execute("PRAGMA user_version = 5")


def content_key(row):
    value = row["value"]
    if row["metric"] != "sleep":
        number = Decimal(str(value))
        if not number.is_finite():
            raise ValueError("数值必须有限")
        value = format(number.normalize(), "f") if number else "0"
    return json.dumps([row["source"], row["metric"], utc_time(row["start"]).isoformat(),
                       utc_time(row["end"]).isoformat(), value, row["unit"]], ensure_ascii=False)


def classify(db, profile, rows, aliases):
    # Earlier rows in this preview participate even before anything has been written.
    identities, contents = {}, set()
    for raw in rows:
        row = {k: raw[k] for k in FIELDS}
        row["source"] = aliases.get(raw["source"], raw["source"])
        row["raw_source"] = raw["source"]
        content = content_key(row)
        new_ids = []
        for external_id in (row["id"], *raw.get("alternate_ids", [])):
            identity = (row["source"], external_id)
            previous = identities.get(identity)
            if previous is None:
                found = db.execute("SELECT content FROM identities WHERE profile_id=? AND source=? AND id=?",
                                   (profile, *identity)).fetchone()
                previous = found[0] if found else None
            if previous is not None and previous != content:
                yield "conflict", dict(row, id=external_id), content, []
                break
            if previous is None:
                new_ids.append(external_id)
        else:
            existing = content in contents or db.execute(
                "SELECT 1 FROM samples WHERE profile_id=? AND content=?", (profile, content)).fetchone()
            for external_id in new_ids:
                identities[(row["source"], external_id)] = content
            contents.add(content)
            yield "duplicate" if existing else "added", row, content, new_ids


def estimate(db, profile, rows, aliases):
    return Counter(action for action, *_ in classify(db, profile, rows, aliases))


def _insert_batch(db, profile, token, rows, settings):
    db.execute("INSERT INTO imports(profile_id,token,settings) VALUES (?,?,?)",
               (profile, token, json.dumps(settings, ensure_ascii=False)))
    counts = Counter()
    for action, row, content, new_ids in classify(db, profile, rows, settings.get("aliases", {})):
        params = dict(row, profile=profile, token=token, content=content)
        if action == "added":
            db.execute("""INSERT INTO samples VALUES (:profile,:content,:token,:id,:metric,:source,
                       :raw_source,:value,:unit,:start,:end)""", params)
        db.executemany("INSERT INTO identities VALUES (?,?,?,?)",
                       ((profile, row["source"], external_id, content) for external_id in new_ids))
        if action == "conflict":
            db.execute("INSERT INTO conflicts VALUES (:profile,:token,:source,:id,:incoming)",
                       dict(params, incoming=json.dumps(row, ensure_ascii=False)))
        counts[action] += 1
    result = tuple(counts[k] for k in ("added", "duplicate", "conflict"))
    db.execute("UPDATE imports SET added=?,duplicate=?,conflict=? WHERE profile_id=? AND token=?",
               (*result, profile, token))
    return result


def source_map(db, profile):
    row = db.execute("""SELECT settings FROM imports WHERE profile_id=?
                     AND json_type(settings,'$.source_map')='object' ORDER BY rowid DESC LIMIT 1""",
                     (profile,)).fetchone()
    if row:
        return json.loads(row[0])["source_map"]
    reserved = [r[0] for r in db.execute("SELECT DISTINCT raw_source FROM samples WHERE profile_id=? ORDER BY 1",
                                         (profile,))]
    return {"version": 1, "sources": {}, "reserved": reserved} if reserved else None


def confirm(db, profile, token, rows, settings, *, previous_map=None):
    with db:
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute("SELECT added,duplicate,conflict FROM imports WHERE profile_id=? AND token=?",
                              (profile, token)).fetchone()
        if previous:
            return tuple(previous)
        if "source_map" in settings:
            current = source_map(db, profile)
            if current != previous_map and current != settings["source_map"]:
                raise ValueError("档案的来源映射已更新，请重新预览")
        family = fixture_family(settings)
        if family:
            other = "full" if family == "crossnight" else "crossnight"
            if any(fixture_family(json.loads(r[0])) == other for r in db.execute(
                    "SELECT settings FROM imports WHERE profile_id=?", (profile,))):
                raise ValueError("跨夜小样例与完整演示使用独立档案，请切换档案或确认重置")
        mode = settings.get("mode", "synthetic")
        db.execute("INSERT INTO profiles(profile_id,mode) VALUES (?,?) ON CONFLICT DO NOTHING",
                   (profile, mode))
        if db.execute("SELECT mode FROM profiles WHERE profile_id=?", (profile,)).fetchone()[0] != mode:
            raise ValueError("数据与档案模式不一致")
        counts = _insert_batch(db, profile, token, rows, settings)
        db.executemany("UPDATE primary_sources SET source=? WHERE profile_id=? AND metric=?",
                       [(src, profile, metric) for metric, src in settings.get("primary", {}).items()])
        db.execute("UPDATE profiles SET revision=revision+1 WHERE profile_id=?", (profile,))
        return counts


def details(db, profile):
    return [dict(row) for row in db.execute("""SELECT s.*, COALESCE(o.excluded,0) AS excluded,
            o.reason, o.changed_at FROM samples s LEFT JOIN sample_overrides o USING(profile_id,content)
            WHERE s.profile_id=? ORDER BY julianday(start),id,source""", (profile,))]


def read_samples(db, profile):
    return [{k: r[k] for k in FIELDS} for r in details(db, profile)]


def override(db, profile, content, excluded, reason):
    if excluded and not reason.strip():
        raise ValueError("请填写排除理由")
    with db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("""INSERT INTO sample_overrides VALUES (?,?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            ON CONFLICT(profile_id,content) DO UPDATE SET excluded=excluded.excluded,
            reason=CASE WHEN excluded.reason='' THEN sample_overrides.reason ELSE excluded.reason END,
            changed_at=excluded.changed_at""", (profile, content, int(excluded), reason.strip()))
        db.execute("UPDATE profiles SET revision=revision+1 WHERE profile_id=?", (profile,))


def counts(db, profile, *, include_schedule=False):
    from storage.feedback import TABLES as feedback_tables
    from storage.planning import TABLES as planning_tables
    from storage.schedule import TABLES as schedule_tables
    return {t: db.execute(f"SELECT count(*) FROM {t} WHERE profile_id=?", (profile,)).fetchone()[0]
            for t in (TABLES + schedule_tables + planning_tables + feedback_tables if include_schedule else TABLES)}


def revision(db, profile):
    row = db.execute("SELECT revision FROM profiles WHERE profile_id=?", (profile,)).fetchone()
    return row[0] if row else 0


def delete_data(db, profile):
    from storage.feedback import TABLES as feedback_tables
    from storage.planning import TABLES as planning_tables
    from storage.schedule import TABLES as schedule_tables
    for table in ("imports", *schedule_tables, *feedback_tables, *planning_tables):
        db.execute(f"DELETE FROM {table} WHERE profile_id=?", (profile,))


def clear(db, profile, expected_revision):
    with db:
        db.execute("BEGIN IMMEDIATE")
        if revision(db, profile) != expected_revision:
            raise ValueError("档案数据已变化，请重新核对清空数量")
        delete_data(db, profile)
        db.execute("UPDATE profiles SET revision=revision+1 WHERE profile_id=?", (profile,))
