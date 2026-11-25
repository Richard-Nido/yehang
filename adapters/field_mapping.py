"""六类健康指标的公共字段映射；文件入口见 adapters.health。"""

from datetime import datetime
from math import isfinite


TYPE_MAP = {
    "HKCategoryTypeIdentifierSleepAnalysis": "sleep",
    "HKQuantityTypeIdentifierHeartRate": "heart_rate",
    "HKQuantityTypeIdentifierRestingHeartRate": "resting_hr",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "hrv_sdnn",
    "HKQuantityTypeIdentifierStepCount": "steps",
    "HKQuantityTypeIdentifierActiveEnergyBurned": "active_energy",
}

SLEEP_MAP = {
    "InBed": "in_bed",
    "Awake": "awake",
    "Asleep": "asleep",
    "AsleepUnspecified": "asleep",
    "AsleepCore": "core",
    "AsleepDeep": "deep",
    "AsleepREM": "rem",
}

UNITS = {
    "heart_rate": {"count/min": ("bpm", 1), "bpm": ("bpm", 1)},
    "resting_hr": {"count/min": ("bpm", 1), "bpm": ("bpm", 1)},
    "hrv_sdnn": {"ms": ("ms", 1), "s": ("ms", 1000)},
    "steps": {"count": ("count", 1)},
    # HealthKit：大卡 Cal = kcal；小卡 cal 是其千分之一，大小写不可混用。
    "active_energy": {"kcal": ("kcal", 1), "Cal": ("kcal", 1),
                      "cal": ("kcal", .001), "kJ": ("kcal", 1 / 4.184), "J": ("kcal", 1 / 4184)},
}


class RecordError(ValueError):
    """可计数的行级错误；错误码不含输入中的个人信息。"""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def parse_time(value):
    """接受苹果导出时间和 ISO 时间；保留原偏移，不采用电脑默认时区。"""
    if not isinstance(value, str):
        raise RecordError("invalid_time")
    try:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S %z")
        if parsed.utcoffset() is None:
            raise ValueError
    except ValueError:
        raise RecordError("invalid_time") from None
    return parsed


def normalize_value(metric, value, unit, *, xml=False):
    if metric == "sleep":
        if xml and isinstance(value, str):
            stage = value.removeprefix("HKCategoryValueSleepAnalysis")
            if stage not in SLEEP_MAP:
                raise RecordError("invalid_stage")
            return SLEEP_MAP[stage], "stage"
        if unit != "stage":
            raise RecordError("invalid_unit")
        if not isinstance(value, str) or value not in set(SLEEP_MAP.values()):
            raise RecordError("invalid_stage")
        return value, "stage"
    if not isinstance(unit, str) or unit not in UNITS[metric]:
        raise RecordError("invalid_unit")
    if isinstance(value, bool) or (not xml and not isinstance(value, (int, float))):
        raise RecordError("invalid_value")
    target, factor = UNITS[metric][unit]
    try:
        number = float(value) * factor
    except (ValueError, TypeError, OverflowError):
        raise RecordError("invalid_value") from None
    if not isfinite(number) or number < 0:
        raise RecordError("invalid_value")
    if number == 0 and metric in {"heart_rate", "resting_hr", "hrv_sdnn"}:
        raise RecordError("zero_physiological_value")
    return number, target


def normalize_xml_record(attrs, *, record_id, source_alias):
    """只接收已分配匿名来源的属性，不把 sourceName/device 元数据带入输出。

    未关注类型返回 None；目标类型的坏数据抛 ValueError。
    record_id 和 source_alias 由文件导入器分配。
    """
    metric = TYPE_MAP.get(attrs.get("type"))
    if metric is None:
        return None
    if not record_id or not source_alias:
        raise RecordError("invalid_identity")
    try:
        start = parse_time(attrs["startDate"])
        end = parse_time(attrs["endDate"])
        if end < start or (metric == "sleep" and end == start):
            raise RecordError("invalid_interval")
        value, unit = normalize_value(metric, attrs["value"], attrs.get("unit"), xml=True)
    except KeyError as exc:
        raise RecordError("missing_field") from exc
    return {
        "id": record_id,
        "metric": metric,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "source": source_alias,
        "value": value,
        "unit": unit,
    }
