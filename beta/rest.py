"""Short rest planning over upcoming free intervals, in Shanghai civil time."""

from datetime import datetime, time, timedelta
from statistics import median

from beta.timebase import ZONE, local, stamp
from core.features import compare
from core.health_state import assess
from core.planner import difference
from core.sleep import asleep_intervals

MIN = timedelta(minutes=1)
DAY = timedelta(days=1)


def planning_intervals(now, blocks, plans, latest_end=None):
    now = local(now)
    day = now.date()
    limit = datetime.combine(day + 7 * DAY, time.min, ZONE)
    if latest_end is not None:
        limit = min(limit, local(latest_end))
    busy = [
        (local(b["start"]), local(b["end"])) for b in blocks if b["kind"] != "available"
    ]
    busy.extend((local(p["start"]), local(p["end"])) for p in plans)
    explicit = [
        (max(now, local(b["start"])), min(limit, local(b["end"])))
        for b in blocks
        if b["kind"] == "available"
        and local(b["end"]) > now
        and local(b["start"]) < limit
    ]
    nights = [
        (local(b["start"]), local(b["end"])) for b in blocks if b["kind"] == "night"
    ]
    # Without explicit availability, search waking hours and the hours before a night shift.
    windows = []
    for offset in range(7):
        d = day + offset * DAY
        a = datetime.combine(d, time(9), ZONE)
        z = datetime.combine(d, time(19), ZONE)
        windows.append((a, z))
    windows.extend((s - timedelta(hours=4), s) for s, _ in nights)
    windows.extend((e, e + timedelta(hours=3)) for _, e in nights)
    spans = explicit or [
        (max(now, a), min(limit, b)) for a, b in windows if a < limit and b > now
    ]
    if latest_end is not None and any(b["kind"] == "available" and local(b["end"]) > now for b in blocks):
        # 用户明确标出的空档若都晚于目标睡眠，不在其他时间凭空生成可用窗口。
        spans = explicit
        assumed = False
    else:
        assumed = not bool(explicit)
    return difference(spans, busy), busy, nights, assumed


def rest_windows(now, blocks, plans, latest_end=None):
    free, busy, _, assumed = planning_intervals(now, blocks, plans, latest_end)
    windows = []
    for a, b in free:
        start = a.replace(second=0, microsecond=0)
        if start < a:
            start += MIN
        # 与推荐算法一致：在下一项已知安排前保留 15 分钟缓冲。
        next_busy = min((x for x, _ in busy if x >= start), default=b + DAY)
        end = min(b, next_busy - 15 * MIN).replace(second=0, microsecond=0)
        if end - start >= 10 * MIN:
            windows.append(dict(start=stamp(start), end=stamp(end), minutes=int((end-start)/MIN)))
    return dict(assumed=assumed, windows=windows, until=stamp(latest_end) if latest_end else None)


def recommend(now, blocks, plans, features, contexts, latest_end=None):
    now = local(now)
    day = now.date()
    limit = datetime.combine(day + 7 * DAY, time.min, ZONE)
    free, busy, nights, assumed = planning_intervals(now, blocks, plans, latest_end)
    recent = [
        d
        for d, f in features["sleep"].items()
        if day - DAY <= d <= day and f.value is not None and not f.partial
    ]
    reasons = []
    if recent:
        d = max(recent)
        f, baseline, same, _, delta, _ = compare(
            features["sleep"], d, contexts, "sleep"
        )
        if delta is not None and delta <= -45:
            reasons.append(f"最近一次睡眠比个人参照少 {abs(delta):.0f} 分钟")
        elif f.value < 420:
            reasons.append(f"最近一个有记录日睡眠 {f.value / 60:.1f} 小时")
    state = assess(features, day, contexts)
    if state.recovery is not None and state.recovery <= 33:
        reasons.append("今天的恢复度估计低于个人常态")
    target = 30 if reasons else 20
    best = None
    for a, b in free:
        start = a.replace(second=0, microsecond=0)
        if start < a:
            start += MIN
        while start + 10 * MIN <= b:
            next_busy = min((x for x, _ in busy if x >= start), default=limit + DAY)
            duration = min(target, (b - start) // MIN, (next_busy - start) // MIN - 15)
            if duration >= 10:
                anchor = start.replace(hour=14, minute=0)
                after = [e for _, e in nights if e <= start < e + 3 * 60 * MIN]
                before = [s for s, _ in nights if start < s <= start + 4 * 60 * MIN]
                if after:
                    anchor = max(after) + 30 * MIN
                elif before:
                    anchor = min(before) - 90 * MIN
                distance = abs((start - anchor) / MIN)
                cost = (
                    (start.date() - day).days * 1500
                    + (target - duration) * 20
                    + distance
                )
                if reasons:
                    cost += (start - now) / MIN * 0.6
                candidate = (cost, start, duration, bool(after or before))
                if best is None or candidate < best:
                    best = candidate
            start += 5 * MIN
    if best is None:
        return None
    _, start, duration, shift = best
    reason = (
        "；".join(reasons)
        if reasons
        else (
            "近期生理资料不足，先按短休安排"
            if not recent
            else "根据最近睡眠记录，先安排一次短休"
        )
    )
    timing = "结合夜班前后时段" if shift else "优先选择较早的白天空档"
    return dict(
        start=stamp(start),
        end=stamp(start + duration * MIN),
        minutes=duration,
        reason=f"{reason}。{timing}，在已知下一项日程前留出缓冲。",
        assumed=assumed,
    )


def followup(plan, rows, sources, now):
    start, end = local(plan["start"]), local(plan["end"])
    if now < end:
        return {"state": "已开放执行反馈 · 等待设备记录", "details": []}
    good = [r for r in rows if not r["excluded"] and local(r["end"]) <= now]
    overlap = sum(
        (min(b, end) - max(a, start)) / MIN
        for a, b in asleep_intervals(good, sources.get("sleep"))
        if b > start and a < end
    )
    details = []
    if overlap:
        coverage = "覆盖计划时长" if overlap >= plan["minutes"] else "部分覆盖计划时段"
        details.append(
            f"佩戴设备记录到约 {overlap:.0f} 分钟睡眠，{coverage}（计划 {plan['minutes']} 分钟）。"
        )
    for metric, label, unit in (
        ("resting_hr", "静息心率", "bpm"),
        ("hrv_sdnn", "HRV（SDNN）", "ms"),
    ):
        selected = [
            r
            for r in good
            if r["metric"] == metric and r["source"] == sources.get(metric)
        ]
        before = [
            r["value"]
            for r in selected
            if start - DAY <= local(r["start"]) and local(r["end"]) <= start
        ]
        after = [
            r["value"]
            for r in selected
            if end <= local(r["start"]) and local(r["end"]) < end + DAY
        ]
        if before and after:
            details.append(
                f"{label}中位数 {median(before):g} → {median(after):g} {unit}（休息前后各 24 小时）。"
            )
    return {
        "state": "已有可对照记录" if details else "等待时段内或后续的健康记录",
        "details": details,
    }
