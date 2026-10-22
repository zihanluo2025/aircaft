# Turnaround

- https://turnaround.luozihan.space/

A mobile-first web app for an aircraft cabin cleaning leading hand. It tracks who is working a shift, who does which job on which aircraft, how long each aircraft took, and the cabin crew's signature. Several phones share the same data.


## Stack

| Layer | Technology |
| --- | --- |
| Frontend | Vue 3 (Composition API, `<script setup>`), Vite, plain CSS |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic v2 |
| Auth | Username and password, JWT bearer tokens, PBKDF2 password hashing |
| Database | PostgreSQL in production, SQLite for local development and tests |
| Delivery | Docker, docker-compose, nginx, GitHub Actions |

## Features

- **Morning and Night shifts.** Each shift has its own staff, flights, roster and report. The whole colour theme changes with the shift.
- **Roster import.** Paste from Excel or upload a CSV, in two layouts. The imported roster is kept as the plan.
- **Same-day changes.** Move someone between Early, Late and All day. Changes are marked against the plan and can be reverted.
- **Call in.** People added at short notice are tagged, with the time they were called.
- **Fixed roles for the day.** Driver, Toilet and Truck. Driver and Truck are chosen from people who hold the qualification.
- **Flights.** Arrivals sorted by expected time, delay, arrivals per hour, and the origin airport.
- **Real arrivals.** One tap pulls the shift's arrivals from FlightAware AeroAPI. Only international flights and Jetstar and Virgin Australia are kept. Cleaning records, crew, notes and signatures are never overwritten.
- **Per aircraft crew.** Section roles assigned per aircraft. The server rejects double booking and people who are not on duty.
- **Timer, notes and signature.** Start and finish, editable times, hand-drawn cabin crew signature.
- **Report.** Totals, per flight and per person tables, and a copyable text summary.
- **Live sync.** Screens refresh every 15 seconds and when the app returns to the foreground.

## Run with Docker

```bash
cp .env.example .env            # then set POSTGRES_PASSWORD and SECRET_KEY
docker compose up -d --build
docker compose exec backend python -m scripts.create_user lead 'a long password' --name "Your Name"
# optional demo data (fictional names and flights)
docker compose exec backend python -m scripts.seed_demo
```

Open <http://localhost:8080>.

## Run for development

```bash
make backend-install && make frontend-install
make seed                 # demo data and the login demo / demo-password-1
make backend-dev          # API on http://localhost:8000, docs at /docs
make frontend-dev         # app on http://localhost:5173 (proxies /api to the API)
```

Without `make`:

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload
cd frontend && npm install && npm run dev
```

## Tests

```bash
cd backend && pytest      # parser, summary, security, and API tests against in-memory SQLite
cd frontend && npm test   # time helpers
```

CI runs both, builds the frontend, and builds both Docker images (`.github/workflows/ci.yml`).

## Project layout

```
backend/
  app/
    main.py              FastAPI app and router wiring
    models.py            SQLAlchemy tables
    schemas.py           Pydantic request and response models
    security.py          password hashing, JWT
    deps.py              current-user dependency
    routers/             auth, staff, roster, flights, flight_data, report
    services/            roster_import, summary, domain helpers, flight_data (AeroAPI client and filter), flight_sync
    migrations.py        adds new columns to older databases on startup
  scripts/               create_user, seed_demo, check_flight_api
  tests/
frontend/
  src/
    api.js               fetch wrapper
    store.js             shared reactive state and actions
    components/          header, tabs, flights, crew, report, flight sheet, signature pad
    lib/time.js          date and time helpers
  nginx.conf             serves the app and proxies /api
