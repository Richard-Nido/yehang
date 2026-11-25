"""Sleep intervals are half-open. Do all arithmetic on UTC instants."""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ASLEEP = {"asleep", "core", "deep", "rem"}
MAX_GAP = timedelta(minutes=90)


def utc_time(value: str) -> datetime:
    instant = datetime.fromisoformat(value)
    if instant.utcoffset() is None:
        raise ValueError(f"时间缺少 UTC 偏移：{value}")
    return instant.astimezone(timezone.utc)


@dataclass(frozen=True)
class SleepSegment:
    start: datetime
    end: datetime
    duration: timedelta
    wake_date: date


def asleep_intervals(records, source):
    """Disjoint intervals actually scored asleep, excluding explicit awake time."""
    # Count active sleep and awake intervals independently at each endpoint.
    changes = defaultdict(lambda: [0, 0])
    for row in records:
        stage = row["value"]
        if row["metric"] != "sleep" or row["source"] != source:
            continue
        if stage not in ASLEEP and stage != "awake":
            continue
        start, end = utc_time(row["start"]), utc_time(row["end"])
        if end <= start:
            raise ValueError("睡眠记录结束时间须晚于开始时间")
        channel = 1 if stage == "awake" else 0
        changes[start][channel] += 1
        changes[end][channel] -= 1

    asleep = awake = 0
    previous = None
    for point, (sleep_delta, awake_delta) in sorted(changes.items()):
        if previous is not None and asleep > 0 and awake == 0:
            yield previous, point
        asleep += sleep_delta
        awake += awake_delta
        previous = point


def group_sleep(intervals, zone):
    segments = []
    for start, end in intervals:
        duration = end - start
        if segments and start - segments[-1].end <= MAX_GAP:
            prior = segments.pop()
            start = prior.start
            duration += prior.duration
        segments.append(SleepSegment(start, end, duration, end.astimezone(zone).date()))
    return segments


def sleep_segments(records, *, source: str, analysis_tz: str = "Asia/Shanghai"):
    """Aggregate v1 records for one source. An empty list means unknown sleep."""
    return group_sleep(asleep_intervals(records, source), ZoneInfo(analysis_tz))
