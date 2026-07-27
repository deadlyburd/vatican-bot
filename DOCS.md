# Vatican Bot — Complete Documentation

## What This Is

A full-stack automation platform that monitors Vatican Museums ticket availability 24/7 across 60+ dates, auto-books tickets when slots open, and manages the entire resale pipeline — from CRM (Google Sheets) through booking to payment capture.

Built as a Docker-based microservices architecture deployed on a Hetzner cloud server (Ubuntu 26.04).

---

## Architecture Overview

```
                    ┌─────────────┐
                    │   NGINX     │  :80, :443 (reverse proxy)
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
         ┌────▼───┐   ┌───▼────┐  ┌───▼──────────┐
         │ BACKEND │   │FRONTEND│  │ CUSTOMER CARE │
         │ Django  │   │Next.js │  │ Telegram Bot  │
         │ :8000   │   │ :3000  │  │ (tourists)    │
         └────┬────┘   └────────┘  └───────────────┘
              │
    ┌─────────┼─────────┬──────────┬──────────────┐
    │         │         │          │              │
┌───▼──┐ ┌───▼───┐ ┌───▼───┐ ┌───▼────┐ ┌──────▼──────┐
│Redis │ │Postgre│ │Celery │ │Celery  │ │Telegram Bot  │
│Cache │ │ -SQL  │ │Worker │ │Beat    │ │(admin alerts)│
└──────┘ └───────┘ │:vatican│ │(sched) │ └──────────────┘
                   │ snipe  │ └────────┘
                   └───┬────┘
                       │
         ┌─────────────┼─────────────┐
         │             │             │
    ┌────▼────┐  ┌────▼────┐  ┌────▼────────┐
    │Chrome   │  │Chrome   │  │Chrome       │
    │Bot 1    │  │Bot 2    │  │Bot 3        │
    │VNC:5901 │  │VNC:5902 │  │VNC:5903     │
    │CDP:9222 │  │CDP:9223 │  │CDP:9224     │
    └─────────┘  └─────────┘  └─────────────┘

    ┌──────────┐  ┌───────────┐  ┌──────────────┐
    │Auto      │  │Master     │  │Extension     │
    │Pipeline  │  │Sync       │  │Bridge        │
    │CRM→Book  │  │Sheets sync│  │Ext→Commands  │
    └──────────┘  └───────────┘  └──────────────┘
```

### Service Descriptions

| Service | Purpose |
|---------|---------|
| **backend** (Django) | REST API, admin panel, business logic. Port 8000 |
| **frontend** (Next.js) | Agency dashboard with task management, holds, logs. Port 3000 |
| **nginx** | Reverse proxy routing to backend + frontend. Ports 80, 443 |
| **db** (PostgreSQL 15) | Primary database. All tickets, agencies, tasks, holds stored here |
| **redis** (Redis 7) | Message broker for Celery + cache layer. 512MB limit |
| **worker_vatican** (Celery) | Continuously scans Vatican API for ticket slots. Concurrency: 8 |
| **beat** (Celery Beat) | Scheduled task runner — periodic CRM scans, sheet syncs |
| **telegram_bot** | Sends admin alerts when slots found / bookings made |
| **customer_care_bot** | Tourist-facing Telegram bot. Uses Claude AI for conversations |
| **chrome_bot_1/2/3** | Headful Chrome instances with VNC remote access. Auto-fill forms, solve captchas, complete checkout |
| **auto_pipeline** | CRM scanner → finds customers needing tickets → triggers booking |
| **master_sync** | Rebuilds the Master sheet from Activity_Lines + Passengers data |
| **extension_bridge** | Dispatches booking commands to Chrome extension instances |

---

## Google Sheets Structure

### Primary CRM Sheet
- **Sheet ID:** `1YkDZgFZs-DiMJ9ECIECJZ3aNmpyWB66qzc2CeteI1Vg`
- **Service account:** `pointours@hydrasnipe.iam.gserviceaccount.com`
- **GCP Project:** `hydrasnipe`
- **Link:** `https://docs.google.com/spreadsheets/d/1YkDZgFZs-DiMJ9ECIECJZ3aNmpyWB66qzc2CeteI1Vg/edit`

### Sheet Tabs

