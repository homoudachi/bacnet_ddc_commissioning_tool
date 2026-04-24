# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: single-file Windows exe for ``tools/runtime/app.py``."""

import pathlib

from PyInstaller.utils.hooks import collect_all

# PyInstaller injects ``SPECPATH`` (directory containing this .spec file).
REPO = pathlib.Path(SPECPATH).resolve().parent.parent
RUNTIME = REPO / "tools" / "runtime"

# ``app.py`` loads sibling tools via ``importlib`` from ``ROOT / "tools" / ...``; bundle the tree.
datas = [
    (str(REPO / "tools"), "tools"),
    (str(REPO / "docs" / "examples"), "docs/examples"),
]

datas_b, binaries_b, hidden_b = collect_all("bacpypes3")
datas_o, binaries_o, hidden_o = collect_all("openpyxl")
datas_f, binaries_f, hidden_f = collect_all("fpdf2")

datas += datas_b + datas_o + datas_f
binaries = binaries_b + binaries_o + binaries_f
hiddenimports = sorted(set(hidden_b + hidden_o + hidden_f))

block_cipher = None

a = Analysis(
    [str(RUNTIME / "app.py")],
    pathex=[str(RUNTIME)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="bacnet-commissioning",
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
