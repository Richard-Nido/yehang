# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import os

ROOT = Path(SPECPATH).parent

from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_all
from PyInstaller.utils.hooks import copy_metadata

datas = [(str(ROOT / '.build/notices'), 'licenses'), (str(ROOT / 'web'), 'web'), (str(ROOT / 'yehang-week/fixtures'), 'yehang-week/fixtures')]
datas += [(str(ROOT / 'knowledge'), 'knowledge'), (str(ROOT / '.build/build-info.json'), '.')]
binaries = []
hiddenimports = ['keyring.backends.macOS', 'uvicorn.protocols.http.h11_impl', 'uvicorn.loops.asyncio', 'uvicorn.lifespan.on']
datas += collect_data_files('tzdata')
datas += copy_metadata('keyring')
tmp_ret = collect_all('pypdfium2_raw')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('ijson')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    [str(ROOT / 'packaging/launch_macos.py')],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Yehang',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch='arm64',
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(ROOT / '.build/yehang.icns')],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Yehang',
)
app = BUNDLE(
    coll,
    name='Yehang.app',
    icon=str(ROOT / '.build/yehang.icns'),
    bundle_identifier='org.yehang.desktop',
    version='0.1.0',
    info_plist={'CFBundleDisplayName':'夜航','CFBundleShortVersionString':os.environ.get('YEHANG_BUILD_VERSION','0.1.0-beta.3'),'CFBundleVersion':'0.1.0.3','LSMinimumSystemVersion':'13.0','NSHighResolutionCapable':True},
)
