"""Puls Sync Protocol v1 decoding, adapted from PulsHealth's reference receiver.

Copyright PulsHealth contributors. SPDX-License-Identifier: Apache-2.0
Upstream: https://github.com/PulsHealth/pulshealth
Only parsing is reused; storage and HTTP handling are implemented by Yehang.
"""
import json
import re
import zlib

MAX_DECODED = 128 << 20

PROTOCOL_VERSIONS = [1]
COUNTS = ("sampleCount", "deletionCount", "routeCount", "seriesCount",
          "aggregateCount", "activitySummaryCount", "profileCount")
# kind -> the detail field that must be present for that kind
KINDS = {"quantity": None, "category": "category", "workout": "workout", "heartbeatSeries": "heartbeats",
         "ecg": "ecg", "stateOfMind": "stateOfMind", "medicationDose": "medicationDose"}
AGG_ENUMS = {"func": {"sum", "average", "min", "max", "mostRecent", "duration"},
             "intervalUnit": {"minute", "hour", "day", "week", "month"},
             "deviceFilter": {"all", "watch", "iphone"}}
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
class BadRequest(Exception):
    """Malformed input: answered with 400, which the app never retries."""


class UnsupportedVersion(Exception):
    """A protocol version this receiver does not speak: fixed 400 body."""


class TooLarge(Exception):
    """Over a size limit: answered with 413, which the app never retries."""


def is_uuid(v):
    return isinstance(v, str) and UUID_RE.match(v) is not None


def norm_uuid(v):
    """The stored form of a UUID. The app sends upper case, other senders may not, and
    the spec says compare case-insensitively: store lower case, look up lower case."""
    return v.lower()


def gunzip(raw, limit=MAX_DECODED):
    """Decode a gzip body (one member, or several back to back, as Go's reader allows)
    without ever holding more than limit + 1 decoded bytes: a few kilobytes of gzip
    can inflate to gigabytes. Raises TooLarge past the limit, BadRequest when invalid."""
    if not raw:
        raise BadRequest("invalid gzip body: empty")
    out = bytearray()
    while raw:
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            out += d.decompress(raw, limit + 1 - len(out))
        except zlib.error as e:
            raise BadRequest(f"invalid gzip body: {e}") from None
        if len(out) > limit:
            raise TooLarge(f"decompressed body exceeds {limit} bytes")
        if not d.eof:
            raise BadRequest("invalid gzip body: truncated")
        raw = d.unused_data
    return bytes(out)


def is_ms(v):
    """A required epoch-ms timestamp: a number in year 1..9999, not 0 (0 means absent)."""
    return (isinstance(v, (int, float)) and not isinstance(v, bool)
            and v != 0 and -62135596800000 <= v <= 253402300799999)


