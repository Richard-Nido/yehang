param(
    [Parameter(Mandatory=$true)][string]$Compiler,
    [string]$OfficeDir,
    [string]$Python = ".venv/Scripts/python.exe"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    $out = Join-Path $root ".build"
    $dist = Join-Path $out "dist"
    $work = Join-Path $out "work"
    $release = Join-Path $out "release"
    New-Item -ItemType Directory -Force $out,$release | Out-Null
    & $Python packaging/notices.py
    if ($LASTEXITCODE -ne 0) {throw "Notice collection failed"}
    & $Python -m PyInstaller --noconfirm --windowed --onedir --name Yehang --icon packaging/yehang.ico --distpath $dist --workpath $work --specpath $root --add-data ".build/notices:licenses" --add-data "web:web" --add-data "packaging/yehang.ico:packaging" --add-data "yehang-week/fixtures:yehang-week/fixtures" --collect-data tzdata --collect-all pypdfium2_raw --collect-all ijson --copy-metadata keyring --hidden-import keyring.backends.Windows --hidden-import uvicorn.protocols.http.h11_impl --hidden-import uvicorn.loops.asyncio --hidden-import uvicorn.lifespan.on launch_studio.py
    if ($LASTEXITCODE -ne 0) {throw "PyInstaller failed"}
    $appDir = Join-Path $dist "Yehang"
    & $Compiler "/DAppDir=$appDir" "/DOutDir=$release" packaging/installer.iss
    if ($LASTEXITCODE -ne 0) {throw "Standard installer failed"}
    if ($OfficeDir) {
        if (-not (Test-Path -LiteralPath (Join-Path $OfficeDir "program/soffice.com"))) {throw "Invalid Office component directory"}
        & $Compiler "/DAppDir=$appDir" "/DOutDir=$release" "/DOfficeDir=$OfficeDir" packaging/installer.iss
        if ($LASTEXITCODE -ne 0) {throw "Office installer failed"}
    }
} finally {Pop-Location}
