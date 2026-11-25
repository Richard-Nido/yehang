"""B2：Apple 健康 XML / v1 JSON 的本地文件导入器，无数据库写入。

运行：python -m adapters.health FILE --date-from YYYY-MM-DD --date-to YYYY-MM-DD
"""

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import tempfile
from time import perf_counter
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .field_mapping import TYPE_MAP, RecordError, normalize_value, parse_time


METRICS = tuple(TYPE_MAP.values())
ALIAS = re.compile(r"^(watch|phone|other)_[1-9][0-9]*$")
UTC = timezone.utc


def record_key(row):
    """文件内和 A2 数据库可共用的内容身份，不依赖输入 ID 或时间写法。"""
    value = row["value"] if row["metric"] == "sleep" else float(row["value"] or 0).hex()
    return (row["source"], row["metric"],
            parse_time(row["start"]).astimezone(UTC).isoformat(),
            parse_time(row["end"]).astimezone(UTC).isoformat(), value, row["unit"])


def _digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


class _SourceAliases:
    """仅保存来源身份摘要与匿名别名，不保存设备名、序列号或完整 device 字段。"""

    def __init__(self, path):
        self.path = path
        self.entries = {}
        self.used = set()
        self.changed = False
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data["version"] != 1 or not isinstance(data["sources"], dict):
                    raise ValueError
                for token, alias in data["sources"].items():
                    if not re.fullmatch(r"[0-9a-f]{64}", token) or not isinstance(alias, str) or not ALIAS.fullmatch(alias):
                        raise ValueError
                reserved = data.get("reserved", [])
                if not isinstance(reserved, list) or any(not isinstance(a, str) or not ALIAS.fullmatch(a) for a in reserved):
                    raise ValueError
                self.entries = data["sources"]
                self.used = set(reserved) | set(self.entries.values())
            except (KeyError, ValueError, TypeError, OSError):
                raise ValueError("本机来源映射文件无效，请保留原件后核对，不能自动重建别名。") from None

    def reserve(self, alias):
        if alias not in self.used:
            self.used.add(alias)
            self.changed = True

    def xml_alias(self, attrs):
        name = attrs.get("sourceName", "").strip()
        if not name:
            raise RecordError("missing_source")
        if ALIAS.fullmatch(name):
            self.reserve(name)
            return name, False
        device = attrs.get("device", "")
        # device 中的内存地址和软件版本随导出变化，不用它们标识来源。
        fields = []
        for key in ("manufacturer", "model", "hardware"):
            match = re.search(r"(?:^|[,<])\s*" + key + r":\s*(.*?)(?=,\s*[A-Za-z][A-Za-z ]*:|>|$)", device, re.I)
            fields.append(match.group(1).strip() if match else "")
        hint = " ".join([name, *fields]).lower()
        kind = "watch" if "watch" in hint or "手表" in hint else "phone" if "iphone" in hint else "other"
        token = _digest([name, *fields])
        alias = self.entries.get(token)
        if alias is None:
            index = 1
            while f"{kind}_{index}" in self.used:
                index += 1
            alias = f"{kind}_{index}"
            self.entries[token] = alias
            self.reserve(alias)
            self.changed = True
        return alias, True

    def save(self):
        if not self.changed:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "sources": self.entries, "reserved": sorted(self.used)}
        # 临时文件关闭后替换，兼容 Windows；解析失败不会调用这里。
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent, delete=False) as stream:
            tmp = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2)
        try:
            tmp.replace(self.path)
        finally:
            tmp.unlink(missing_ok=True)


def _xml_records(path):
    """只读取 HealthData 的直接 Record 子元素，并释放已处理节点。"""
    try:
        with path.open("rb") as stream:
            depth = 0
            root = None
            for event, el in ET.iterparse(stream, events=("start", "end")):
                tag = el.tag.rsplit("}", 1)[-1]
                if event == "start":
                    depth += 1
                    if root is None:
                        if tag != "HealthData":
                            raise ValueError("请选择 HealthData 主 XML，不能导入临床文书 XML。")
                        root = el
                    continue
                if depth == 2 and tag == "Record":
                    yield el.attrib.copy()
                if depth == 2:
                    root.remove(el)
                el.clear()
                depth -= 1
            if root is None:
                raise ValueError("XML 内容为空。")
    except ET.ParseError:
        raise ValueError("XML 无法完整解析，未返回部分结果。") from None


def _json_records(path):
    try:
        with path.open(encoding="utf-8-sig") as stream:
            data = json.load(stream)
    except (ValueError, UnicodeError):
        raise ValueError("JSON 无法完整解析。") from None
    if not isinstance(data, dict) or data.get("schema_version") != "1.0":
        raise ValueError('仅支持 schema_version 为字符串 "1.0" 的健康 JSON。')
    if not isinstance(data.get("mode"), str) or data["mode"] not in {"synthetic", "personal"} or not isinstance(data.get("records"), list):
        raise ValueError("JSON 须包含合法 mode 和 records 数组；排班文件不能交给健康导入器。")
    if set(data) - {"schema_version", "mode", "records"}:
        raise ValueError("JSON 顶层仅接收 schema_version、mode、records，不能包含个人资料。")
    return data["records"], data["mode"]


