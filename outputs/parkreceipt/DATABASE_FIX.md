# What caused the backend error

The decisive line in the pasted trace is:

```text
OperationalError: (1045, "Access denied for user 'parkreceipt'@'localhost' (using password: YES)")
```

FastAPI was checking a login session. SQLAlchemy requested a database connection and PyMySQL tried to authenticate to MySQL. MySQL rejected the login before the session query could execute. The many middleware lines are the path the exception followed, not separate failures.

`using password: YES` means a password was supplied; it does not mean it was correct. Error 1045 may mean an incorrect username/password or no matching allowed MySQL user/host account. This trace does not establish a broken table, SQL syntax error, missing cryptography library, or a problem with the website account password.

## Defects corrected

1. **Silent example credentials.** Previously, a missing DATABASE_URL triggered a hardcoded connection using `parkreceipt` as both database username and password. No `.env` existed in this checkout at inspection time. That fallback is removed; database settings must be explicit.
2. **Configuration was not loaded from local files.** The backend now reads literal KEY=value settings from `backend/.env`, then project `.env`, preserving existing process/Compose variables. The private setup helper validates the connection and safely encodes special characters in passwords.
3. **Connection errors appeared on the first web request.** SQLAlchemy connects lazily. A startup check now verifies the connection and required tables before the API serves traffic. A read-only `check_db` command distinguishes login rejection, connection failure, nonexistent database, and missing application tables.
4. **Database outages escaped as unhandled server exceptions.** Operational database failures now return a controlled 503 response without raw SQL or credentials. An ambiguous payment result remains unknown; the client must retry the same request rather than assume failure or success.
5. **An unauthenticated session check queried the database unnecessarily.** An absent session cookie now returns 401 immediately.

## Finish connecting your existing MySQL server

From the project folder:

```sh
cd backend
. .venv/bin/activate
python -m app.configure_db
# If DATABASE_URL is already exported and you want to use the saved file:
unset DATABASE_URL
python -m app.check_db
```

The helper asks for MySQL host, port, database username, database password, database name and an optional Unix socket. Enter the credentials for the actual MySQL account. Do not enter the `owner` or `staff-a` web password. For a normal local MySQL installation use the correct local host/port, commonly 127.0.0.1 and 3306. The `db` hostname in the Compose example only resolves inside its container network.

The helper changes no server accounts, permissions or data. It only saves a verified DATABASE_URL to `backend/.env`. It does not save a rejected configuration. If the account does not exist or its password is unknown, use the MySQL administrator who manages that server to provide a valid dedicated account for the `parkreceipt` database. Do not delete the database or reset unrelated MySQL accounts to resolve this error.

If the diagnostic confirms that the connection works but application tables are missing:

```sh
alembic upgrade head
# For missing sample application accounts, set a SEED_PASSWORD of 12+ characters, then:
python -m app.seed
python -m app.check_db
```

The seed password is for newly created website accounts. Seeding does not reset existing website passwords. Stop and restart the existing backend process after configuration is verified:

```sh
uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

No default account/password or automatic switch to SQLite is used by the backend. `python3 start_local.py` remains an explicitly separate SQLite rehearsal option, not a repair of a MySQL login.

## Evidence and remaining limitation

18 tests passed on SQLite and MySQL 9.5. The exact 1045 error was reproduced using a wrong password on a temporary account in a separate socket-only MySQL instance. The correct password succeeded. The configuration helper also passed a test with password characters that need URL encoding.

The existing local MySQL server rejected passwordless root access. Its real credentials were unavailable, so its account state could not be inspected or changed. The code and diagnostic fixes are verified; your existing MySQL connection is not yet verified. No existing application database was deleted, reset or migrated during this repair.
