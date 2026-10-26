# ParkReceipt — research MVP

A small React + TypeScript / FastAPI / SQLAlchemy application for testing QR parking requests, staff cash confirmation, and digital receipts at three locations. MySQL is the intended shared source of truth. Online payment is a simulation and never collects money. The entire interface and CSV exports identify this as a research prototype.

## MySQL access denied (1045)

See `DATABASE_FIX.md` for the error explanation and verified fix. Database credentials are separate from the website's owner/staff credentials. The backend no longer falls back to the example `parkreceipt` password. It reads process environment settings first, then `backend/.env`, then the project `.env` (literal KEY=value settings; no variable expansion).

To configure an existing local MySQL account, activate the backend environment and run `python -m app.configure_db`. This prompts privately for database credentials, verifies them, and saves `backend/.env` with owner-only permissions. It does not reset accounts or create databases. Run `python -m app.check_db` before starting Uvicorn. If DATABASE_URL was previously exported, it takes precedence over the file; unset it if you intend to use the saved settings.

## Quick local rehearsal (macOS / Linux)

From this project folder, run:

```sh
python3 start_local.py
```

Requires Python 3.12+ and Node 22+. The launcher installs missing dependencies, migrates and seeds a private SQLite rehearsal database, and starts the API and frontend at http://localhost:5173. It prints a randomly generated local password for `owner`, `staff-a`, `staff-b`, and `staff-c`; that password is also stored in `.runtime/login-password.txt` with owner-only file permissions. Records persist in `.runtime/rehearsal.db`. Ctrl+C stops both servers. Keep `.runtime/` private and out of shared source archives.

This launcher always uses its own SQLite database and binds to this computer only. It is for workflow rehearsal, not a multi-phone operational pilot. Use the MySQL setup below for a shared deployment. If a port is occupied, the launcher stops with an explanation instead of silently switching ports. Developers can reuse an existing Python environment with `PARKRECEIPT_PYTHON=/absolute/path/to/venv/bin/python`.

Staff can choose **Enter vehicle**, submit a cash request, return directly to the queue, confirm the rehearsal cash, and open the receipt. Staff entry is authenticated and restricted to the assigned location. Pending requests are listed oldest first (up to 200), separately from the latest 50 confirmed receipts, so a long receipt history cannot hide the waiting queue. Customer and staff retry drafts are separate even on the same phone.

## Start with Docker Compose

Install Docker with Compose, then from this folder:

```sh
cp .env.example .env
# Edit .env and replace all password placeholders.
# Use matching MYSQL_PASSWORD and the password inside DATABASE_URL.
# URL-encode special characters in DATABASE_URL passwords.
docker compose up --build
```

Open http://localhost:5173. The first start migrates the database and creates three sample locations at ₹30 per visit. Sign in as `owner`, `staff-a`, `staff-b` or `staff-c`, using the `SEED_PASSWORD` you set. Do not reuse a personal password. Seed accounts share that initial password for rehearsal only; assign individual credentials before operational use. Seeding is repeatable and does not reset existing passwords. Database records survive container restarts in the `mysql_data` volume. `docker compose down` retains that volume; deleting it destroys records.

For a phone on the same network, configure `APP_ORIGIN=http://YOUR-LAN-IP:5173`, restart the API, and open that URL on the phone. Download QR codes from the owner page at that same reachable address. A QR generated at `localhost` cannot work on someone else's phone. Use HTTPS and `COOKIE_SECURE=true` on any public deployment. This project is delivered locally because Sites hosting cannot run its Python/MySQL backend.

## Five-minute walkthrough

1. Open Parking A from the home page and submit a fictional plate with Pay Cash.
2. Keep the status tab open. In another tab sign in as `staff-a`; match the reference and click **Cash received** only after collecting the rehearsal payment.
3. The customer status polls every four seconds while pending. Open the confirmed receipt and use browser Print / Save as PDF.
4. Sign in as `owner`. Today's cash total and count now reflect the recorded confirmation. Demo totals remain separate.
5. Submit another request with Pay Online (Demo). Try success, failure, pending or cancellation. Only simulated success issues a demo receipt.
6. Change a sample rate, create a new request, and compare it to an existing request. Existing quotes retain their original amount.
7. Export CSV, download location QR codes, or reassign staff from the owner page.

The optional phone field is stored but never sends an SMS. A customer without a phone can have the attendant enter a cash request; this digital-only app cannot provide a takeaway paper receipt without a printer or another channel.

## Run without Docker (development)

Requires Python 3.12+ and Node 22+. Start with a MySQL database and a `DATABASE_URL` suitable for your host, or use SQLite **only for a local rehearsal**:

