from datetime import datetime
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("Asia/Shanghai")


def local(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZONE)
    return value.astimezone(ZONE)


def stamp(value):
    return local(value).isoformat(timespec="minutes")
