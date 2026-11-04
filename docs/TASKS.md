# Work Tracker — Tasks

Implementation steps for [SPEC.md](SPEC.md). Each task is small enough to review and commit on its own,
and ends with passing tests and the flake8 check. Sections 6–9 were first collected under "Later" as `L.…`, the
numbers older commits use: L.1a–c → 6.1a–c, L.2–L.5 → 6.2–6.5, L.7 → 6.6, L.9 → 6.7, L.12 → 6.8, L.14 → 6.9,
L.15 → 6.10; L.8 → 7.1, L.8a (.1–.3) → 7.2 (a–c), L.8b → 7.3, L.10 → 7.4; L.11 (a–n) → 8.1 (a–n), L.13 → 8.2;
L.16 (a–i) → 9.1 (a–i).

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

## 6. Settings, setup and UI

- [x] **6.1a** Settings page `/settings`, data only (no change to the calculations): overtime balance start date and
  opening balance (h:mm, signed) via `GET/PUT /api/settings`; PTO years (allowance, extra days, fixed carry-over,
  note) as an editable table on the existing `/api/pto-years`; services and activity types moved here from `/lists`
  (which forwards to `/settings#services`)
- [x] **6.1b** Work schedules valid from a date (a change counts from that day on, never rewrites the past): hours per
  week and work days (e.g. Mon–Fri), split evenly into the daily target (40 h / 5 days = 8:00; half days: half of
  it); replaces the fixed 8:00 in `src/lib/daytypes.py`; API `/api/work-schedules` (GET, POST, PUT, DELETE) and a
  section on the settings page; the first schedule is 40 h Mon–Fri from the balance start. The importer keeps the
  spreadsheet's own 8:00 rule
- [x] **6.1c** Holidays in the work schedule: federal state (`holidays` subdivision, e.g. `BE`) and whether 24.12. and
  31.12. are company half days (0.5 PTO each); replaces the fixed Berlin calendar in `src/lib/public_holidays.py`
- [x] **6.2** Days off as a range: "Book days off" button on the week page opens a form (from, to, full-day type: PTO,
  sick, unpaid leave or overtime off; optional note). Only the work days of the schedule get the type; weekends, days off
  of the schedule, public holidays and company half days stay automatic. A preview shows the days and the PTO used before
  saving; future days are allowed (planned PTO). If days in the range hold times or entries, a popup lists them: skip
  these days, book them too (times and entries are kept), or cancel. Saved in one transaction via
  `POST /api/days/range`; afterwards the week of the first day is shown. Clearing a range is not part of it (single
  days can be deleted)
- [x] **6.3** Initial setup: a new database starts clean (a migration marks a database holding days or entries as set
  up and leaves it unchanged; an empty one loses the original setup's PTO years and services and is marked not set
  up). Until set up, every page forwards to `/setup` (the API stays reachable), a guided page in five steps with
  defaults: 1. start day (today) and opening balance (0:00); 2. work schedule (40 h, Mon–Fri, Berlin, company half
  days); 3. PTO days per year (30) and for the first year, with a proposed pro-rata number (the start month counts if
  starting by the 15th, rounded up to half days) that can be changed; 4. services (optional); 5. summary and "Start",
  saving everything at once and opening the week view. A side note points to the spreadsheet import instead. The
  README's "start from zero" shrinks to starting on a new database file
- [x] **6.4** Dark mode: a second set of the color variables (WCAG AA contrast, checked by a test), previewed on
  the component gallery; the theme (System, Light, Dark) is chosen on the settings page and stored in the database
  (`GET/PUT /api/theme`); pages are rendered with the theme, so nothing flashes
- [x] **6.5** Accessibility, WCAG 2.2 AA (found with axe-core on all pages, both themes): light accent `#2C69CB` and
  mint `#1A7B5E` (all text pairs at least 4.5:1, the contrast test checks light mode fully too); entry actions always
  visible in muted text instead of dimmed; links in body text underlined; error messages connected to their field
  (`aria-describedby`); visible labels for the "add" forms of the settings tables; Escape closes inline forms and the
  booking form, and focus returns to the button that opened them; a "Skip to content" link first on each page; the
  gallery's code blocks focusable. No separate axe script and no screen-reader checklist
