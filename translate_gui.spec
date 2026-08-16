# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = (
    collect_submodules("ebooklib")
    + collect_submodules("bs4")
    + collect_submodules("lxml")
    + collect_submodules("openai")
    + collect_submodules("flask")
)

datas = [
    ("translator/templates", "translator/templates"),
    ("translator/static", "translator/static"),
]

a = Analysis(
    ["packed_launcher.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="EpubTsuyaku",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
