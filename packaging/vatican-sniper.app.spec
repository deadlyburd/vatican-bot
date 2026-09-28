# -*- mode: python ; coding: utf-8 -*-
# macOS .app build (BUNDLE) for the Vatican Sniper desktop app.
#
# Set APP_NAME and TARGET_ARCH via env to control the bundle name and arch:
#   APP_NAME="Vatican Sniper (Apple Silicon).app" TARGET_ARCH=arm64 \
#       python -m PyInstaller packaging/vatican-sniper.app.spec
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(SPEC), ".."))
APP_NAME = os.environ.get("APP_NAME", "Vatican Sniper.app")
TARGET_ARCH = os.environ.get("TARGET_ARCH") or None

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

# Optionally bake google_credentials.json into the .app (single-client distribution).
# Only bundled when the file exists at build time — it is gitignored, never committed.
_creds = os.path.join(ROOT, "google_credentials.json")
if os.path.isfile(_creds):
    _datas.append((_creds, "."))

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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=TARGET_ARCH,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="vatican-sniper",
)

app = BUNDLE(
    coll,
    name=APP_NAME,
    icon=None,
    bundle_identifier="com.vatican.sniper",
    info_plist={
        "CFBundleDisplayName": APP_NAME.replace(".app", ""),
        "CFBundleName": "Vatican Sniper",
        "NSHighResolutionCapable": True,
        "LSApplicationCategoryType": "public.app-category.productivity",
    },
)
