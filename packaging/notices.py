"""Collect notices for the Python runtime and distributions shipped in the installer."""

from importlib.metadata import distribution
from pathlib import Path
import shutil
import sys

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

root = Path(__file__).resolve().parents[1]
out = root / ".build" / "notices"
out.mkdir(parents=True, exist_ok=True)
pending = [
    Requirement(line).name
    for line in (root / "requirements.txt").read_text().splitlines()
    if line.strip()
]
seen = set()
while pending:
    name = canonicalize_name(pending.pop())
    if name in seen:
        continue
    seen.add(name)
    dist = distribution(name)
    target = out / name
    target.mkdir(exist_ok=True)
    for file in dist.files or ():
        if any(
            term in file.name.lower() for term in ("license", "copying", "notice")
        ) and file.suffix.lower() not in {".py", ".pyc"}:
            item = Path(dist.locate_file(file))
            if item.is_file():
                relative = Path(*[p for p in file.parts if p not in ("..", ".")])
                dest = target / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(item, dest)
    (target / "distribution.txt").write_text(
        f"{dist.metadata['Name']} {dist.version}\n"
        + "\n".join(dist.metadata.get_all("Project-URL") or []),
        encoding="utf8",
    )
    for item in dist.requires or ():
        req = Requirement(item)
        if not req.marker or req.marker.evaluate({"extra": ""}):
            pending.append(req.name)
python_license = next(
    p for p in (
        Path(sys.base_prefix) / "LICENSE.txt",
        Path(sys.base_prefix) / f"lib/python{sys.version_info.major}.{sys.version_info.minor}/LICENSE.txt",
    ) if p.is_file()
)
shutil.copyfile(python_license, out / "Python-LICENSE.txt")
for dest in (Path(sys.base_prefix) / "tcl").rglob("license.terms"):
    local = out / "Tcl-Tk" / dest.relative_to(Path(sys.base_prefix) / "tcl")
    local.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(dest, local)
shutil.copyfile(root / "knowledge/Pulsr-LICENSE.txt", out / "Pulsr-LICENSE.txt")

for license_file in (root / "packaging/licenses").glob("*.terms"):
    shutil.copyfile(license_file, out / license_file.name)
shutil.copytree(root / "third_party/pulshealth", out / "PulsHealth", dirs_exist_ok=True)
