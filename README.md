# work-tracker

Simple tracker for daily tasks: working hours, overtime balance, PTO and task entries for the
monthly work report. A Falcon REST API with a small browser frontend, backed by SQLite, run locally.

The project was partially implemented using claude.ai.

> Calculation rules, storage, spreadsheet import, REST API and frontend are done; later ideas are listed in
> `docs/TASKS.md`.

## Requirements

- Python 3.15
- [Pipenv](https://pipenv.pypa.io/)
- Node.js 26.13 (pinned in `.node-version`, e.g. via [fnm](https://github.com/Schniz/fnm)) for building the frontend

## Setup

```shell
pipenv install --dev
fnm use          # Node version from .node-version
npm install
npm run build    # compile the frontend: src/templates/ts → src/templates/static/js
```

The compiled JavaScript is not committed; build it after checking out or changing TypeScript (`npm run watch` rebuilds
on every change).

## Start from zero

Without a spreadsheet, e.g. when starting a new job. A new database file is created and migrated on the first
start; it comes with the settings, PTO years and services of the original setup, which the steps below replace.

1. Start the app on a new database file:

   ```shell
   export WORK_TRACKER_DB=work_tracker.db  # a file that does not exist yet
   pipenv run python -m src
   ```

2. Set the first day of the overtime balance, and an opening balance in minutes if overtime is taken over (otherwise 0).
   There is no page or API for this yet (task L.1), so it is set in the database (`sqlite3`):

   ```shell
   sqlite3 "$WORK_TRACKER_DB" "UPDATE settings SET value = '2027-03-01' WHERE key = 'balance_start'"
   sqlite3 "$WORK_TRACKER_DB" "UPDATE settings SET value = '0' WHERE key = 'opening_balance'"
   ```

3. Enter the PTO days per year, pro rata in the first one (March–December of 30 days: 25). Years before the start
   day are ignored; a year without entry has no PTO account. Also possible in `/apidoc/swagger`:

   ```shell
   curl -X PUT localhost:8000/api/pto-years/2027 -H 'Content-Type: application/json' \
     -d '{"allowance": 25, "note": "pro rata from March"}'
   curl -X PUT localhost:8000/api/pto-years/2028 -H 'Content-Type: application/json' -d '{"allowance": 30}'
   ```

4. Replace the services on `/lists` with those of the new job; adjust the activity types if needed.

5. Record every day in the week view (`/`): times, day type (PTO, sick, …) and entries. From the start day on,
   each weekday counts −8:00 until its times are entered (today included); weekends and Berlin public holidays
   need nothing. The 8:00 target and the Berlin holidays are fixed for now (task L.1).

## Import the spreadsheet

One CSV export per year; the database is `$WORK_TRACKER_DB`, or `work_tracker.db` in the working directory.

```shell
pipenv run python -m src.modules.importer "examples/Time_tracking_DK - 2024_Data.csv"
pipenv run python -m src.modules.importer "examples/Time_tracking_DK - 2024_Data.csv" --replace  # import a year again
```

A year is imported in one transaction: on any error nothing is written. `--replace` deletes the year's days,
entries, history and flags first; tickets keep their assigned services.
After the import, a reconciliation compares every day up to today with the sheet and shows the overtime
balance and the year's PTO account.

## Run the app

```shell
pipenv run python -m src                       # http://127.0.0.1:8000/
pipenv run gunicorn 'src.app:create_app()' --reload  # alternative with auto-reload
```

Open http://127.0.0.1:8000/ for the frontend (build it first with `npm run build`): the current week,
other weeks via `/?week=2026-W44`; days and entries are edited in place (`&edit=2025-12-06` opens a day's form,
`&entry=129` an entry's form; each entry shows its change history). `/month` shows the month report with the work report
(coding hours by service and ticket), `/year` the year report (totals, PTO account, balance month by month); `/review`
lists what needs attention after
the import: guessed tickets (confirm, rename or split), entries without duration or ticket, flagged days, and tickets
without service (assign one to several at once). `/lists` manages services and activity types (add, edit, delete;
an activity type used by entries cannot be deleted). `/components` is a
gallery of the UI components, each with its use and the HTML to copy. The database (`$WORK_TRACKER_DB` or
`work_tracker.db`) is migrated on start. API documentation:
`/apidoc/swagger`, `/apidoc/redoc` or `/apidoc/scalar`; the OpenAPI spec is at `/apidoc/openapi.json`.
These documentation routes are listed in the spec as well, under the Maintenance tag.
`$WORK_TRACKER_HOST` and `$WORK_TRACKER_PORT` change the address of the development server.

## Tests and code quality

```shell
pipenv run pytest
pipenv run flake8 --count --exit-zero --radon-max-cc 6 --radon-no-assert --max-line-length=127 \
  --statistics --exclude=.idea,.venv,test,.terraform --extend-ignore=E203,W503,ANN101,ANN102
```

```shell
npm test           # frontend tests (Node runs the TypeScript tests directly)
```

## API types for the frontend

The TypeScript types of the API are generated from its OpenAPI spec. After changing the API, run

```shell
npm run api-types  # writes src/templates/openapi.json, generates src/templates/ts/api-types.ts
```

and commit both files; a test fails while `openapi.json` is outdated. The generator (`openapi-typescript`)
runs through `npx` with its own TypeScript 5, as it does not support the project's TypeScript 7 yet.

## Project layout

| Path                   | Contents                                                                                                                                                                                                                                                                                                                                                                                                     |
|------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `src/app.py`           | WSGI app: routes, storage errors as 404 / 409, API docs                                                                                                                                                                                                                                                                                                                                                      |
| `src/__main__.py`      | Development server (`python -m src`)                                                                                                                                                                                                                                                                                                                                                                         |
| `src/lib`              | Calculation rules: durations, breaks, holidays, targets, overtime, PTO                                                                                                                                                                                                                                                                                                                                       |
| `src/models`           | Pydantic models                                                                                                                                                                                                                                                                                                                                                                                              |
| `src/modules`          | Features: storage, import, days, entries, tickets, catalog, PTO years, reports, review, pages                                                                                                                                                                                                                                                                                                                |
| `src/utils`            | Shared helpers; `spec`: OpenAPI docs and validation (spectree); `api`: shared API types; `openapi`: spec file for the frontend types                                                                                                                                                                                                                                                                         |
| `src/defaultresources` | Default resource at `/health` (plain-text status)                                                                                                                                                                                                                                                                                                                                                            |
| `src/templates`        | Frontend: `frame.html` (shared page frame), `pages/` (page content), `static/` (served at `/static`: `css/main.css` with the UI style variables, Inter font with its OFL license in `fonts/`), TypeScript in `ts/` (`main.ts` loads the page code, e.g. `week.ts`; `api.ts`: typed API client, `api-types.ts`: generated) compiled to `static/js/` (git-ignored), `openapi.json`, frontend tests in `tests/` |
| `src/tests`            | Tests, mirroring the packages above                                                                                                                                                                                                                                                                                                                                                                          |

## API (`src/modules/<feature>`)

JSON over HTTP; dates in ISO format (`2026-10-28`), clock times as `HH:MM`, durations as `h:mm` (`-1:30`).
Invalid input gives 422, unknown records 404, conflicts 409.
Reports count worked time, target and overtime up to today (today included); planned days off count too.

| Endpoint                                             | Method           | Description                                                                                                                         |
|------------------------------------------------------|------------------|-------------------------------------------------------------------------------------------------------------------------------------|
| `/health`                                            | GET              | Status in plain text (Maintenance)                                                                                                  |
| `/apidoc/openapi.json`                               | GET              | OpenAPI specification (Maintenance)                                                                                                 |
| `/apidoc/swagger`, `/apidoc/redoc`, `/apidoc/scalar` | GET              | API documentation pages (Maintenance)                                                                                               |
| `/api/days`                                          | GET              | Every calendar day of `?week=2026-W44` or `?start=…&end=…` (max. 366 days): day type, times, worked, target, overtime, flags        |
| `/api/days/{date}`                                   | GET              | One calendar day, recorded or not                                                                                                   |
| `/api/days/{date}`                                   | PUT              | Record a day: `day_type`, `start`, `end`, `break_time` (empty: legal minimum), `note`                                               |
| `/api/days/{date}`                                   | DELETE           | Delete a recorded day and its review flags                                                                                          |
| `/api/entries`                                       | GET              | Entries of `?week=…` or `?start=…&end=…`, with service, activity type, flags and `changed` marker                                   |
| `/api/entries`                                       | POST             | Create a ticket entry (`ticket_key`, `description`, `coding`, optional `service_id`) or activity entry (`activity_type_id`, `note`) |
| `/api/entries/{id}`                                  | GET              | One entry                                                                                                                           |
| `/api/entries/{id}`                                  | PUT              | Change an entry (same kind); a given `service_id` applies to all entries of the ticket                                              |
| `/api/entries/{id}`                                  | DELETE           | Delete an entry and its flags; the history is kept                                                                                  |
| `/api/entries/{id}/history`                          | GET              | Change history of an entry (also after deletion)                                                                                    |
| `/api/entries/{id}/split`                            | POST             | Divide a ticket entry among several tickets (`ticket_keys`), hours split evenly; recorded in the history                            |
| `/api/tickets`                                       | GET              | All tickets with service and number of entries; `?without_service=true` for review                                                  |
| `/api/tickets/{key}`                                 | GET              | A known ticket with its remembered service (pre-fill)                                                                               |
| `/api/tickets/{key}`                                 | PUT              | Set or unassign the service (`service_id`); applies to all entries of the ticket                                                    |
| `/api/tickets/assign-service`                        | POST             | One service for several tickets: `keys`, `service_id` (all or nothing)                                                              |
| `/api/tickets/{key}/rename`                          | POST             | Rename to `new_key`, or merge into an existing ticket (keeps its service); recorded in the history                                  |
| `/api/reports/weeks/{week}`                          | GET              | Week (`2026-W44`): worked, target, overtime up to today, balance before and after, days off                                         |
| `/api/reports/months/{month}`                        | GET              | Month (`2026-10`): totals, days off, PTO days and the work report: coding hours by service and ticket                               |
| `/api/reports/years/{year}`                          | GET              | Year: totals, per month, days worked and average, days off, PTO account                                                             |
| `/api/pto-years`                                     | GET              | PTO days per year: `allowance`, `extra_days`, `carried_over` (empty: remainder of the year before), `note`                          |
| `/api/pto-years/{year}`                              | GET, PUT         | Read or enter the PTO days of a year (insert or replace); a year without entry has no PTO account                                   |
| `/api/review`                                        | GET              | What needs attention: tickets without service, entries with 0:00 / without ticket / import flag, flagged days                       |
| `/api/review/flags/{id}`                             | DELETE           | Clear a review flag of an entry or a day                                                                                            |
| `/api/services`, `/api/activity-types`               | GET, POST        | List and add (names unique)                                                                                                         |
| `/api/services/{id}`, `/api/activity-types/{id}`     | GET, PUT, DELETE | Read, change, delete (activity types in use cannot be deleted; deleting a service unassigns its tickets)                            |

## Calculation rules (`src/lib`)

All times and durations are whole minutes.

| Module            | Rules                                                                                                                                                                                                                                          |
|-------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `durations`       | Parse and format clock times (`HH:MM`), durations (`h:mm`) and decimal-comma hours (`1,5`); split durations evenly in quarter hours                                                                                                            |
| `worktime`        | Worked time = end − start − break; without a break, the legal minimum applies (German ArbZG §4: 0:30 beyond 6 h, 0:45 beyond 9 h)                                                                                                              |
| `public_holidays` | Berlin public holidays (via `holidays`), plus Heiligabend and Silvester as company half days                                                                                                                                                   |
| `daytypes`        | Day types (see below) with target time and PTO used; weekends have no target. Overtime = worked − target                                                                                                                                       |
| `balances`        | Overtime balance over every calendar day up to a cut-off date (a weekday without record counts as −8:00); PTO per year from its terms (allowance + extra days; carry-over fixed or the remainder of the year before): used, planned, remaining |
| `dates`           | Date range helper                                                                                                                                                                                                                              |

### Day types

Targets and PTO apply Mon–Fri; on weekends every type has target 0:00 and uses no PTO.

| Type               | Description                                              | Target | PTO |
|--------------------|----------------------------------------------------------|--------|-----|
| `work`             | Regular work day (default)                               | 8:00   | 0   |
| `pto`              | Paid time off, full day                                  | 0:00   | 1   |
| `pto_half`         | Paid time off, half day                                  | 4:00   | 0.5 |
| `sick`             | Off sick, full day                                       | 0:00   | 0   |
| `sick_half`        | Off sick, half day                                       | 4:00   | 0   |
| `overtime_off`     | Day off taken from the overtime balance                  | 8:00   | 0   |
| `unpaid_leave`     | Unpaid day off                                           | 0:00   | 0   |
| `public_holiday`   | Berlin public holiday (automatic)                        | 0:00   | 0   |
| `company_half_day` | Heiligabend / Silvester: half PTO, half free (automatic) | 0:00   | 0.5 |

## Domain models (`src/models`)

Pydantic models; times in minutes, validated on creation and assignment.

| Module     | Models                                                                                                                                         |
|------------|------------------------------------------------------------------------------------------------------------------------------------------------|
| `days`     | `Day`: date, day type (empty = automatic), start / end, break (empty = legal minimum), note; provides worked time                              |
| `entries`  | `TicketEntry` (ticket, duration, description, coding) and `ActivityEntry` (activity type, duration, note); durations in quarter hours          |
| `catalog`  | `Service`, `ActivityType` and `Ticket` (key like `ENGINE-461`, remembers its service)                                                          |
| `history`  | `EntryChange`: one line of an entry's history (created, imported, updated, renamed, merged, split, deleted) with the changed fields, old → new |
| `review`   | `ReviewFlag`: import flag on an entry or a day (uncertain ticket, weekend hours)                                                               |
| `pto`      | `PtoYear`: allowance, extra days, fixed carry-over (empty = remainder of the year before), note                                                |
| `settings` | `Settings`: balance start date, opening balance                                                                                                |

## Storage (`src/modules/storage`)

SQLite, one connection per transaction (commit on success, rollback on error), foreign keys enforced.
Repositories work within the transaction of the connection they are given.

| Module       | Contents                                                                                                                                                                                                                                                        |
|--------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `database`   | `Database(path)`: transactions and schema migration (`migrate()`, tracked in `PRAGMA user_version`)                                                                                                                                                             |
| `migrations` | Schema scripts, applied once in order; the first one seeds settings, services and activity types, the second the PTO allowances 2024–2027, the third moves them into `pto_years`. Entries keep a change history that outlives them (entry ids are never reused) |
| `settings`   | Load and save user settings                                                                                                                                                                                                                                     |
| `pto_years`  | `PtoYearRepository`: list, get and save (insert or replace) the PTO days of a year; terms for the PTO accounts                                                                                                                                                  |
| `days`       | `DayRepository`: get, list, save (insert or replace) and delete days; records for balances; review flags on days                                                                                                                                                |
| `catalog`    | `ServiceRepository`, `ActivityTypeRepository`: list, get, add, update, delete (deleting a service unassigns its tickets; an activity type in use cannot be deleted)                                                                                             |
| `tickets`    | `TicketRepository`: get, list (sorted by prefix and number), create on first use; set a service on one or several tickets; tickets without service                                                                                                              |
| `entries`    | `EntryRepository`: get, list, create, update and delete entries, each change written to the entry's history (kept after deletion); review flags on entries                                                                                                      |
| `renames`    | `rename_ticket`: move all entries to a new key (history line per entry); renaming to an existing ticket merges both, the existing ticket keeps its service                                                                                                      |
| `errors`     | `NotFoundError` for records that do not exist, `ConflictError` for duplicates and records still in use                                                                                                                                                          |

### Database schema

Solid lines are foreign keys; dotted lines are links without one (by date, or kept after deletion).
Times and durations are minutes, dates ISO text.

```mermaid
erDiagram
    services |o--o{ tickets: "service of"
    tickets |o--o{ entries: "ticket of"
    activity_types |o--o{ entries: "type of"
    entries |o--o{ review_flags: "flagged"
    days |o..o{ review_flags: "flagged (by date)"
    days |o..o{ entries: "on (by date)"
    entries |o..o{ entry_history: "history (kept after deletion)"

    settings {
        TEXT key PK "balance_start, opening_balance"
        TEXT value
    }
    pto_years {
        INTEGER year PK
        TEXT allowance "e.g. 17.5"
        TEXT extra_days "days granted on top"
        TEXT carried_over "NULL = remainder of the year before"
        TEXT note
    }
    services {
        INTEGER id PK
        TEXT short_name UK "case-insensitive"
        TEXT name
    }
    activity_types {
        INTEGER id PK
        TEXT name UK "case-insensitive"
    }
    tickets {
        TEXT key PK "e.g. ENGINE-461"
        INTEGER service_id FK "nullable"
    }
    days {
        TEXT date PK
        TEXT day_type "nullable: automatic"
        INTEGER start_time "nullable"
        INTEGER end_time "nullable"
        INTEGER break_minutes "nullable: legal minimum"
        TEXT note
    }
    entries {
        INTEGER id PK "never reused"
        TEXT date
        TEXT kind "ticket or activity"
        TEXT ticket_key FK "ticket entries"
        INTEGER activity_type_id FK "activity entries"
        INTEGER duration
        TEXT text "description or note"
        INTEGER coding "0 or 1"
    }
    entry_history {
        INTEGER id PK
        INTEGER entry_id
        TEXT changed_at
        TEXT action "created, imported, updated, renamed, merged, split, deleted"
        TEXT changes "JSON: field to old and new"
        TEXT detail
    }
    review_flags {
        INTEGER id PK
        INTEGER entry_id FK "entry flag"
        TEXT date "day flag"
        TEXT reason "uncertain_ticket, weekend_hours"
        TEXT detail
    }
```

## Import (`src/modules/importer`)

Imports the yearly spreadsheet exports (CSV with `Date`, `Start`, `End`, `Pause`, `Sum`, `Comment`).

| Module        | Contents                                                                                                                                                                                                |
|---------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `sheet`       | Read a CSV into one `SheetRow` per day: date (weekday checked), times, pause, sum and comment lines; detects empty future days and placeholder times (08:00–16:00 without break)                        |
| `lines`       | Split leading decimal-comma hours off a comment line (`1,5 KP-2035 refinement` → 1:30)                                                                                                                  |
| `days`        | Day type (PTO, sick, half days, overtime off; holidays automatic), times (placeholders dropped, half days end 4:00 earlier, weekends `Sum` − 8:00), notes for overtime used, weekend flags              |
| `tickets`     | Ticket keys (KP, TNG, ENGINE, AGA, MSI) and their clean-up: typos corrected (`EINGINE-`, `TNG4840`, `MSI-02`, `#KP-1494`); guessed keys flagged (`#4138` → `TNG-4138`, `#4347 aka #1482`, `TNG-2035ff`) |
| `comments`    | Comment lines → entries: tickets anywhere in a line (several tickets split evenly), PR reviews without ticket, Meeting, Tool Management, Travel, Other; lines without hours or ticket become day notes  |
| `corrections` | Known corrections the sheet cannot express: 2024 unpaid leave days (marked "PTO")                                                                                                                       |
| `run`         | Import one year in a single transaction: days, entries (history line with the original comment line), review flags; refuses years with data unless replacing; summary                                   |
| `reconcile`   | Compare an imported year with the sheet (`Sum` − 8:00 per day, up to today): differing days, overtime balance, PTO account                                                                              |
| `__main__`    | Command line: `python -m src.modules.importer SHEET.csv [--replace] [--db PATH]`                                                                                                                        |