def parse_batch(text):
    """NDJSON text -> dict of validated lines in wire order. Raises BadRequest/UnsupportedVersion."""
    lines = iter(line for line in text.split("\n") if line.strip())

    def take(n, what, key=None):
        for i in range(1, n + 1):
            try:
                obj = json.loads(next(lines))
            except StopIteration:
                raise BadRequest(f"{what} {i}/{n}: unexpected end of body") from None
            except ValueError as e:
                raise BadRequest(f"{what} {i}: invalid JSON: {e}") from None
            if key:  # wrapped line: the wrapper key must hold a non-null object
                obj = obj.get(key) if isinstance(obj, dict) else None
            if not isinstance(obj, dict):
                raise BadRequest(f"{what} {i}: missing or null {key or 'object'}")
            yield i, obj

    def points(inner, what, i, *required):
        pts = inner.get("points")
        if not isinstance(pts, list) or len(pts) > 4000:
            raise BadRequest(f"{what} {i}: points must be a list of at most 4000")
        for p in pts:
            if not isinstance(p, dict) or not is_ms(p.get("t")) or any(p.get(k) is None for k in required):
                raise BadRequest(f"{what} {i}: bad point")
        return pts

    header = next(take(1, "batch header"), (0, None))[1]
    if header is None:
        raise BadRequest("empty body: missing batch header")
    version = header.get("schemaVersion")  # absent or null = legacy client = 1
    if version is not None and (type(version) is not int or version not in PROTOCOL_VERSIONS):
        raise UnsupportedVersion(f"schemaVersion {version}")
    if not is_uuid(header.get("batchID")) or not header.get("type"):
        raise BadRequest("invalid batch header: batchID must be a UUID and type non-empty")
    counts = {k: header.get(k) or 0 for k in COUNTS}
    if any(isinstance(n, bool) or not isinstance(n, int) or not 0 <= n <= 100_000 for n in counts.values()):
        raise BadRequest("invalid batch header: counts must be integers 0..100000")
    if counts["profileCount"] > 1 or sum(counts.values()) > 200_000:
        raise BadRequest("invalid batch header: too many declared lines")

    b = {"header": header, "samples": [], "deletions": [], "routes": [], "series": [],
         "aggregates": [], "activitySummaries": [], "profile": None}
    for i, s in take(counts["sampleCount"], "sample"):
        if not is_uuid(s.get("uuid")) or not s.get("type") or s.get("kind") not in KINDS or not is_ms(s.get("start")):
            raise BadRequest(f"sample {i}: bad uuid, type, kind, or start")
        if KINDS[s["kind"]] and s.get(KINDS[s["kind"]]) is None:
            raise BadRequest(f"sample {i}: {s['kind']} sample missing {KINDS[s['kind']]}")
        b["samples"].append(s)  # the stored line keeps the sender's spelling; the key column does not
    for i, d in take(counts["deletionCount"], "deletion", "deleted"):
        if not is_uuid(d.get("uuid")) or not d.get("type"):
            raise BadRequest(f"deletion {i}: bad uuid or type")
        d["uuid"] = norm_uuid(d["uuid"])
        b["deletions"].append(d)
    for i, r in take(counts["routeCount"], "route", "route"):
        if not is_uuid(r.get("workoutUUID")):
            raise BadRequest(f"route {i}: workoutUUID is not a UUID")
        points(r, "route", i, "lat", "lon")
        r["workoutUUID"] = norm_uuid(r["workoutUUID"])
        b["routes"].append(r)
    for i, s in take(counts["seriesCount"], "series", "series"):
        if not is_uuid(s.get("workoutUUID")) or not s.get("type"):
            raise BadRequest(f"series {i}: bad workoutUUID or type")
        points(s, "series", i, "value")
        s["workoutUUID"] = norm_uuid(s["workoutUUID"])
        b["series"].append(s)
    for i, a in take(counts["aggregateCount"], "aggregate", "aggregate"):
        iv = a.get("intervalValue")
        if (not a.get("type") or any(a.get(k) not in v for k, v in AGG_ENUMS.items())
                or isinstance(iv, bool) or not isinstance(iv, int) or iv < 1):
            raise BadRequest(f"aggregate {i}: bad type, func, interval, or deviceFilter")
        if not is_ms(a.get("bucketStart")) or not is_ms(a.get("bucketEnd")) or a["bucketEnd"] <= a["bucketStart"]:
            raise BadRequest(f"aggregate {i}: bucketEnd must be after bucketStart")
        b["aggregates"].append(a)
    for i, a in take(counts["activitySummaryCount"], "activity summary", "activitySummary"):
        if not is_ms(a.get("date")) or a.get("moveMode") not in (None, 0, 1):
            raise BadRequest(f"activity summary {i}: bad date or moveMode")
        if a.get("localDate") is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(a["localDate"])):
            raise BadRequest(f"activity summary {i}: invalid localDate")
        b["activitySummaries"].append(a)
    for _, p in take(counts["profileCount"], "profile", "profile"):
        b["profile"] = p
    for _ in lines:
        raise BadRequest("unexpected trailing line after the declared counts")
    return b
