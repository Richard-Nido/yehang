"""Daily features for one profile, with all elapsed-time arithmetic in UTC."""
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from statistics import median
from zoneinfo import ZoneInfo

from core.sleep import MAX_GAP, asleep_intervals, group_sleep, utc_time

DAY = timedelta(days=1)
METRICS = ("sleep", "resting_hr", "hrv_sdnn", "heart_rate", "steps", "active_energy", "onset")
UNITS = dict(sleep="分钟", resting_hr="bpm", hrv_sdnn="ms", heart_rate="bpm",
             steps="步", active_energy="kcal", onset="分钟")
LABELS = dict(sleep="睡眠", resting_hr="静息心率", hrv_sdnn="HRV-SDNN", heart_rate="心率",
              steps="步数", active_energy="活动能量", onset="主段入睡时间")


@dataclass
class Feature:
    value: float | None = None
    count: int = 0
    reason: str = "无有效记录"
    partial: bool = False
    bed: int = 0


def midnight(day, zone):
    return datetime.combine(day, time.min, zone).astimezone(timezone.utc)


def portions(start, end, zone):
    if start == end:
        yield start.astimezone(zone).date(), start, end
    while start < end:
        day = start.astimezone(zone).date()
        stop = min(end, midnight(day + DAY, zone))
        yield day, start, stop
        start = stop


def daily_features(rows, sources, zone_name, coverage=None):
    zone = ZoneInfo(zone_name)
    days = {m: defaultdict(Feature) for m in METRICS}
    sleep_rows = []
    hrv_records = []
    days["sleep_hrv"] = {}
    samples = defaultdict(list)
    cumulative = defaultdict(list)
    bounds = coverage or {}
    for r in rows:
        m = r["metric"]
        if r["source"] != sources.get(m):
            continue
        start, end = utc_time(r["start"]), utc_time(r["end"])
        day = (end if m == "sleep" else start).astimezone(zone).date()
        if r.get("excluded"):
            affected = (d for d, _, _ in portions(start, end, zone)) if m in ("steps", "active_energy") else [day]
            for d in affected:
                days[m][d].reason = "有用户排除记录"
            continue
        if m == "sleep":
            sleep_rows.append(r)
            if r["value"] == "in_bed":
                days[m][day].bed += 1
        elif m in ("steps", "active_energy"):
            span = (end - start).total_seconds()
            for d, a, b in portions(start, end, zone):
                share = (b - a).total_seconds() / span if span else 1
                cumulative[m, d].append((a, b, r["value"] * share, share < 1))
        else:
            samples[m, day].append(r["value"])
            if m == "hrv_sdnn":
                hrv_records.append((start, end, r["value"]))

    for (m, d), values in samples.items():
        days[m][d] = Feature(median(values), len(values), "样本中位数")
    for (m, d), intervals in cumulative.items():
        latest = None
        conflict = False
        for a, b, _, _ in sorted(intervals):
            if a < b:
                conflict |= latest is not None and a < latest
                latest = max(latest, b) if latest else b
        estimated = any(i[3] for i in intervals)
        days[m][d] = Feature(None if conflict else sum(i[2] for i in intervals), len(intervals),
                             "同源累计段重叠冲突" if conflict else "跨日按秒分摊（估算）" if estimated else "同源累计")
    segments = defaultdict(list)
    intervals = list(asleep_intervals(sleep_rows, sources.get("sleep")))
    for s in group_sleep(intervals, zone):
        segments[s.wake_date].append(s)
    # A sample in an awake interval or a gap within the main sleep is ineligible.
    # Adjacent sleep stages form a continuous asleep interval.
    continuous = []
    for start, end in intervals:
        if continuous and continuous[-1][1] == start:
            continuous[-1] = (continuous[-1][0], end)
        else:
            continuous.append((start, end))
    interval_starts = [a for a, _ in continuous]
    sleep_hrv = []
    for start, end, value in sorted(hrv_records):
        idx = bisect_right(interval_starts, start) - 1
        if idx >= 0 and start < continuous[idx][1] and end <= continuous[idx][1]:
            sleep_hrv.append((start, value))
    sample_times = [a for a, _ in sleep_hrv]
    # Only an actual import boundary can flag truncation. Never use the viewport or
    # first/last observed heartbeat as a substitute for a known selection boundary.
    edges = sorted((utc_time(r["start"]), utc_time(r["end"]), r.get("token", ""))
                   for r in sleep_rows if r["value"] not in ("awake", "in_bed")) if bounds else []
    starts = [a for a, _, _ in edges]
    longest = max((b - a for a, b, _ in edges), default=timedelta())
    for d, group in segments.items():
        main = min(group, key=lambda s: (-s.duration, s.start))
        partial = False
        for s in group:
            for a, b, token in edges[bisect_left(starts, s.start - longest):bisect_left(starts, s.end)]:
                if b <= s.start or token not in bounds:
                    continue
                lo, hi = bounds[token]
                if s.start <= lo + MAX_GAP or s.end >= hi - MAX_GAP:
                    partial = True
        reason = "部分覆盖：睡眠段触及导入边界或其 90 分钟并段范围" if partial else "按末次醒来归日"
        bed = days["sleep"][d].bed
        days["sleep"][d] = Feature(sum(s.duration.total_seconds() / 60 for s in group),
                                   len(group), reason, partial, bed)
        local = main.start.astimezone(zone)
        clock = (local.hour * 60 + local.minute + (local.second + local.microsecond / 1e6) / 60 - 720) % 1440
        days["onset"][d] = Feature(clock, len(group), reason, partial, bed)
        values = [v for _, v in sleep_hrv[bisect_left(sample_times, main.start):bisect_left(sample_times, main.end)]]
        days["sleep_hrv"][d] = Feature(median(values) if values else None, len(values),
                                       "主睡眠内 SDNN 中位数", partial)
    for d, item in days["sleep"].items():
        if item.value is None:
            if item.bed:
                item.reason = "仅有卧床或缺少有效已睡区间" + ("；有用户排除记录" if "排除" in item.reason else "")
            days["onset"][d] = Feature(reason=item.reason, bed=item.bed)
    return days


@dataclass
class Layer:
    values: list = field(repr=False)
    ready: bool = False

    @property
    def center(self):
        return median(self.values) if self.values else None

    @property
    def mad(self):
        center = self.center
        return median(abs(v - center) for v in self.values) if self.values else None


def crosses_noon(values):
    return bool(values) and max(values) - min(values) > 720


def compare(series, day, contexts, metric):
    current = series.get(day, Feature())
    history = {d: f.value for d, f in series.items() if day - 28 * DAY <= d < day
               and f.value is not None and not f.partial}
    context = contexts.get(day, "unknown")
    same = [v for d, v in history.items() if context != "unknown" and contexts.get(d) == context]
    long = Layer(list(history.values()), len(history) >= 7)
    matched = Layer(same, long.ready and len(same) >= 3)
    selected = matched if matched.ready else long if long.ready else None
    reason = ("优先同情境" if matched.ready else "样本不足（长期少于 7 天）" if not long.ready
              else "回退长期（当日情境 unknown）" if context == "unknown" else "回退长期（同情境少于 3 天）")

    def difference(layer):
        if not layer.ready or current.value is None or current.partial:
            return None
        if metric == "onset" and crosses_noon([*layer.values, current.value]):
            return None
        return current.value - layer.center

    if selected and metric == "onset" and current.value is not None and crosses_noon([*selected.values, current.value]):
        reason += " · 跨分界，暂不比较"
    return current, long, matched, reason, difference(selected) if selected else None, difference(long)