- [x] **6.6** Dashboard as the start page `/` (until the database is set up, `/setup` as before); the week view moves to
  `/week`, and old links like `/?week=2026-W44&edit=…` forward there with their parameters. Content: key figures
  (balance today and this year's change, PTO left and planned, this week worked of target, open review items; each
  links to its page), a chart of the overtime balance with a switch (current month by day; year, last 12 months and
  all since the balance start by month; below zero in the warning color; plain SVG, both themes), coming up in the
  next 60 days (public holidays, company half days and planned days off, days in a row combined), and this year's
  figures (days worked and average, sick days, overtime-off days, coding hours, top services). Data from
  `GET /api/dashboard` in one transaction
- [ ] **6.7** Narrow screens and zoom (WCAG 1.4.10 Reflow, 320 CSS px / 200 % zoom): wide tables scroll in their own
  container, the navigation wraps, form grids fall back to one column
- [x] **6.8** Duration formats: every duration field (entry duration, break, hours per week, opening balance with a
  minus) accepts `1:30`, `1.5`, `1,5`, `1h30m`, `1h30`, `1h`, `1 h 30 min`, `90m`, `90min` (spaces and case do not
  matter); the field shows the normalized `h:mm` when left, and the API reads the same formats
  - Limits: an entry at most the rest of its day (from 08:00 at most 16:00; without a start time 24:00), a break at
    most the day from start to end, hours per week at most 168:00. Explicit units over the limit are an error naming it
  - A bare number (`2`, `90`) is hours if that fits the limit; otherwise a popup asks "Did you mean 90 minutes
    (1:30)?" (use it or cancel)
  - Entries stay in quarter hours: `1.1` (1:06) opens a popup with "1:00", "1:15" or cancel; breaks and hours per
    week need no quarter hours. The API refuses non-quarter-hour entries and durations over the limit
- [x] **6.9** Log out during the setup: a new user (e.g. after registering) sees their name and "Log out" on `/setup`
  as well; after the next login, every page forwards to the setup again until it is done
- [x] **6.10** Company half days made visible: 24.12. and 31.12. take 0.5 PTO by themselves (half PTO, half free), and
  the UI now says so: in the week ("Company half day · 0.5 PTO (half free)"), under "Coming up" on the dashboard
  ("company half day: 0.5 PTO") and in the preview of "Book days off" ("… is a company half day: 0.5 PTO, booked
  automatically"); the API gives the PTO of left-out days and coming-up items (`pto_days`)

## 7. Users and teams

- [x] **7.1** Login: a user has a username and an e-mail address (both unique, ignoring case), a first name, an optional
  last name and a password (at least 12 characters, stored as a salted scrypt hash). Login with username or e-mail
  address; the session is a random token in an `HttpOnly`, `SameSite=Strict` cookie (`Secure` over HTTPS), stored hashed
  in a table, valid for 24 h since the last activity (each request extends it to 24 h from now; the stored expiry is
  renewed at most every 30 minutes); log out ends it, a password change ends all sessions; after 5 wrong attempts logins
  pause for a minute. Pages forward to `/login?next=…`, the API answers 401; `/login`, static files, `/health` and the
  API docs stay open. The first user is created in the setup (new databases) or once on the next visit (existing ones);
  the settings page changes the profile and password; a command resets a forgotten password. `WORK_TRACKER_AUTH=off`
  switches the login off for local development
- [x] **7.2** Multi-user app, run locally (a later AWS Lambda deployment stays possible; it is a task of its own):
  several users with their own time tracking in one database, data per user. Ownership: days, entries, history, review
  flags, settings (balance start, opening balance, theme), work schedules, PTO years, tickets with their service and
  activity types belong to a user; services belong to a user (personal) or to a team (shared with its members);
  users, teams and memberships are app-wide. Nobody sees someone else's days and entries, the admin neither (technical
  support works on the database directly; team admins get a read-only view in 7.4). Roles: admin, team admin, user. In
  three steps:
  - [x] **7.2a** Data per user: `user_id` (a random UUID) on every personal table; a migration gives all existing
    records to the only user and makes that user admin (a database with data but no user: the first user created takes
    over everything without an owner). Repositories, reports, review, dashboard, setup and the importer work per user
    (`--user` for the importer); a new user starts with the four default activity types and goes through the setup for
    their own data
  - [x] **7.2b** Registration and roles:
    - `/register` with the fields of the login: the new user is logged in at once and goes through the setup (no
      e-mail confirmation). Registrations share the pause of the failed logins (5 per minute). The login page links to
      it only while registration is on; otherwise `/register` answers 404, and it does not exist with the login off
    - Admin page `/admin` (an "Admin" link in the navigation for admins only; the admin API answers 403 to others):
      registration on or off (off by default), and the users with username, name, e-mail address, role, active,
      registered on and last login (new columns), but nothing of their time data
    - Change the role (admin or user; team admin comes with 7.2c), deactivate and reactivate: a deactivated user
      cannot log in, their sessions end at once, their data is kept. Nobody deactivates or demotes themselves, so an
      active admin always remains. Users are not deleted
    - Forgotten passwords stay with the command on the computer running the app
  - [x] **7.2c** Teams:
    - A user is a member of at most one team. Memberships are kept as history (team, joined on, left on), so it stays
      known which team a user was in on each day (e.g. for 7.4)
    - Admin page: a Teams section to create, rename and delete teams (only without members; open invitations are
      dropped), and to name team admins. A team admin is a role on the user and admin of their own team only; leaving
      or being removed from it makes them a user again
    - Invitations: the admin, and a team admin for their team, invite a user by their exact e-mail address (ignoring
      case); the answer is the same whether such a user exists or not. Only the admin sees the list of users and teams;
      users never see which teams exist. The inviter can withdraw an open invitation
    - The invited user accepts or declines in the settings; the Settings link shows a badge while an invitation is
      open. Several invitations may be open; accepting one declines the others. A user in a team can be invited to
      another; accepting means leaving the old team
    - Team page `/team` for team admins and the admin (the admin opens it for any team from the admin page): members
      (names and e-mail addresses, none of their time data) with "Remove", open invitations, and the team's services
    - Services: team services are added, changed and deleted only by the admin and the team's admins; members choose
      them in entries, grouped as "Team <name>" and "Personal" (the same short name may be in both). Personal services
      stay with the user, and they can still add their own
    - Leaving: a member leaves in the settings or is removed by the admin or a team admin. The team services their
      tickets use are copied into their personal services (a personal service with the same short name is used
      instead of a copy), so their tickets keep their service
