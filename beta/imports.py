"""Stream one export into the existing transactional, content-addressed store."""

from collections import Counter
from itertools import islice
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import ijson
from adapters.health import ALIAS, _SourceAliases, _xml_records, _digest, record_key
from adapters.field_mapping import TYPE_MAP, normalize_value, RecordError
from beta.timebase import local
from storage import workspace as ws
from storage.schedule import locked_profile


def json_rows(path):
    header = {}
    found = False
    with path.open("rb") as stream:
        if stream.read(3) != b"\xef\xbb\xbf":
            stream.seek(0)
        events = iter(ijson.parse(stream, use_float=True))
        for prefix, event, value in events:
            if (
                prefix == ""
                and event == "map_key"
                and value not in {"records", "schema_version", "mode"}
            ):
                raise ValueError("健康 JSON 含有不支持的顶层字段。")
            if prefix in {"schema_version", "mode"} and event == "string":
                header[prefix] = value
            if prefix == "records" and event == "start_array":
                found = True
            if prefix == "records.item" and event == "start_map":
                obj = ijson.ObjectBuilder()
                obj.event(event, value)
                for p, e, v in events:
                    obj.event(e, v)
                    if p == prefix and e == "end_map":
                        break
                yield obj.value
            elif prefix == "records.item":
                raise ValueError("健康记录应为对象。")
    if (
        not found
        or header.get("schema_version") != "1.0"
        or header.get("mode") != "personal"
    ):
        raise ValueError(
            "请选择个人健康 JSON（schema_version 1.0、mode personal）或 Apple 健康 XML。"
        )


def normalized(path, aliases, counts):
    xml = path.suffix == ".xml"
    metrics = set(TYPE_MAP.values())
    for raw in _xml_records(path) if xml else json_rows(path):
        metric = TYPE_MAP.get(raw.get("type")) if xml else raw.get("metric")
        if metric not in metrics:
            continue
        try:
            start = local(raw["startDate" if xml else "start"])
            end = local(raw["endDate" if xml else "end"])
            if end < start or (end == start and metric == "sleep"):
                raise ValueError()
            value, unit = normalize_value(
                metric, raw.get("value"), raw.get("unit"), xml=xml
            )
            if xml:
                source, _ = aliases.xml_alias(raw)
            else:
                source = raw["source"]
                if (
                    not ALIAS.fullmatch(source)
                    or not isinstance(raw["id"], str)
                    or not raw["id"].strip()
                ):
                    raise ValueError()
                aliases.reserve(source)
            row = dict(
                metric=metric,
                source=source,
                value=value,
                unit=unit,
                start=start.isoformat(),
                end=end.isoformat(),
            )
            row["id"] = "xml_" + _digest(record_key(row)) if xml else raw["id"]
            yield row
        except (RecordError, KeyError, ValueError, TypeError, OverflowError):
            counts["invalid"] += 1


def import_health(path, db, profile):
    token = uuid4().hex
    counts = Counter(added=0, duplicate=0, invalid=0, conflict=0)
    with locked_profile(db, profile, "personal"), TemporaryDirectory() as tmp:
        mapping = Path(tmp) / "map.json"
        prior = ws.source_map(db, profile)
        if prior:
            mapping.write_text(json.dumps(prior), encoding="utf8")
        aliases = _SourceAliases(mapping)
        db.execute(
            "INSERT INTO imports(profile_id,token,settings) VALUES (?,?,?)",
            (profile, token, "{}"),
        )
        rows = normalized(path, aliases, counts)
        while batch := list(islice(rows, 1024)):
            for action, row, content, ids in ws.classify(db, profile, batch, {}):
                counts[action] += 1
                if action == "added":
                    db.execute(
                        "INSERT INTO samples VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            profile,
                            content,
                            token,
                            row["id"],
                            row["metric"],
                            row["source"],
                            row["source"],
                            row["value"],
                            row["unit"],
                            row["start"],
                            row["end"],
                        ),
                    )
                db.executemany(
                    "INSERT INTO identities VALUES (?,?,?,?)",
                    ((profile, row["source"], i, content) for i in ids),
                )
        aliases.save()
        settings = {"mode": "personal", "analysis_tz": "Asia/Shanghai"}
        if mapping.exists():
            settings["source_map"] = json.loads(mapping.read_text(encoding="utf8"))
        db.execute(
            "UPDATE imports SET settings=?,added=?,duplicate=?,conflict=? WHERE profile_id=? AND token=?",
            (
                json.dumps(settings),
                counts["added"],
                counts["duplicate"],
                counts["conflict"],
                profile,
                token,
            ),
        )
        db.execute(
            "UPDATE profiles SET revision=revision+1 WHERE profile_id=?", (profile,)
        )
    return dict(counts)
