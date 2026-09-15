# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ["Main.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
# PySide6 6.11 on Windows uses the system ICU forwarding DLLs. Build hosts may
# put unrelated ICU builds (for example Poppler's icudt78.dll) on PATH; bundling
# those beside Qt6Core.dll makes the frozen application fail to load QtCore.
a.binaries = [
    binary for binary in a.binaries
    if not (binary[0].lower().startswith("icu") and binary[0].lower().endswith(".dll"))
]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="UEPackageManager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