| Tab Name | Purpose | Columns (key ones) |
|----------|---------|-------------------|
| **📊 Master** | Aggregated booking view. Auto-rebuilt by `master_sync.py` | Date, Time, Product, Pax, First Name, Last Name, Booking ID, Status, Confirmation, Payment Link, Missing Info, Ticket Type, Platform |
| **Activity_Lines** | Raw booking data from Bokun/Viator/other sources | All booking line items |
| **Passengers** | Individual passenger details per booking | First Name, Last Name, Type (Adult/Child/Infant), Booking ID |
| **Bookings** | Consolidated booking records | Booking ID, Date, Time, Product, Status, Payment |
| **Products** | Ticket product catalog | Product name, Vatican ticket type mapping |

### Bokun Mapping Sheet
- **Sheet ID:** `1MLEb4tKzCF3KWsgUiHGyqn-GaMgPIN0scEAWxFQvJT0`
- **Link:** `https://docs.google.com/spreadsheets/d/1MLEb4tKzCF3KWsgUiHGyqn-GaMgPIN0scEAWxFQvJT0/edit`
- **Tabs:** `Bookings_Input` (raw Bokun bookings), `Participants` (passenger details)

---

## External Integrations

### 1. Telegram (Required)
Two bots are needed:
- **Admin Bot:** Sends slot alerts, booking confirmations, and system status
- **Tourist Bot:** Customer-facing chatbot for booking inquiries (handled by `customer_care_bot`)

