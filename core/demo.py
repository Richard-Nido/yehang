"""Local import boundary. B2 owns parsing, normalization and the date context."""
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

from adapters.health import read_export

FIXTURE = Path(__file__).resolve().parents[1] / "yehang-week/fixtures/crossnight.json"
DEMO_FILES = ("crossnight.json", "crossnight.xml", "b2-six-metrics.json", "b2-six-metrics.xml",
              "demo-records.json")


def demo_path(name):
    if name not in DEMO_FILES:
        raise ValueError("请选择包内合成文件")
    return FIXTURE.with_name(name)


def fingerprint(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_selected(name, *, analysis_tz, date_from, date_to, source_map=None):
    path = name if isinstance(name, Path) else demo_path(name)
    if path.suffix.lower() not in {".xml", ".json"} or not path.is_file():
        raise ValueError("请选择本机已有的 XML 或 JSON 文件")
    signature = path.stat()
    digest = fingerprint(path)
    with TemporaryDirectory() as directory:
        mapping = Path(directory) / "sources.json"
        if source_map is not None:
            mapping.write_text(json.dumps(source_map), encoding="utf8")
        output = read_export(path, analysis_tz=analysis_tz, date_from=date_from, date_to=date_to,
                             source_map_path=mapping, include_identity_aliases=True)
        output["source_map"] = json.loads(mapping.read_text(encoding="utf8")) if mapping.exists() else None
    after = path.stat()
    if (signature.st_size, signature.st_mtime_ns, signature.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError("文件在解析期间已变化，请重新预览")
    return output, digest


def read_demo_records():
    """Read the A1 reference fixture for deterministic regression comparisons."""
    return json.loads(FIXTURE.read_text(encoding="utf8"))["records"]


def sources_by_metric(rows):
    counts = defaultdict(Counter)
    for row in rows:
        if not row.get("excluded"):
            counts[row["metric"]][row["source"]] += 1
    return {metric: sorted(options, key=lambda s: (-options[s], s)) for metric, options in counts.items()}


def fixture_family(settings):
    """Recognize known synthetic fixtures even when selected through a local path."""
    if settings.get("mode", "synthetic") != "synthetic":
        return None
    name = settings.get("file")
    families = {"crossnight.json": "crossnight", "crossnight.xml": "crossnight",
                "demo-records.json": "full"}
    if name in families:
        return families[name]
    if name == "本机文件" and settings.get("sha256"):
        for filename, family in families.items():
            path = demo_path(filename)
            if path.exists() and fingerprint(path) == settings["sha256"]:
                return family
    return None
