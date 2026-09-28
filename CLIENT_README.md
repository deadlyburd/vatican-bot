# Vatican Sniper — Client Setup Guide

## What you need

- A Mac, Windows, or Linux computer with an internet connection
- A **residential internet connection** (home/office). Do **not** run it behind a
  datacenter VPN or cloud server — the Vatican's Cloudflare protection will block it.
- **Brave, Chrome, or Edge** installed (auto-detected; nothing else to install).

## Install

### macOS
1. Open the app that matches your Mac:
   - **Apple Silicon (M1/M2/M3/M4):** `Vatican Sniper (Apple Silicon).app`
   - **Intel:** `Vatican Sniper (Intel).app`
2. Drag it to Applications if you like.
3. The first time, right-click → **Open** → **Open** (to bypass Gatekeeper, since it's not notarized).

> The Apple Silicon build must be produced on an M-series Mac:
> `packaging/build_macos_arm64.sh` → outputs `dist/Vatican Sniper (Apple Silicon).app`.
> The Intel build is produced by `packaging/build_macos_app.sh` on an Intel Mac.

### Windows / Linux
Run `vatican-sniper.exe` (Windows) or `vatican-sniper` (Linux). If you were sent a
build script instead of a binary, run `packaging/build.bat` (Windows) or
`packaging/build.sh` (Linux) on your machine first.

## First-run setup (one time)

When you open the app, your browser opens `http://localhost:8765`.

1. **Settings tab** → paste the path to your `google_credentials.json` file (your
   sheet-access key). Save.
2. **Sheets tab** → paste your Google Sheet URL → **Connect** → it auto-detects the
   columns → **Add sheet** → **Save**.
3. (Optional) **Proxies tab** → add proxy IPs if you have any.

## Start / Stop

- **Start** begins booking. Each booking runs in its own browser window.
- Watch the **Status** tab; you'll also get a desktop notification for each
  "Hold active" / "Booking failed".
- **Stop** ends the run.

---

# How your Google Sheet must be set up

## One tab with these columns (any names — the app auto-maps them)

| Purpose | Required? | Example column name |
|---|---|---|
| Booking ID | ✅ must be unique per row | `Booking ID` |
| Date | ✅ | `Date` or `Activity Date` |
| Visitors | ✅ | `Pax` / `Guests` / `Visitors` |
| Customer name | ✅ | `Customer Name` |
| Email | ⬜ optional | `Email` |
| Product | ✅ | `Product` / `Tour` |
| Status | ✅ | `Status` |

> The app recognizes your columns automatically when you click **Connect**. If a
> column isn't detected, just pick it from the dropdown in the mapping grid.

## Which rows get booked

The app picks up a row when **all** of these are true:

1. **Product** contains one of: `vatican`, `sistine`, `musei`, `vaticani`
2. **Status** is `PENDING` or `CONFIRMED`
3. **Date** is today or in the future

Anything else is ignored. Once a row is booked, the app writes the result back:

| Written to | Value |
|---|---|
| Status column | `BOOKING` → `HELD` (reserved) → `PAID` / `FAILED` |
| Payment Link column (optional) | the payment URL when captured |

## Share the sheet with the service account (required)

The app reads your sheet through a Google **service account**. Your sheet must be
shared with it, otherwise the app gets "access denied":

1. Open your Google Sheet → **Share** (top-right).
2. Add this email as **Editor**:

   ```
   pointours@hydrasnipe.iam.gserviceaccount.com
   ```

3. Click **Send** / **Done**.

> If you're using your own service account instead, share the sheet with the
> `client_email` shown inside your `google_credentials.json` file.

## Getting a `google_credentials.json` (if you don't have one)

1. Go to [Google Cloud Console](https://console.cloud.google.com) → create a project.
2. **APIs & Services → Library** → enable **Google Sheets API** (and Drive API).
3. **IAM & Admin → Service Accounts** → Create Service Account.
4. Add a **Key** (JSON) and download it — that file is your `google_credentials.json`.
5. Share your sheet with the service account email (see above).

---

## Run at startup

- **macOS:** run `packaging/autostart/install_macos.sh "/path/to/Vatican Sniper.app/Contents/MacOS/vatican-sniper"`
- **Linux:** run `packaging/autostart/install_linux.sh "/path/to/vatican-sniper"`
- **Windows:** run `packaging/autostart/install_windows.bat "C:\path\to\vatican-sniper.exe"`

## Troubleshooting

- **Dashboard won't open:** browse to `http://localhost:8765` manually.
- **"access denied" on Connect:** the sheet isn't shared with the service account (see above).
- **Nothing books / "no slots":** the Vatican has no open tickets for those dates right now — it's genuinely sold out, not an error.
- **Logs:** `~/.vatican-sniper/vatican-sniper.log`
