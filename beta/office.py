"""Render office schedules locally, with an isolated high-security LibreOffice profile."""

from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

WORD = set(".doc .docx .docm .dot .dotx .dotm .rtf .odt .ott".split())
SHEETS = set(".xls .xlsx .xlsm .xlsb .xlt .xltx .xltm .ods .ots .csv .tsv".split())
SLIDES = set(".ppt .pptx .pptm .pot .potx .potm .pps .ppsx .ppsm .odp .otp".split())
FORMATS = WORD | SHEETS | SLIDES


def executable():
    paths = []
    if getattr(sys, "frozen", False):
        paths.append(Path(sys.executable).parent / "office/program/soffice.com")
    for name in ("soffice", "libreoffice"):
        if found := shutil.which(name):
            paths.append(Path(found))
    paths.extend(
        [
            Path(os.getenv("ProgramFiles", "C:/Program Files"))
            / "LibreOffice/program/soffice.com",
            Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"),
        ]
    )
    return next((p for p in paths if p.is_file()), None)


@contextmanager
def render(path):
    if path.suffix.lower() not in FORMATS:
        yield path
        return
    app = executable()
    if not app:
        raise ValueError(
            "此电脑尚未安装 Office 转换组件。请运行含 Office 组件的夜航安装包，或先将排班另存为 PDF。"
        )
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        profile = root / "profile"
        (profile / "user").mkdir(parents=True)
        (profile / "user/registrymodifications.xcu").write_text(
            '<oor:items xmlns:oor="http://openoffice.org/2001/registry">'
            '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
            '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>'
            '<prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop></item>'
            "</oor:items>",
            encoding="utf8",
        )
        cmd = [
            str(app),
            "-env:UserInstallation=" + profile.as_uri(),
            "--headless",
            "--nologo",
            "--nofirststartwizard",
            "--norestore",
            "--convert-to",
            "pdf",
            "--outdir",
            str(root),
            str(path.resolve()),
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=180,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            raise ValueError("Office 转换超时，请缩小排班文件或另存为 PDF。") from None
        output = root / (path.stem + ".pdf")
        if result.returncode or not output.is_file() or not output.stat().st_size:
            raise ValueError(
                "未能读取此 Office 文件。请检查是否加密、文件格式是否正确，或另存为 PDF。"
            )
        yield output
