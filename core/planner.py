"""Half-open intervals. Compare UTC instants at their original precision."""
import re
from datetime import timedelta

from core.sleep import utc_time


def check_minutes(minutes):
    if type(minutes) is not int or minutes <= 0:
        raise ValueError("所需分钟须为正整数")


def endpoint(value, field):
    try:
        instant = utc_time(value)
        offset = re.search(r"[+-]\d{2}:?(\d{2})(?::?(\d{2}))?(?:[.,]\d+)?$", value)
        if offset and any(int(part) >= 60 for part in offset.groups() if part):
            raise ValueError("UTC 偏移无效")
        if any(fraction[6:].strip("0") for fraction in re.findall(r"[.,](\d+)", value)):
            raise ValueError("时间精度超过微秒")
        return instant
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"{field}请填写含日期和 UTC 偏移的有效 ISO 时间（精确至微秒）") from exc


def interval(start, end):
    left, right = endpoint(start, "开始时间"), endpoint(end, "结束时间")
    if right <= left:
        raise ValueError("结束时间须晚于开始时间")
    return left, right


def merged(pairs):
    result = []
    for left, right in sorted(pairs):
        if result and left <= result[-1][1]:
            result[-1] = result[-1][0], max(result[-1][1], right)
        else:
            result.append((left, right))
    return result


def difference(available, busy):
    """Subtract merged busy intervals; retain even sub-minute fragments."""
    occupied = merged(busy)
    result = []
    for left, right in merged(available):
        for start, end in occupied:
            if start >= right:
                break
            if end <= left:
                continue
            if start > left:
                result.append((left, start))
            left = max(left, end)
            if left >= right:
                break
        if left < right:
            result.append((left, right))
    return result


def enough(windows, minutes):
    check_minutes(minutes)
    return [(left, right) for left, right in windows if (right-left) // timedelta(minutes=1) >= minutes]


def free_windows(available, busy, *, minutes):
    fragments = difference([interval(*p) for p in available], [interval(*p) for p in busy])
    return [(s.isoformat(), e.isoformat()) for s, e in enough(fragments, minutes)]
