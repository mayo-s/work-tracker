# Work Tracker — Tasks

Implementation steps for [SPEC.md](SPEC.md). Each task is small enough to review and commit on its own,
and ends with passing tests and the flake8 check.

## 0. Tooling

- [x] **0.1** pytest config (`src/tests`), flake8 config: no type annotations required in tests

## 1. Calculation rules (`src/lib`)

- [x] **1.1** Time helpers: parse / format `HH:MM` and `h:mm`, decimal-comma hours, quarter-hour check, even split
- [x] **1.2** Legal break default and worked time
- [x] **1.3** Add `holidays` package; Berlin holiday calendar plus Heiligabend / Silvester
- [x] **1.4** Day types: target, PTO used, overtime per day
- [x] **1.5** Overtime balance (from 01.06.2024, future days excluded) and PTO per year with carry-over

## 2. Storage

- [x] **2.1** Domain models: day, ticket entry, activity entry, ticket, service, activity type, review flag
- [x] **2.2** SQLite schema (incl. entry history table) and connection handling, settings, seed data (services, activity
  types)
- [x] **2.3** Days repository, including day flags
- [x] **2.4a** Services and activity types repositories
- [x] **2.4b** Tickets repository: service per ticket, assign a service to several tickets
- [x] **2.4c** Entries repository with history (4.5) and entry flags
- [x] **2.4d** Rename and merge tickets (history lines; the existing ticket keeps its service)

## 3. Import

- [x] **3.1** CSV reader: row parsing, placeholder detection
- [x] **3.2** Day classification: day types, half days, overtime notes, weekend flags
- [x] **3.3** Comment-line parser: tickets, splitting, Meeting / TM / Travel / Other / PR review
- [x] **3.4** Ticket clean-up rules and flags
- [x] **3.5** Import command with `--replace`, known corrections and summary
- [x] **3.6** Reconciliation report; real run on the 3 CSVs (expect 13:15 → 6:30 → 13:45, 0.5 PTO days carried into
    2025)

## 4. REST API

- [x] **4.1** Falcon and spectree setup: `src/utils/spec.py`, `src/app.py`, dev server; `default.py` at `/` (plain text)
- [x] **4.2** Days: range / week, update, delete
- [x] **4.3** Entries CRUD, with service pre-fill from the ticket
- [x] **4.4** Tickets, services and activity types, including assigning a service to several tickets at once
- [x] **4.5** Review list and clearing flags
- [x] **4.6** Reports: week summary, month, year

## 5. Frontend (`src/templates`, TypeScript)

- [x] **5.1a** Node 26.13.0 via fnm (`.node-version`), TypeScript setup (`npm run build` / `watch`); compiled JS is
  built locally and git-ignored
- [x] **5.1b** Static serving and page frame at `/`; move the default resource to `/health`
- [x] **5.1c** Base layout and styles: UI style from SPEC 5.5 as CSS variables, Inter font stored in the project
- [x] **5.1d** Typed API client
- [x] **5.1e** Component gallery at `/components` (replaces the style preview): every UI element with its use and HTML
- [x] **5.2** Week view, read-only
- [x] **5.3** Week view: edit days (type, times, default break, note)
- [x] **5.4** Week view: add, edit and delete entries
- [x] **5.5** Review page
- [x] **5.6** Month report
- [x] **5.7** Year report
- [x] **5.7b** PTO years as data, not code: table `pto_years` (year, allowance, extra days, carried over, note) in
  migration 3, taking over the current values; carry-over is calculated unless a fixed value is entered (later years
  build on it); a year without a row has no PTO account (no "valid from that year on"); API `GET /api/pto-years`,
  `PUT /api/pto-years/{year}`; migration 2 stays as it is
- [x] **5.8** Page for managing services and activity types

## Later (to be discussed)

- [ ] **L.1a** Settings page `/settings`, data only (no change to the calculations): overtime balance start date and
  opening balance (h:mm, signed) via `GET/PUT /api/settings`; PTO years (allowance, extra days, fixed carry-over,
  note) as an editable table on the existing `/api/pto-years`; services and activity types moved here from `/lists`
  (which forwards to `/settings#services`)
- [ ] **L.1b** Work schedules valid from a date (a change counts from that day on, never rewrites the past): hours per
  week and work days (e.g. Mon–Fri), split evenly into the daily target (40 h / 5 days = 8:00; half days: half of
  it); replaces the fixed 8:00 in `src/lib/daytypes.py`; API `/api/work-schedules` (GET, POST, PUT, DELETE) and a
  section on the settings page; the first schedule is 40 h Mon–Fri from the balance start. The importer keeps the
  spreadsheet's own 8:00 rule
- [ ] **L.1c** Holidays in the work schedule: federal state (`holidays` subdivision, e.g. `BE`) and whether 24.12. and
  31.12. are company half days (0.5 PTO each); replaces the fixed Berlin calendar in `src/lib/public_holidays.py`
- [ ] **L.2** Vacation day range: Instead of booking every vacation day one after another, there should be an option to
  enter a time range vor vacations. Same for sick days in case one is sick for more than just a few days.
- [ ] **L.3** Initial setup: the "start from zero" section explains how to start from scratch, but many steps should be
  part of an initial start-setup page. Guiding the user through the process, when there is no database yet.
- [ ] **L.4** Dark mode: a second set of the color variables from the UI style (e.g. following the system setting)
- [ ] **L.5** Accessibility: the ui should be accessible for everyone and follow modern accessibility standards
- [ ] **L.6** Overtime used in hours: record hours taken from the overtime balance on a work day (e.g.
  `2,0 PTO Dentist`,
  today only a day note) as a value, and show them in the year report next to the days off.
- [ ] **L.6** Dashboard: A dashboard page with a clean overview and summary of vacation days, overtime balance and other
  interesting stats.