- [x] **7.3** Password rules: a new password (registration, first user, password change, `set-password`) has at least
  12 characters with letters, digits and at least one special character (anything but letters, digits and spaces).
  Existing passwords keep working
- [x] **7.4** Team view for team admins (after 7.2c):
  - On the dashboard, a team admin chooses a current member of their team ("Viewing: Rainer Zufall"); dashboard, week,
    month and year then show that member's data read-only (no editing, no review), e.g. `/month?member=<id>`, with a
    banner "Read-only: Rainer Zufall's data · back to yours" on every page
  - Shown: times, tickets, hours and entry descriptions and notes; day notes (e.g. a reason for sick leave) stay hidden.
    Days outside the member's time in this team show as "not in this team", without times or entries. Running figures
    (overtime balance, PTO left) are as of now, with a note that they cover the whole time
  - Only the team admins of the member's current team, the admin neither (unless team admin of that team); former
    members drop out of the view
  - Members see in their settings that their team admins can see their reports, and a log of who looked at which
    report and when

## 8. AWS Lambda deployment

- [x] **8.1** AWS Lambda deployment with DynamoDB (SPEC 7.1–7.4), in steps:
  - [x] **8.1a** Python 3.14: Pipfile, lock file, README, Dockerfile; tests and flake8 pass on 3.14
  - [x] **8.1b** Storage interfaces: repository protocols and a backend-neutral transaction; resources and reports
    no longer touch `sqlite3`, which stays inside the SQLite backend (and the SQLite-only importer). A refactoring
    only, tests unchanged
  - [x] **8.1c** Stages: `.env.example` with `STAGE=Local`, Lambda detection, the startup errors of 7.1
  - [x] **8.1d** Export of the own data as JSON, download on the settings page (SPEC 5.8)
  - [x] **8.1e** Import of an export file in the setup, for a user without days and entries; removed again on failure;
    round-trip test (SPEC 5.8)
  - [x] **8.1f** DynamoDB base: `boto3`, `moto` for the tests, table command (keys, on-demand, time to live,
    point-in-time recovery), schema version item, transactions up to 100 items and resumable atomic chunks beyond;
    contract tests run on both backends
  - [x] **8.1g** DynamoDB repositories: users, sessions, failed logins, user settings (the app settings came with
    8.1f); their tests are contract tests now, on both backends
  - [x] **8.1h** DynamoDB repositories: days, entries with history, review flags; their tests are contract tests now
  - [x] **8.1i** DynamoDB repositories: tickets, personal services, activity types, rename and merge tickets (in
    resumable chunks); their tests are contract tests now
  - [x] **8.1j** DynamoDB repositories: work schedules, PTO years, teams, memberships, invitations, report views;
    team services and the team's service choices (deleting one unassigns the members' tickets); contract tests
  - [x] **8.1i2** UUIDv7 ids for records (SPEC 7.2a), before the DynamoDB table is in use; one task, since the
    app only works with ids changed everywhere at once:
    - Models and storage interfaces: ids are UUID strings; new ids from `uuid.uuid7()`
    - SQLite: a migration to UUIDv7 ids in the order of the old ones, with all references (also in history lines)
    - DynamoDB: no counters; sort keys with the ids
    - API paths and schemas with string ids, OpenAPI file and TypeScript types; frontend code and tests
    - Export and import: file ids stay 1, 2, …; the import gives new ids
  - [x] **8.1j2** Import on DynamoDB: an export file holds thousands of items, far more than one transaction's 100,
    so the import writes atomic chunks; references are checked before anything is written, and an import that
    stopped halfway is replaced by the next one (SPEC 5.8)
  - [x] **8.1k** Access tests on both backends: another user's id answers 404 for every repository and API resource
    (7.3)
  - [x] **8.1l** One-time password: the admin sets it for a user who forgot theirs (changed at the next login)
  - [x] **8.1m** Setup token on Lambda: the first user only with the token from the SSM parameter (SPEC 7.4; `moto`
    in the tests)
  - [x] **8.1n** zappa: the Lambda stage uses the DynamoDB table (`stages.py`, after the setup token of 8.1m);
    `zappa_settings.json` (`eu-central-1`, `python3.14`, `TZ`, table, parameter name), WSGI module, package
    excludes, IAM policy for the one table and the one parameter, README deployment steps (including creating and
    deleting the parameter)
