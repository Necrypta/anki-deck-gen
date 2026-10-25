# PyInstaller spec: builds a single windowed AnkiDeckGenerator.exe.
#   npm --prefix frontend run build
#   pyinstaller ankigen.spec
# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ["run.py"],
    pathex=[],
    datas=[("frontend/dist", "frontend/dist")],
    hiddenimports=[],
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="AnkiDeckGenerator",
    console=False,
    upx=False,
)