docker-compose.yml
```

## Data model

- `users`: leading hands who can sign in
- `staff`: a person, their team (morning or night), qualifications (Driver, Truck)
- `roster_entries`: a person on one day of one shift, with the planned shift, today's shift, fixed role, call-in time
- `flights`: one aircraft turnaround, with origin, times, notes, signature, and a snapshot of the fixed role holders taken when cleaning starts
- `assignments`: per aircraft jobs and who does them
- `flight_sync_log`: each FlightAware update, used for the throttle and the monthly quota

The snapshot means that changing the Driver at lunchtime does not rewrite the records of aircraft already cleaned.

## API

Interactive docs are served at `/docs` when the backend is running. Main routes:

| Route | Purpose |
| --- | --- |
| `POST /api/auth/login` | sign in, returns a token |
| `GET/POST/PATCH/DELETE /api/staff` | team members (delete keeps history) |
| `GET /api/roster?date=&shift=` | the day's roster |
| `PATCH /api/roster/{staff_id}?date=&shift=` | change shift, fixed role, call in, take off |
| `POST /api/roster/import/preview`, `POST /api/roster/import` | roster import |
| `GET/POST /api/flights`, `PATCH/DELETE /api/flights/{id}` | flights |
| `PUT /api/flights/{id}/assignments` | per aircraft crew |
| `POST /api/flights/{id}/start`, `/finish`, `/reopen` | cleaning timer |
| `PUT/DELETE /api/flights/{id}/signature` | cabin crew sign-off |
| `GET /api/flight-data/status` | filter in force, last update, result sets used this month |
| `POST /api/flight-data/sync` | pull the shift's arrivals from FlightAware |
| `GET /api/report?date=&shift=` | totals and the summary text |

## Flight data (FlightAware AeroAPI)

```bash
cp backend/.env.example backend/.env        # then put your key in FLIGHT_API_KEY
cd backend
python -m scripts.check_flight_api --shift morning --raw    # try the key, prints a sample record and the filtered list
```

- **Filter.** International means the origin airport's ICAO code does not start with `Y`. The default keeps international flights plus the airlines in `FLIGHT_AIRLINES` (`JQ`, `VA`). Set `FLIGHT_FILTER_MODE=all` to require both. Everything else is dropped.
- **Shift windows.** Arrivals are placed in Morning (`MORNING_WINDOW`) or Night (`NIGHT_WINDOW`) by their scheduled gate time in `AIRPORT_TZ` (Adelaide). Morning is 06:00 to 13:00. Night is everything else, 13:00 to 06:00 the next morning, and flights after midnight belong to the previous day's night shift.
- **What an update touches.** It adds new flights and refreshes time, gate, registration and landed or cancelled state. It never changes a flight once cleaning has started, and never touches crew, notes or signatures.
- **Cost control.** FlightAware bills per result set of 15 flights. An update is limited by `FLIGHT_MAX_PAGES`, throttled by `FLIGHT_SYNC_MIN_INTERVAL_SECONDS`, and stops at `FLIGHT_MONTHLY_CALL_LIMIT` result sets a month. The limit is counted by this app, so check your usage on the FlightAware portal too.
- **Terms.** FlightAware's personal plan is for personal use. Check its terms before relying on it for work.

## Roster import formats

```
Name,13/10/2026,14/10/2026        Date,Name,Shift,Role
Alex K,Early,All day              13/10/2026,Alex K,Early,Driver
Priya S,Late,Off
```

Dates are day first. Shifts are `Early`, `Late`, `All day` (also `E`, `L`, `A`). `Off` or blank means not working. The optional `Role` column (`Driver` or `Truck`) marks who is qualified.

## Deploying

1. Get a small Linux server (any VPS) with Docker installed and a domain name pointing at it.
2. Copy the project, create `.env` with strong secrets, run `docker compose up -d --build`, then create a user.
3. Put HTTPS in front. The copy button and installing to the home screen both need it. Caddy is the shortest route:

```
turnaround.example.com {
    reverse_proxy localhost:8080
}
```

4. Back up the `dbdata` volume (`docker compose exec db pg_dump -U turnaround turnaround > backup.sql`).

## Security notes

- Set a long random `SECRET_KEY`. The backend refuses to start with the default key when `ENV=production`.
- There is no public sign-up. Create users with `scripts.create_user`.
- Login attempts are not rate limited. Put the site behind a proxy that does so if it is exposed to the internet.
- Staff names and signatures are personal data. Keep the database private, and check with your employer before storing real data.

## Roadmap

- Alembic migrations (tables are currently created on startup)
- Offline support with a service worker
- Roles for managers (read only) and an audit log