def _dates(date_from, date_to, analysis_tz):
    try:
        zone = ZoneInfo(analysis_tz)
        first, last = date.fromisoformat(date_from), date.fromisoformat(date_to)
        if last < first:
            raise ValueError
        lower = datetime.combine(first - timedelta(days=1), time.min, zone).astimezone(UTC)
        requested = datetime.combine(first, time.min, zone).astimezone(UTC)
        upper = datetime.combine(last + timedelta(days=1), time.min, zone).astimezone(UTC)
    except (ValueError, TypeError, OverflowError, ZoneInfoNotFoundError):
        raise ValueError("请提供合法时区和含首尾的 ISO 日期范围。Windows 缺时区库时需安装 tzdata。") from None
    return zone, first, last, lower, requested, upper


def read_export(path, *, analysis_tz="Asia/Shanghai", date_from, date_to, source_map_path=None, include_identity_aliases=False):
    """返回完整记录和质量报告；只写本机匿名来源映射，不写业务数据库。

    包含前一个本地日的上下文，A 按醒来日聚合后筛选日期。
    source_map_path 可由 A 指定为档案独立的 .local/.../sources.json；
    默认保存在输入文件所在目录的 .local/health_sources.json。
    include_identity_aliases=True 时，内容相同且外部 ID 不同的行在首条记录的
    alternate_ids 中保留附加 ID，供存储层跨批次检查身份冲突。默认输出仍为 v1 字段。
    """
    zone, first, last, lower, requested, upper = _dates(date_from, date_to, analysis_tz)
    path = Path(path)
    if path.suffix.lower() not in {".xml", ".json"}:
        raise ValueError("仅支持主 XML 或 v1 JSON；ZIP 请先在本机解压。")
    aliases = _SourceAliases(Path(source_map_path) if source_map_path is not None else path.parent / ".local" / "health_sources.json")
    report = {"read_target": 0, "accepted": 0, "duplicate": 0, "invalid": 0,
              "ignored_type": 0, "by_metric": dict.fromkeys(METRICS, 0), "warnings": [],
              "out_of_range": 0, "invalid_reasons": {}, "id_conflict": 0,
              "analysis_tz": analysis_tz, "date_from": first.isoformat(), "date_to": last.isoformat(),
              "context_from": (first - timedelta(days=1)).isoformat()}
    result, seen, identities = [], {}, {}
    errors = Counter()
    needs_confirmation = set()
    source_counts = {metric: Counter() for metric in METRICS}
    sleep_stages = defaultdict(Counter)
    coverage = defaultdict(set)
    is_xml = path.suffix.lower() == ".xml"
    try:
        if is_xml:
            rows, mode = _xml_records(path), None
        else:
            rows, mode = _json_records(path)
        for attrs in rows:
            if not isinstance(attrs, dict):
                report["read_target"] += 1
                report["invalid"] += 1
                errors["invalid_row"] += 1
                continue
            if is_xml:
                raw_type = attrs.get("type")
                metric = TYPE_MAP.get(raw_type) if isinstance(raw_type, str) else None
                if isinstance(raw_type, str) and metric is None:
                    report["ignored_type"] += 1
                    continue
            else:
                metric = attrs.get("metric")
            if not is_xml and isinstance(metric, str) and metric not in METRICS:
                report["ignored_type"] += 1
                continue
            counted = False
            try:
                if not isinstance(metric, str) or metric not in METRICS:
                    raise RecordError("invalid_metric")
                start = parse_time(attrs.get("startDate" if is_xml else "start"))
                end = parse_time(attrs.get("endDate" if is_xml else "end"))
                a, b = start.astimezone(UTC), end.astimezone(UTC)
                if b < a or (metric == "sleep" and b == a):
                    raise RecordError("invalid_interval")
                intersects = lower <= a < upper if a == b else a < upper and b > lower
                if not intersects:
                    report["out_of_range"] += 1
                    continue
                report["read_target"] += 1
                counted = True
                value, unit = normalize_value(metric, attrs.get("value"), attrs.get("unit"), xml=is_xml)
                if is_xml:
                    source, confirm = aliases.xml_alias(attrs)
                    row_id = None
                else:
                    source, row_id = attrs.get("source"), attrs.get("id")
                    if not isinstance(source, str) or not ALIAS.fullmatch(source):
                        raise RecordError("invalid_source_alias")
                    if not isinstance(row_id, str) or not row_id.strip():
                        raise RecordError("invalid_id")
                    confirm = False
                    aliases.reserve(source)
                row = {"id": row_id, "metric": metric, "start": start.isoformat(),
                       "end": end.isoformat(), "source": source, "value": value, "unit": unit}
                key = record_key(row)
                if is_xml:
                    row["id"] = "xml_" + _digest(key)
                identity = (source, row["id"])
                if identity in identities and identities[identity] != key:
                    report["id_conflict"] += 1
                    raise RecordError("id_conflict")
                new_identity = identity not in identities
                identities[identity] = key
                if key in seen:
                    if new_identity and include_identity_aliases:
                        seen[key].setdefault("alternate_ids", []).append(row["id"])
                    report["duplicate"] += 1
                    continue
                seen[key] = row
                result.append(row)
                report["accepted"] += 1
                report["by_metric"][metric] += 1
                source_counts[metric][source] += 1
                if metric == "sleep":
                    sleep_stages[source][value] += 1
                if confirm:
                    needs_confirmation.add(source)
                # 覆盖只计用户请求范围；额外一天的上下文不算成当日已有数据。
                if a == b:
                    if requested <= a < upper:
                        coverage[(metric, source)].add(a.astimezone(zone).date())
                elif b > requested:
                    day = max(a, requested).astimezone(zone).date()
                    until = (min(b, upper) - timedelta(microseconds=1)).astimezone(zone).date()
                    while day <= until:
                        coverage[(metric, source)].add(day)
                        day += timedelta(days=1)
            except (RecordError, OverflowError) as exc:
                if not counted:
                    report["read_target"] += 1
                report["invalid"] += 1
                errors[exc.code if isinstance(exc, RecordError) else "invalid_time"] += 1
        aliases.save()
    except OSError:
        raise ValueError("无法读取输入文件或保存本机来源映射，请检查路径和权限。") from None

    report["mode"] = mode
    report["invalid_reasons"] = dict(sorted(errors.items()))
    report["source_counts"] = {m: dict(sorted(counts.items())) for m, counts in source_counts.items()}
    report["sleep_stage_counts"] = {s: dict(sorted(stages.items())) for s, stages in sorted(sleep_stages.items())}
    report["suggested_sources"] = {m: min(counts, key=lambda s: (-counts[s], s)) if counts else None for m, counts in source_counts.items()}
    report["sources_needing_confirmation"] = sorted(needs_confirmation)
    report["coverage"] = {
        m: {source: {"days_with_records": len(coverage[(m, source)]),
                     "first_date": min(coverage[(m, source)]).isoformat() if coverage[(m, source)] else None,
                     "last_date": max(coverage[(m, source)]).isoformat() if coverage[(m, source)] else None}
            for source in sorted(counts)}
        for m, counts in source_counts.items()
    }
    report["missing_metrics"] = [m for m in METRICS if not any(coverage[(m, s)] for s in source_counts[m])]
    if report["missing_metrics"]:
        report["warnings"].append("请求范围内部分指标无有效记录；缺失不能填成零。")
    if report["invalid"]:
        report["warnings"].append("已隔离无效行，原因与数量见 invalid_reasons；无法判断日期的坏行也计入 invalid。")
    if report["id_conflict"]:
        report["warnings"].append("发现同来源同 ID 内容冲突：首条保留，后续冲突行隔离；确认入库前须核对。")
    if needs_confirmation:
        report["warnings"].append("XML 来源仅为本机匿名标签，须核对主要来源；跨格式不能仅凭别名相同认定为同一设备。")
    if any(not (set(stages) & {"asleep", "core", "deep", "rem"}) for stages in sleep_stages.values()):
        report["warnings"].append("部分睡眠来源只有卧床或清醒记录，不能据此计算已睡时长或填为零。")
    report["warnings"].append("records 含前一日本地日上下文；聚合后须按分析日过滤，边界部分覆盖日不得纳入基线。")
    return {"records": result, "report": report}


def main():
    parser = argparse.ArgumentParser(description="本机健康文件预览：只输出质量计数，不输出健康记录值或设备原名。")
    parser.add_argument("path", type=Path)
    parser.add_argument("--date-from", required=True)
    parser.add_argument("--date-to", required=True)
    parser.add_argument("--analysis-tz", default="Asia/Shanghai")
    parser.add_argument("--source-map", type=Path)
    parser.add_argument("--report", type=Path, help="将质量报告保存在本机；不输出原始记录")
    args = parser.parse_args()
    began = perf_counter()
    try:
        data = read_export(args.path, analysis_tz=args.analysis_tz, date_from=args.date_from,
                           date_to=args.date_to, source_map_path=args.source_map)
    except ValueError as exc:
        parser.exit(2, str(exc) + "\n")
    report = data["report"]
    report["elapsed_seconds"] = round(perf_counter() - began, 3)
    report["file_size_mib"] = round(args.path.stat().st_size / 1024**2, 1)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
