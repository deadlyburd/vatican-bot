# Vatican Sniper — Windows Setup Guide

Runs the booking automation on a Windows PC. One browser process per booking,
local dashboard at `http://localhost:8765`.

---

## What you need

- **Windows 10 or 11** (64-bit)
- A **Chromium browser** installed: Brave, Chrome, or Edge (required at run time)
- A **residential internet connection** (home/office — not a datacenter/VPN, or Cloudflare will block it)
- **Python 3.11+** or **uv** (only needed to *build* the `.exe`; the client's PC does not need it)

---

## 1. Files & folders you need

Copy the **source package** to the Windows PC. It looks like this:

```
vatican-sniper-source/            ← copy this whole folder to the Windows PC
├── sniper_app.py                 ← app entry point
├── slot_finder.py                ← Vatican slot finder
├── requirements-desktop.txt      ← the 4 runtime deps
├── config.example.json
├── desktop_app/                  ← the whole app package
│   ├── server.py, dashboard.html, …
│   └── providers/ (vatican.py …)
└── packaging/
    ├── vatican-sniper.spec       ← PyInstaller build spec (Windows/Linux)
    ├── build.bat                 ← Windows build script  ← RUN THIS
    ├── vatican-sniper.app.spec   ← (macOS only — ignore)
    ├── build.sh, build_macos_*.sh
    └── autostart/
        └── install_windows.bat   ← optional: run at login
```

> Easiest: transfer **`vatican-sniper-source.zip`** (generated on the dev Mac via
> `packaging/package_source.sh`) and unzip it on the Windows PC. Same contents.

## 2. Install Python (or uv) — build machine only

**Option A — Python (recommended, standard):**
1. Download from <https://www.python.org/downloads/windows/> (64-bit installer).
2. Install with **"Add python.exe to PATH"** ticked.

**Option B — uv (faster, auto-manages Python):**
```powershell
winget install --id=astral-sh.uv -e
```

## 3. Build the .exe

Open **Command Prompt** in the source folder and run:

```bat
cd vatican-sniper-source
packaging\build.bat
```

The script auto-creates a `.venv`, installs the deps + PyInstaller, and builds.
(It uses `uv` if installed, otherwise falls back to `python -m pip`.)

### Output

```
dist\vatican-sniper\
├── vatican-sniper.exe        ← double-click this to run
└── _internal\                ← bundled runtime — keep together with the .exe
```

## 4. Verify the build (optional but recommended)

From a Command Prompt in the source folder:

```bat
dist\vatican-sniper\vatican-sniper.exe --self-test
```

Because the app is windowed, the result is written to a file instead of the console:

```
%USERPROFILE%\.vatican-sniper\self_test_result.txt
```

It should say: `SELF-TEST OK: playwright driver + CDP + browser all working`.

## 5. Run it

- **Double-click `vatican-sniper.exe`** (inside `dist\vatican-sniper\`).
- It starts a local server and opens **`http://localhost:8765`** in your browser.
- Logs: `%USERPROFILE%\.vatican-sniper\vatican-sniper.log`

> Windows SmartScreen may warn on first run (unsigned app): click
> **More info → Run anyway**.

## 6. First-run setup (one time)

1. **Settings** → paste the path to your `google_credentials.json` → Save.
2. **Sheets** → paste your Google Sheet URL → **Connect** → **Add sheet** → **Save**.
3. (Optional) **Proxies** → add proxy IPs.
4. **Start** begins booking; **Status** shows live progress; desktop toast
   notifications fire on each hold/failure.

## 7. Sheet requirements (same as every platform)

- One tab with columns: Booking ID, Date, Visitors, Customer name, Email (opt),
  Product, Status — **any names, auto-mapped on Connect**.
- A row is booked when: **Product** contains `vatican`/`sistine`/`musei`/`vaticani`,
  **Status** is `PENDING`/`CONFIRMED`, **Date** is today or future.
- The sheet must be **shared (Editor)** with the service-account email inside
  `google_credentials.json` (currently `pointours@hydrasnipe.iam.gserviceaccount.com`).
- Results are written back: Status → `BOOKING` → `HELD`/`PAID`/`FAILED`.

## 8. Run at startup (optional)

From the source folder:

```bat
packaging\autostart\install_windows.bat "C:\full\path\to\dist\vatican-sniper\vatican-sniper.exe"
```

This drops a shortcut into the Windows **Startup** folder so the app starts at login.

## 9. Troubleshooting

| Problem | Fix |
|---|---|
| `uv` / `python` not found during build | Install Python (step 2) and reopen Command Prompt |
| "access denied" on Connect | Sheet isn't shared with the service-account email |
| Nothing books / "no slots" | Vatican genuinely sold out for those dates |
| App won't open the browser | Browse to `http://localhost:8765` manually |
| No logs visible | Check `%USERPROFILE%\.vatican-sniper\vatican-sniper.log` |
