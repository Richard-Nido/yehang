"""Daily personal-baseline estimates. Formula choices and evidence are in README.md."""
from dataclasses import dataclass
from math import exp, log
from statistics import median

from core.features import DAY, Feature
from core.sleep import utc_time

# Minimum scale for each robust z score, in log(ms), bpm or minutes.
SCALES = {"sleep_hrv": 0.15, "hrv_sdnn": 0.15, "resting_hr": 3.0, "sleep": 60.0}
MIN_HISTORY = 14
MIN_CONTEXT = 7


@dataclass(frozen=True)
class Signal:
    current: Feature
    center: float | None
    n: int
    basis: str
    z: float | None
    reason: str


def quality(metric, feature):
    if feature.partial:
        return "导入边界覆盖不全"
    if feature.value is None or feature.value <= 0:
        return "缺少有效记录"
    if metric in ("sleep_hrv", "hrv_sdnn") and feature.count < 2:
        return "至少需要 2 条 SDNN 样本"
    return ""


def signal(metric, features, day, contexts):
    series = features.get(metric, {})
    current = series.get(day, Feature())
    history = {d: f.value for d, f in series.items() if day - 28 * DAY <= d < day
               and not quality(metric, f)}
    context = contexts.get(day, "unknown")
    same = [v for d, v in history.items() if context != "unknown" and contexts.get(d) == context]
    matched = len(history) >= MIN_HISTORY and len(same) >= MIN_CONTEXT
    values = same if matched else list(history.values())
    basis = "同班次情境" if matched else "全部情境"
    reason = quality(metric, current)
    if len(history) < MIN_HISTORY:
        reason = "；".join(filter(None, (reason, f"基线 {len(history)}/{MIN_HISTORY} 天")))
    center = median(values) if values else None
    if reason:
        return Signal(current, center, len(values), basis, None, reason)
    transform = log if metric in ("sleep_hrv", "hrv_sdnn") else float
    transformed = [transform(v) for v in values]
    middle = median(transformed)
    mad = median(abs(v - middle) for v in transformed)
    z = (transform(current.value) - middle) / max(1.4826 * mad, SCALES[metric])
    return Signal(current, center, len(values), basis, max(-3.0, min(3.0, z)), "")


@dataclass(frozen=True)
class HealthState:
    recovery: int | None
    stress: int | None
    signals: dict[str, Signal]


def assess(features, day, contexts):
    signals = {m: signal(m, features, day, contexts) for m in SCALES}
    night, daily, pulse, sleep = (signals[m].z for m in ("sleep_hrv", "hrv_sdnn", "resting_hr", "sleep"))
    recovery = stress = None
    if night is not None and pulse is not None and sleep is not None:
        # Adapt the Pulsr recovery composite to the available measurements.
        # Extra time asleep earns no bonus over the person's habitual duration.
        composite = (0.55 * night - 0.25 * pulse + 0.15 * min(sleep, 0)) / 0.95
        recovery = round(100 / (1 + exp(-(1.25 * composite + 0.35))))
    if daily is not None and pulse is not None:
        stress = round(100 / (1 + exp(-(pulse - daily) / 2)))
    return HealthState(recovery, stress, signals)


def latest_fatigue(events, now, zone):
    today = now.astimezone(zone).date()
    reports = [(utc_time(r["at"]), r["value"]) for r in events if r["kind"] == "fatigue"]
    return max(((t, v) for t, v in reports if t <= now and t.astimezone(zone).date() == today),
               key=lambda pair: pair[0], default=(None, None))[1]


def priority_reasons(recovery, stress, fatigue):
    reasons = []
    if recovery is not None and recovery <= 33:
        reasons.append("今日身体恢复度偏低")
    if stress is not None and stress >= 75:
        reasons.append("昨日生理压力估计偏高")
    if fatigue is not None and fatigue >= 4:
        reasons.append("今日自评疲劳较高")
    return reasons