- [x] **8.2** Validation errors are logged with their locations and error types only (e.g.
  `data.history.3.changed_at (datetime_parsing)`), never with the input or the message: a refused import or export
  would otherwise put a user's whole data into the log (on Lambda: CloudWatch); the answer still names the problem

## 9. Roles for running the app

- [x] **9.1** Roles for running the app (SPEC 5.6, 5.7, 5.9, 7.4), in steps:
  - [x] **9.1a** Team role on the membership: member or team admin, for admins and users alike (migration: a
    `team_admin` becomes a user and team admin of their team); the team view checks the membership
  - [x] **9.1b** Root: the app role `root` (exactly one, not demoted or deactivated); the setup of a new database
    creates root (with the setup token on Lambda) and no tracking data; root's pages are `/admin`, its profile and
    password (the tracking API answers 403); "Create root admin" once on `/login` of a database with users but no
    root; the first user who is not root takes over the records of a database used without users
  - [x] **9.1c** Permissions: root switches registration, appoints and removes admins and helps admins (one-time
    password, deactivate, reactivate); admins manage users, team admins and teams, no longer admins
  - [x] **9.1d** Audit log: role, team admin, auditor and team changes, (de)activations, one-time passwords,
    two-factor resets, registration, backups and restores; all on `/admin` for root and admins, the own entries in the
    settings
  - [x] **9.1e** Auditors: an admin assigns users or admins (not themselves) to teams, optionally until an end date;
    the team view read-only for everyone who was in the team, for the days of each stay; shown to members with the
    team admins, views in the view log
  - [x] **9.1f** Setup token once only (hashes of used tokens); "Reset root login" on `/login` with a new token
  - [x] **9.1g** Two-factor login (TOTP), in steps:
    - [x] **9.1g1** TOTP core: setting it up in the settings (QR code with `segno`, the secret as text, a first code
      confirms it), the code at login, each code only once, switching it off with the password; optional for everyone
    - [x] **9.1g2** Required for root and admins (forwarded to `/2fa` until set up), 10 recovery codes, resets (an
      admin for users, root for admins, root's own with the setup token), audit log entries
    - [x] **9.1g3** "Remember this browser" for 30 days (not root); root's session ends after 1 hour without activity
    - [x] **9.1g4** A new authenticator app (e.g. a new phone): in the settings, with the password and a current code (or
      a recovery code), a new secret replaces the old one once a code of the new app confirms it; also for root and
      admins, who cannot switch two-factor login off
  - [x] **9.1h** Full backup on `/admin`: the whole database, gzip and AES-256-GCM with root's passphrase (scrypt;
    `cryptography`)
  - [x] **9.1i** Restore on `/admin`: at once when nobody but root exists, otherwise after confirming the purge;
    root stays; checked before writing; DynamoDB in resumable chunks, only root uses the app until it is done