**Setup:**
1. Create a bot via [@BotFather](https://t.me/BotFather)
2. Get the token and add it to `.env` as `TELEGRAM_BOT_TOKEN`
3. Get your Telegram user ID from [@userinfobot](https://t.me/userinfobot)
4. Add it to `.env` as `ADMIN_TELEGRAM_IDS` (comma-separated for multiple admins)

### 2. Google Sheets API (Required)
**Setup:**
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project (or use existing `hydrasnipe`)
3. Enable Google Sheets API and Google Drive API
4. Create a Service Account
5. Download the JSON key → save as `google_credentials.json` in the project root
6. Share your Google Sheets with the service account email (as Editor)

### 3. Bokun API (Booking System)
Bokun is a tourism booking platform that feeds bookings into this system.
- **API Base:** `https://api.bokun.io`
- **Credentials needed:** Access Key + Secret Key (set in `.env`)
- Webhook endpoint receives new bookings in real-time
- `fetch_bokun_bookings.py` polls Bokun every 5 minutes as a fallback

### 4. Oxylabs ISP Proxies (Optional — Recommended)
Italian residential IPs to bypass Cloudflare geo-blocking on the Vatican site.
- **Host:** `isp.oxylabs.io`
- **Ports:** 8001-8013
- Set `OXYLABS_USERNAME` and `OXYLABS_PASSWORD` in `.env`

### 5. 2Captcha (Optional)
Fallback captcha solving if Turnstile auto-solve fails.
- Set `TWOCAPTCHA_API_KEY` in `.env`

### 6. DeepSeek AI (Optional)
Powers the AI admin assistant and CEO agent for automated CRM queries.
- Set `DEEPSEEK_API_KEY` in `.env`

### 7. Anthropic Claude (Optional)
Powers the tourist customer care chatbot.
- Set `ANTHROPIC_API_KEY` in `.env`

### 8. Clerk Authentication (Optional — Frontend)
User authentication for the Next.js dashboard.
- Set `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` and `CLERK_SECRET_KEY` in `.env`

---

## How the Booking Flow Works

### Monitoring Loop (Continuous)
1. `worker_vatican` (Celery) continuously polls the Vatican Search API
2. Checks 60+ dates simultaneously for availability
3. When a slot is found → fires a notification via Telegram

### Booking Flow (When Slot Found)
1. **Slot Detection:** Vatican API returns `AVAILABLE` status
2. **Notification:** Telegram alert sent to admin group
3. **Hold (optional):** Slot can be held via `hold_manager.py`
4. **Booking:** One of these methods completes the purchase:
   - **API + Playwright:** Headless browser navigates booking flow
   - **Chrome Bot:** Headful Chrome with VNC (human can watch/take over)
   - **Browser Extension:** Chrome extension on a local machine
5. **Form Fill:** Buyer info + participant names from CRM inserted
6. **Captcha:** Cloudflare Turnstile auto-solved via browser fingerprint
7. **Payment Redirect:** `epay.catholica.va` URL captured and stored
8. **Sheet Update:** Payment link written back to Google Sheets

### CRM-Driven Booking (Auto Pipeline)
1. `auto_pipeline.py` scans CRM for customers needing Vatican tickets
2. `SlotFinder` checks availability for each customer's date + visitor count
3. Booking commands created and dispatched to Chrome extension
4. After booking → epay link pushed back → sheet updated → Telegram sent

---

## Configuration Reference (.env)

```bash
# ── REQUIRED ──────────────────────────────────────
DATABASE_URL=postgres://postgres:postgres@db:5432/ticketbot
CELERY_BROKER_URL=redis://redis:6379/0
DJANGO_SECRET_KEY=<generate-a-random-key>

# ── TELEGRAM ──────────────────────────────────────
TELEGRAM_BOT_TOKEN=<from-botfather>
ADMIN_TELEGRAM_IDS=<your-telegram-id>

# ── GOOGLE SHEETS ─────────────────────────────────
GOOGLE_SERVICE_ACCOUNT_FILE=/app/google_credentials.json
GOOGLE_SHEET_ID=1YkDZgFZs-DiMJ9ECIECJZ3aNmpyWB66qzc2CeteI1Vg
GOOGLE_API_KEY=<google-api-key>
GOOGLE_SHEET_URL=<full-sheet-url>

# ── SERVER ────────────────────────────────────────
SERVER_BASE_URL=http://YOUR_SERVER_IP
ALLOWED_HOSTS=localhost,127.0.0.1,YOUR_SERVER_IP
DEBUG=False

# ── BOKUN API (Optional) ──────────────────────────
BOKUN_ACCESS_KEY=<bokun-access-key>
BOKUN_SECRET_KEY=<bokun-secret-key>

# ── PROXIES (Optional but recommended) ────────────
OXYLABS_USERNAME=<oxylabs-username>
OXYLABS_PASSWORD=<oxylabs-password>

# ── CAPTCHA (Optional) ────────────────────────────
TWOCAPTCHA_API_KEY=<2captcha-key>

# ── AI (Optional) ─────────────────────────────────
DEEPSEEK_API_KEY=<deepseek-key>
ANTHROPIC_API_KEY=<anthropic-key>

# ── FRONTEND AUTH (Optional) ──────────────────────
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=<clerk-pub-key>
CLERK_SECRET_KEY=<clerk-secret-key>

# ── MONITORING ────────────────────────────────────
VATICAN_CONCURRENCY=8
VATICAN_RPS=5
VATICAN_VISITORS=2
VATICAN_MONITOR_MODE=hybrid
```

---

## Quick Deploy

### Prerequisites
- Server with Docker and Docker Compose installed
- Ports 80, 443, 8000, 3000, 5901-5903 available

### Steps

```bash
# 1. Clone
git clone https://github.com/deadlyburd/vatican-bot.git
cd vatican-bot

# 2. Configure
cp .env.example .env
nano .env  # Fill in ALL values

# 3. Add Google credentials
# Place your google_credentials.json in the project root

# 4. Deploy
chmod +x deploy.sh
./deploy.sh

# Or for server-only (no frontend/nginx):
chmod +x deploy-server-only.sh
./deploy-server-only.sh

# 5. Create initial monitoring task
docker compose exec backend python /app/create_real_monitoring_task.py

# 6. Check everything is running
docker compose ps
docker compose logs -f
```

### Deploy Scripts

| Script | Use Case |
|--------|----------|
| `deploy.sh` | Full production deploy (backend + frontend + nginx + chrome bots) |
| `deploy-server-only.sh` | Server-only deploy (backend + workers + chrome bots, no frontend) |
| `deploy_and_setup.sh` | Deploy + auto-create monitoring tasks |

### Alternative: Server-Only Compose

```bash
# Use the streamlined config (no frontend/nginx)
docker compose -f docker-compose.server.yml up -d
```

### Alternative: AI Services Only

```bash
docker compose -f docker-compose.ai.yml up -d
```

---

## Useful Commands

```bash
# Check service status
docker compose ps

# View logs for specific service
docker compose logs -f worker_vatican
docker compose logs -f telegram_bot
docker compose logs -f backend --tail=100

# Restart a service
docker compose restart worker_vatican

# Run Django management commands
docker compose exec backend python manage.py shell
docker compose exec backend python manage.py createsuperuser

# Check Redis queues
docker compose exec redis redis-cli LLEN vatican

# Access Chrome Bot VNC
# Open VNC viewer → connect to your-server-ip:5901 (no password)

# Rebuild after code changes
docker compose build --no-cache
docker compose up -d

# Stop everything
docker compose down

# Full reset (WARNING: deletes all data)
docker compose down -v
docker compose up -d
```

---

## Key Scripts Reference

### Monitoring & Booking

| Script | Purpose |
|--------|---------|
| `book_from_recording.py` | Main auto-booker using nodriver (undetected Chrome) |
| `booker_playwright.py` | Playwright-based auto-booker |
| `booker_existing_chrome.py` | Book using already-running Chrome via CDP |
| `smart_booker.py` | Reads Master sheet, groups by date/time, books each group |
| `slot_finder.py` | Check Vatican API for available slots |
| `fast_recap_scanner.py` | Scan all dates in next 2 months, recap both standard + guided |
| `hold_agent.py` | Hold slots with keepalive |
| `hold_and_keepalive.py` | Hold workflow with auto-renewal |
| `extend_hold.py` | Extend an existing hold |
| `instant_sniper.py` | Ultra-fast booking when slot detected |
| `bulk_snipe_june15.py` | Bulk booking campaign for specific date |

### CRM & Sheets

| Script | Purpose |
|--------|---------|
| `master_sync.py` | Rebuild Master sheet from Activity_Lines + Passengers (runs as service) |
| `auto_pipeline.py` | CRM scanner → slot finder → booking commands (runs as service) |
| `extension_bridge.py` | CRM-sourced commands → Chrome extension dispatcher (runs as service) |
| `create_tasks_from_sheets.py` | Create monitoring tasks from sheet data |
| `fix_master.py` | Manual Master sheet rebuild |
| `rebuild_master_v2.py` | Alternative Master rebuild with newer logic |
| `create_bokun_sheets_mapping.py` | Map Bokun bookings to Google Sheets |
| `check_sheets.py` | Quick sheet connectivity test |
| `organize_sheets.py` | Organize sheet structure |

### Maintenance & Debugging

| Script | Purpose |
|--------|---------|
| `check_vatican_slots.py` | Quick slot availability check |
| `check_ts.py` | Check Turnstile status |
| `check_redis.sh` | Redis queue status |
| `check_queue.sh` | Task queue status |
| `debug_server.py` | Server connectivity debug |
| `debug_server_time.py` | Timezone sync debug |
| `verify_bot_health.py` | Full system health check |
| `clear_all_cooldowns.sh` | Reset all cooldowns |
| `clear_sweep_cache.sh` | Clear sweep cache |
| `reset_fast.sh` | Quick reset |

---

## Chrome Bots (Visual Booking)

Three headful Chrome instances run 24/7 with VNC remote access:

| Bot | VNC Port | CDP Port | Profile |
|-----|----------|----------|---------|
| chrome_bot_1 | 5901 | 9222 | Profile 1 |
| chrome_bot_2 | 5902 | 9223 | Profile 2 |
| chrome_bot_3 | 5903 | 9224 | Profile 3 |

**Connect via VNC:** `your-server-ip:5901` (no password)
**CDP endpoint:** `http://your-server-ip:9222/json`

The browser extension is auto-loaded into each Chrome instance from `./browser-extension/`.

---

## Browser Extension

Located in `browser-extension/`. A Chrome/Firefox extension that:
- Monitors Vatican ticket availability in real-time
- Sends desktop notifications when slots found
- Can be used standalone (without server) or integrated with the server

**Install manually:**
1. Chrome → `chrome://extensions/` → Enable Developer Mode
2. Click "Load unpacked" → Select `browser-extension/` folder

---

## Django Admin

Access at `http://your-server:8000/admin/`

### Key Models
- **Agencies** — Reseller agency accounts
- **MonitorTask** — Active monitoring configurations (date, visitors, ticket type)
- **BuyerProfile** — Customer payment info for checkout
- **HeldSlot** — Currently held ticket slots
- **TelegramGroup** — Telegram chat groups for notifications

### Creating a Superuser
```bash
docker compose exec backend python manage.py createsuperuser
```

---

## API Endpoints

### Health Check
```
GET /api/v1/health/
```

### Tasks
```
GET    /api/v1/tasks/           # List monitoring tasks
POST   /api/v1/tasks/           # Create monitoring task
GET    /api/v1/tasks/<id>/      # Task detail
```

### Holds
```
GET    /api/v1/holds/           # List held slots
POST   /api/v1/holds/           # Create hold
DELETE /api/v1/holds/<id>/      # Release hold
```

### Agencies
```
GET    /api/v1/agencies/        # List agencies
POST   /api/v1/agencies/        # Create agency
```

### Bokun Webhook
```
POST   /api/v1/bokun/webhook/   # Receive Bokun booking notifications
```

---

## Directory Structure

```
vatican-bot/
├── backend/                    # Django API
│   ├── core/                   # Settings, URLs, WSGI, Celery config
│   ├── monitors/               # Main app: models, tasks, views, migrations
│   ├── services/               # Bokun, Google Sheets, AI agent, auto-booker
│   └── management/             # Django management commands
├── frontend/                   # Next.js dashboard
│   └── src/
│       ├── app/                # App router pages (dashboard, admin)
│       ├── components/         # React components
│       └── lib/                # API client, utilities
├── chrome_bot/                 # Chrome automation Docker config
├── browser-extension/          # Chrome/Firefox monitoring extension
├── customer_care/              # Tourist Telegram bot
│   ├── bot/                    # Bot logic (Claude AI powered)
│   ├── channels/               # Telegram, Email, WhatsApp channels
│   └── config/                 # Bot configuration
├── crm_intelligence/           # CRM analytics + AI agents
│   ├── ai/                     # CRM analyzer
│   ├── parsers/                # Sheet parsers
│   └── sync/                   # CRM sync
├── ai_agents/                  # Autonomous AI agents
├── worker_vatican/             # Vatican monitoring workers
├── booking-engine/             # Booking logic (stub — being developed)
├── shared/                     # Shared utilities (stub)
├── nginx/                      # Reverse proxy config
├── docker-compose.yml          # Full production compose
├── docker-compose.server.yml   # Server-only compose (no frontend/nginx)
├── docker-compose.ai.yml       # AI services only
├── Dockerfile                  # Main Python/Django image
├── Dockerfile.frontend         # Next.js frontend image
├── requirements.txt            # Python dependencies
├── .env.example                # Environment template
└── DOCS.md                     # This documentation
```

---

## Troubleshooting

### Backend won't start
```bash
docker compose logs backend --tail=50
# Check: database reachable? migrations applied? .env variables set?
```

### Worker not finding slots
```bash
docker compose logs worker_vatican | grep "Vatican"
# Check: OXYLABS credentials valid? Vatican site accessible from server IP?
```

### Sheets sync not working
```bash
docker compose logs master_sync
# Check: google_credentials.json present? Sheet shared with service account?
```

### Chrome bot not accessible via VNC
```bash
docker compose logs chrome_bot_1
# Check: port 5901 open in firewall?
```

### Telegram notifications not arriving
```bash
docker compose logs telegram_bot
# Check: TELEGRAM_BOT_TOKEN correct? Bot added to group? Admin IDs set?
```

### Database issues
```bash
docker compose exec backend python manage.py migrate --run-syncdb
docker compose exec backend python manage.py showmigrations
```

---

## Security Notes

- **Rotate all credentials** before deploying — tokens/keys in this repo have been stripped, but you must generate your own
- **Never commit `.env`** — it's in `.gitignore`
- **Never commit `google_credentials.json`** — it's in `.gitignore`
- **PostgreSQL password** defaults to `postgres` — change in production
- **Chrome bots run as root** in their containers — isolate on a private network
- **VNC has no password** — restrict ports 5901-5903 via firewall
- **Django admin** at `/admin/` — use a strong password and restrict by IP

---

## Scaling

- **More monitoring capacity:** Increase `VATICAN_CONCURRENCY` in `.env` or add more worker replicas
- **More Chrome bots:** Duplicate the `chrome_bot_X` service block in `docker-compose.yml` (ports 5904+, 9225+)
- **Multiple servers:** Each server needs its own `.env` — point all at the same database for coordination
- **Production hardening:** Put PostgreSQL on a managed service, use Redis Cluster, add Cloudflare Tunnel instead of exposing ports

---

## Version Info

- **Django:** 4.2.7
- **Python:** 3.12
- **Next.js:** 16.1.4
- **PostgreSQL:** 15
- **Redis:** 7
- **Celery:** 5.3.4
- **Playwright:** 1.40.0
- **Docker Compose:** v2+
- **OS:** Ubuntu 26.04 LTS (original server)

---

_Generated with [Claude Code](https://claude.com/claude-code)_
