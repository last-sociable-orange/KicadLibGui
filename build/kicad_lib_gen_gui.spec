# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-file spec for the KiCad LibGen GUI.

Build from the repository root:

    pyinstaller --clean --noconfirm build/kicad_lib_gen_gui.spec

The result is ``dist/KiCadLibGen`` (``KiCadLibGen.exe`` on Windows).
``prompt_toolkit`` is excluded because the GUI never imports the CLI's
interactive path; the CLI still works from a normal Python install.
"""

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(ROOT / "gui_main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "assets"), "assets"),
        (str(ROOT / "LICENSE"), "."),
        (str(ROOT / "README-GUI.md"), "."),
        (str(ROOT / "THIRD-PARTY-NOTICES.md"), "."),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "prompt_toolkit",
        "pytest",
        "PIL",
        "ruff",
        "pydoc",
        "doctest",
        "unittest",
        "test",
        "tkinter.test",
        "setuptools",
        "pip",
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="KiCadLibGen",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "app.ico"),
    version=str(ROOT / "build" / "version_info.txt"),
)