## 10. Lean tests

- [x] **10.1** Trim the tests to our own behaviour and contracts (README, "Tests and code quality"), in steps:
  - [x] **10.1a** `lib`, `models`, `utils`, `test_app`: no tests of `holidays`, `uuid`, pydantic or spectree, fewer
    parametrized cases (one per rule and boundary), no generated grid
  - [x] **10.1b** Storage: merge contract tests with the same setup and action, the interface check and the access
    matrix in one test per backend (actual statuses against an explicit table)
  - [x] **10.1c** Auth, admin, backup: representative paths and names in place of lists of them
  - [x] **10.1d** The other modules: no `*_is_documented` tests (the OpenAPI file test covers them), the isolation
    matrix in one test per backend, merged checks
  - [x] **10.1e** Frontend tests (`src/templates/tests`)
- [x] **10.2** One place for each rule, in steps:
  - [x] **10.2a** Storage: the rules of entries (create, update, split, history) shared by both backends, as the rename
    rules already are (the one-liners for days, PTO years and schedules stay: sharing them would take as many lines)
  - [x] **10.2b** Review: the API suggests how to split a guessed ticket (the import's ticket rules), the frontend no
    longer maps old numbers to keys itself
  - [x] **10.2c** Frontend: one `errorText`, one `button`, `formatDate` from `dates.ts`, the setup's fields from `forms.ts`
- [ ] **10.3** One place for each rule, second round, in steps:
  - [x] **10.3a** Tests: one login helper (`login`, `session`, `logged_in`), one `Clock`, one `run` for the storage
    contract tests, in place of their copies
  - [ ] **10.3b** Dashboard and reports share their inputs (settings, schedules, what the team view shows from when)
  - [ ] **10.3c** Storage: deleting an entry and its history line in `EntryRules`, as creating and changing already
  - [ ] **10.3d** Frontend: one header for the week, month and year pages

## 11. Running and checking the app

- [x] **11.1** The local server (`python -m src`) answers requests side by side: `wsgiref` serves one at a time and
  drops what waits beyond 5, so a page that loads its ~20 modules at once sometimes stays empty ("Failed to fetch
  dynamically imported module", 3–4 of 10 dashboard loads; gunicorn with threads: 0 of 10). A threaded server with a
  longer queue
- [x] **11.2** A readable message for an invalid ticket key, e.g. when renaming a ticket: today pydantic's "String should
  match pattern '^[A-Z][A-Z0-9]*-[1-9]\d*$'"; instead e.g. "A ticket key is letters, a dash and a number, e.g. TNG-4138"
- [x] **11.3** End-to-end tests in the browser, with Playwright (`pytest-playwright`, the installed Chrome, headless)
  rather than Cypress: they run in pytest with the fixtures and personas of the API tests, a browser context per user
  (team admin, root and admin with 2FA), native `confirm()` handled, and axe-core for the WCAG checks of 6.5. A few
  flows, not every page: login with 2FA, setup, week (record a day, add and change an entry), review (split, rename),
  settings (a table row, delete), admin (one-time password dialog), team view; marked `e2e` so the quick suite stays
  quick. The run skill's driver stays for screenshots and before/after comparisons

## Later (to be discussed)

- [ ] **L.6** Overtime used in hours: record hours taken from the overtime balance on a work day (e.g.
  `2,0 PTO Dentist`, today only a day note) as a value, and show them in the year report next to the days off.
  On hold: kept as day notes for now, to see how hours off are used in practice
