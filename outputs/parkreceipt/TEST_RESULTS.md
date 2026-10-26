# Database authentication fix — 17 October 2026

- **18 tests passed on SQLite and 18 tests passed on isolated MySQL 9.5.0.** Includes missing configuration, environment precedence, credential redaction, missing-schema diagnostics, startup validation, cookie-free 401 without database lookup, controlled runtime 503, and previous payment/permission/queue tests.
- Exact MySQL error **1045** reproduced with an intentionally incorrect password on an isolated temporary account. Valid credentials passed the same connection/schema check. Temporary account removed after verification.
- Configuration helper tested against that isolated instance: successful connection, percent-encoding of password special characters, atomic `.env` save with mode 0600. No real local MySQL account was modified.
- Existing host MySQL root access was rejected with 1045. Its account/password/grants therefore could not be inspected or repaired; valid database credentials must be supplied privately through the configuration helper.
- Existing backend process was not restarted or reconfigured. Restart it after setting verified credentials to load the code changes. No application records or existing databases were deleted.
- Docker/MySQL 8.4 remains unverified. One existing Starlette TestClient deprecation warning; no failures.

# Staff trial and launcher update — 16 October 2026

- **11 backend tests passed on SQLite**, including authenticated staff creation, wrong-location rejection, cash-only enforcement, idempotent staff retries, and queue visibility with 205 newer confirmed records.
- **4 frontend recovery tests passed**, including independent staff/customer drafts on one device. Existing customer recovery keys remain compatible.
- TypeScript checking and production build passed.
- Local launcher successfully migrated, seeded and started both servers using the existing Python environment and frontend dependencies. Its first-run dependency installation branch has not been exercised on a clean machine.
- Browser verified staff-a login, vehicle REHEARSAL01 entry, automatic return to the queue, rehearsal cash approval and receipt retrieval. The local database contains this fictional confirmed record; no money was collected.
- The two new backend tests have not yet run on MySQL. The previous nine tests passed on isolated MySQL 9.5, as recorded below.
- Docker/MySQL 8.4, real phones, QR scans and printing remain unverified.

# Verification update — 16 October 2026

- **9 backend integration tests passed on MySQL 9.5.0**, using a new isolated instance with TCP networking disabled. No existing databases were used. Tests include five concurrent request creations returning one request, five concurrent cash approvals returning one receipt, permissions, rate snapshots, demo separation, CSV filter parity and formula escaping, and India date boundaries.
- **Fresh Alembic migration passed on MySQL 9.5**, followed by successful seeding and browser login.
- **3 frontend recovery tests passed** using Node 24: exact payload/key recovery, location isolation and cleanup, storage denial, and corrupt draft handling.
- **TypeScript check and Vite production build passed** (78 modules).
- Browser verified that draft search changes do not alter the CSV link until Apply is clicked. The generated location sign was rendered and visually inspected; automated download event waiting timed out, so an on-page preview and explicit Save sign fallback were added. The generated PNG was saved from the rendered image.
- Browser verified that an API outage shows an error without confirmation and that a page refresh preserves the pending submission. After restarting the API, Retry recovered vehicle RECOVER01 and opened its server-backed pending cash status successfully. This browser test covered an unavailable API; concurrent replay after a committed request is covered by the MySQL integration test.
- Still unverified: Docker build/Compose runtime, MySQL 8.4 (the Compose target), actual phone scanning, mobile browser behavior, and physical printing. No live payment integration exists.
- The Starlette/httpx TestClient deprecation warning remains; no tests failed.

## Original verification — 15 October 2026


- Backend integration suite: **7 passed** using Python 3.14 and a disposable SQLite database. Includes concurrent approvals (five callers, one receipt), unauthorized and wrong-location access, server-controlled amounts, request idempotency, rate snapshots, demo success/failure/cancellation, demo disabling, session logout, India midnight boundaries, CSV retrieval, persistence across reconnection, and staff reassignment.
- One test dependency warning: Starlette reports deprecation of its httpx-based TestClient. Tests still passed.
- Frontend: `npm run build` passed TypeScript checking and Vite production compilation (77 modules).
- Alembic: initial migration applied successfully to an empty SQLite preview database; the final migration is frozen schema code.
- Browser smoke check in the Codex browser: home lists A/B/C at ₹30; Parking A form submits a fictional vehicle; online success issues a clearly labelled demo receipt; owner login succeeds; dashboard shows ₹30 demo total and ₹0 cash total.
- Browser layout inspected at the available desktop viewport. Print dialog, actual QR scanning, mobile devices, and download dialogs were not tested.
- MySQL, Docker image builds and deployment were **not executed** because Docker is unavailable on this machine. SQLite concurrency success does not establish MySQL behavior; rerun against an isolated MySQL database before operational use.
- No real money was collected, and no live online payment adapter is implemented.

The temporary preview used fictional vehicle `TEST001`. The source archive contains no preview database, credentials, installed dependencies or private customer records.
