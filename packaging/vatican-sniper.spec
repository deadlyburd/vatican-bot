# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the Vatican Sniper desktop app.
# One-folder build (COLLECT) so the bundled Playwright node driver stays on disk.
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(SPEC), ".."))

# Bundle the Playwright driver (needed even for connect_over_cdp).
_pw_driver = None
try:
    import playwright
    _candidate = os.path.join(os.path.dirname(playwright.__file__), "driver")
    if os.path.isdir(_candidate):
        _pw_driver = _candidate
except Exception:
    pass

_datas = [
    (os.path.join(ROOT, "desktop_app", "dashboard.html"), "desktop_app"),
    (os.path.join(ROOT, "config.example.json"), "."),
]
if _pw_driver:
    _datas.append((_pw_driver, "playwright/driver"))

a = Analysis(
    [os.path.join(ROOT, "sniper_app.py")],
    pathex=[ROOT],
    binaries=[],
    datas=_datas,
    hiddenimports=[
        "slot_finder",
        "gspread",
        "google.oauth2.service_account",
        "google.oauth2.credentials",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "test", "unittest", "pytest", "django"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="vatican-sniper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # windowed/double-click app; logs go to ~/.vatican-sniper/
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="vatican-sniper",
)