```sh
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL='sqlite:////tmp/parkreceipt-local.db'
export SEED_PASSWORD='choose-a-unique-rehearsal-password'
export PAYMENT_MODE=demo
export APP_ORIGIN=http://localhost:5173
alembic upgrade head
python -m app.seed
uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

In another terminal:

```sh
cd frontend
npm ci
npm run dev -- --port 5173
```

Vite forwards `/api` to the Python server. Docker uses Nginx for the same same-origin routing. Cookies are opaque, hashed in the database, HttpOnly, SameSite Strict, and expire after eight hours. Session records persist across restarts. Passwords use Argon2. API access logs are disabled by the supplied launch commands because URLs carry private receipt tokens.

## Code map

- `backend/app/models.py`: database tables, integer-paise money, UTC timestamps and uniqueness constraints.
- `backend/app/main.py`: API, authentication, permissions, confirmations, reports and export. A conditional update wins a payment transition; receipt and audit creation commit in the same transaction.
- `backend/app/seed.py`: sample locations and rehearsal accounts from an environment password.
- `backend/migrations/`: Alembic schema setup. Future schema changes should be additional migrations.
- `frontend/src/main.tsx`: customer, pending, receipt, staff and owner screens. Shared records are in the backend, never localStorage.
- `frontend/src/style.css`: responsive layout and printable receipts.
- `backend/tests/test_flow.py`: focused integration tests.
- `RESEARCH_PLAN.md` and `research_observations.csv`: an experiment plan and blank observation template.

## API overview

Interactive request schemas: FastAPI `/docs` when accessing the backend directly (development port 8000).

| Endpoint | Purpose / access |
| --- | --- |
| GET `/api/locations`, `/api/locations/{slug}` | Public location and rate |
| POST `/api/requests` | Public creation; client idempotency key, server price |
| GET `/api/requests/{token}` | Bearer-secret status |
| POST `/api/requests/{token}/cancel` | Cancel an unpaid bearer-secret request |
| POST `/api/requests/{token}/simulate` | Demo-only outcomes, disabled outside demo mode |
| GET `/api/receipts/{token}` | Confirmed bearer-secret receipt only |
| POST `/api/login`, `/api/logout`; GET `/api/me` | Session access |
| GET `/api/staff/requests` | Assigned location's oldest 200 pending / latest 50 confirmed cash requests |
| POST `/api/staff/requests` | Assigned staff or owner creates a cash request |
| POST `/api/staff/requests/{token}/approve` | Assigned staff or owner cash confirmation |
| GET `/api/owner/report`, `/api/owner/export` | Owner-only filters, pagination / CSV |
| PATCH `/api/owner/locations/{id}` | Owner-only rate in paise |
| GET `/api/owner/users`; PATCH `/api/owner/users/{id}` | Owner staff assignments |

Receipt links are long random bearer secrets: anyone you share one with can read that receipt. There is no sequential-ID or vehicle-only public lookup. Confirmed payments cannot be deleted or edited through this API. CSV cells are escaped against spreadsheet formula execution. Reports display India dates; UTC storage is converted using Asia/Kolkata daily boundaries.

## Checks

```sh
cd backend
# Uses a disposable SQLite database by default. Never point tests at a real database:
# the test fixture drops and recreates all application tables.
python -m pytest -q
cd ../frontend
npm run build
# With Node 24+ (or a Node release supporting TypeScript stripping):
node --test tests/recovery.test.mjs
```

See `TEST_RESULTS.md` for the actual results from this build. Set `TEST_DATABASE_URL` to a **dedicated disposable MySQL database** to run the same tests on MySQL before a pilot. Do not use your pilot database. The updated suite passed on isolated MySQL 9.5. The Compose target, MySQL 8.4, still needs its own deployment check.

## Updates — 16 October 2026

Refresh recovery now preserves unanswered submissions across reloads in the same tab. CSV exports and pagination follow the last successfully applied filters, even when draft filter fields change. Location signs include instructions and demo labels, with preview and save fallback. MySQL transaction and migration checks now pass on a disposable MySQL 9.5 instance.

## Deliberate rough edges and next steps

This is a single-worker research tool: rate limiting is process-local, staff listing is capped at 200 pending plus 50 confirmed, report filtering loads matching rows in memory, and polling is four-second intervals. Unanswered submissions keep their exact payload and retry key in sessionStorage for that tab. Refreshing and retrying recovers the same server request. Closing the tab or clearing its storage loses recovery; do not do that while the outcome is unknown. No payment state is trusted from browser storage. Staff must match references carefully. There is no offline payment confirmation, receipt delivery, account administration UI, password reset, refund flow, independent cash verification, or production monitoring. QR downloads are labelled 1200×1600 PNG signs with an on-page preview and Save sign fallback. They omit the price to avoid stale printed rates; the customer page shows the current quote. The sample sign supplied with the project uses localhost and is for illustration only; regenerate it at a phone-reachable URL before a trial. No page-view analytics are collected.

Before wider use, add durable throttling, indexed/database-aggregated reporting, expired-session cleanup, explicit retention and deletion tooling, tested backups, individual staff credentials, and a reviewed deployment. Start with the small experiment in `RESEARCH_PLAN.md`.

Live online integration is intentionally absent. A later adapter needs backend-created gateway orders with server-controlled INR amount, checkout, signature verification, verified captured/paid status, signed webhooks, deduplicated events, and reconciliation of delayed results. Match order, amount, currency and payment identity before issuing a real receipt. Never treat a redirect, screenshot or client callback as confirmation. Read the provider's current official documentation when implementing that adapter; no live provider documentation was relied on or verified for this simulation.
