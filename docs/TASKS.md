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
    - [x] **6.1c** Holidays in the work schedule: federal state (`holidays` subdivision, e.g. `BE`) and whether 24.12.
      and
      31.12. are company half days (0.5 PTO each); replaces the fixed Berlin calendar in `src/lib/public_holidays.py`
- [x] **6.2** Days off as a range: "Book days off" button on the week page opens a form (from, to, full-day type: PTO,
  sick, unpaid leave or overtime off; optional note). Only the work days of the schedule get the type; weekends, days
  off
  of the schedule, public holidays and company half days stay automatic. A preview shows the days and the PTO used
  before
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
- [x] **6.7** Narrow screens and zoom (WCAG 1.4.10 Reflow, 320 CSS px / 400 % zoom): wide tables scroll in their own
  area (focusable while it scrolls), the navigation and button rows wrap, form grids fall back to one column, the
  week's entries and forms stay on screen; checked by the end-to-end tests (no page wider than 320 px, axe at that
  width)
- [x] **6.8** Duration formats: every duration field (entry duration, break, hours per week, opening balance with a
  minus) accepts `1:30`, `1.5`, `1,5`, `1h30m`, `1h30`, `1h`, `1 h 30 min`, `90m`, `90min` (spaces and case do not
  matter); the field shows the normalized `h:mm` when left, and the API reads the same formats
    - Limits: an entry at most the rest of its day (from 08:00 at most 16:00; without a start time 24:00), a break at
      most the day from start to end, hours per week at most 168:00. Explicit units over the limit are an error naming
      it
    - A bare number (`2`, `90`) is hours if that fits the limit; otherwise a popup asks "Did you mean 90 minutes (1:
      30)?" (use it or cancel)
    - Entries stay in quarter hours: `1.1` (1:06) opens a popup with "1:00", "1:15" or cancel; breaks and hours per
      week need no quarter hours. The API refuses non-quarter-hour entries and durations over the limit
- [x] **6.9** Log out during the setup: a new user (e.g. after registering) sees their name and "Log out" on `/setup`
  as well; after the next login, every page forwards to the setup again until it is done
- [x] **6.10** Company half days made visible: 24.12. and 31.12. take 0.5 PTO by themselves (half PTO, half free), and
  the UI now says so: in the week ("Company half day · 0.5 PTO (half free)"), under "Coming up" on the dashboard (
  "company half day: 0.5 PTO") and in the preview of "Book days off" ("… is a company half day: 0.5 PTO, booked
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
          e-mail confirmation). Registrations share the pause of the failed logins (5 per minute). The login page links
          to
          it only while registration is on; otherwise `/register` answers 404, and it does not exist with the login off
        - Admin page `/admin` (an "Admin" link in the navigation for admins only; the admin API answers 403 to others):
          registration on or off (off by default), and the users with username, name, e-mail address, role, active,
          registered on and last login (new columns), but nothing of their time data
        - Change the role (admin or user; team admin comes with 7.2c), deactivate and reactivate: a deactivated user
          cannot log in, their sessions end at once, their data is kept. Nobody deactivates or demotes themselves, so an
          active admin always remains. Users are not deleted
        - Forgotten passwords stay with the command on the computer running the app
    - [x] **7.2c** Teams:
        - A user is a member of at most one team. Memberships are kept as history (team, joined on, left on), so it
          stays
          known which team a user was in on each day (e.g. for 7.4)
        - Admin page: a Teams section to create, rename and delete teams (only without members; open invitations are
          dropped), and to name team admins. A team admin is a role on the user and admin of their own team only;
          leaving
          or being removed from it makes them a user again
        - Invitations: the admin, and a team admin for their team, invite a user by their exact e-mail address (ignoring
          case); the answer is the same whether such a user exists or not. Only the admin sees the list of users and
          teams;
          users never see which teams exist. The inviter can withdraw an open invitation
        - The invited user accepts or declines in the settings; the Settings link shows a badge while an invitation is
          open. Several invitations may be open; accepting one declines the others. A user in a team can be invited to
          another; accepting means leaving the old team
        - Team page `/team` for team admins and the admin (the admin opens it for any team from the admin page): members
          (names and e-mail addresses, none of their time data) with "Remove", open invitations, and the team's services
        - Services: team services are added, changed and deleted only by the admin and the team's admins; members choose
          them in entries, grouped as "Team <name>" and "Personal" (the same short name may be in both). Personal
          services
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
    - Shown: times, tickets, hours and entry descriptions and notes; day notes (e.g. a reason for sick leave) stay
      hidden.
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
          confirms it), the code at login, each code only once, switching it off with the password; optional for
          everyone
        - [x] **9.1g2** Required for root and admins (forwarded to `/2fa` until set up), 10 recovery codes, resets (an
          admin for users, root for admins, root's own with the setup token), audit log entries
        - [x] **9.1g3** "Remember this browser" for 30 days (not root); root's session ends after 1 hour without
          activity
        - [x] **9.1g4** A new authenticator app (e.g. a new phone): in the settings, with the password and a current
          code (or
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
    - [x] **10.2a** Storage: the rules of entries (create, update, split, history) shared by both backends, as the
      rename
      rules already are (the one-liners for days, PTO years and schedules stay: sharing them would take as many lines)
    - [x] **10.2b** Review: the API suggests how to split a guessed ticket (the import's ticket rules), the frontend no
      longer maps old numbers to keys itself
    - [x] **10.2c** Frontend: one `errorText`, one `button`, `formatDate` from `dates.ts`, the setup's fields from
      `forms.ts`
- [x] **10.3** One place for each rule, second round, in steps:
    - [x] **10.3a** Tests: one login helper (`login`, `session`, `logged_in`), one `Clock`, one `run` for the storage
      contract tests, in place of their copies
    - [x] **10.3b** Dashboard and reports share their inputs (settings, schedules, what the team view shows from when)
    - [x] **10.3c** Storage: deleting an entry and its history line in `EntryRules`, as creating and changing already
    - [x] **10.3d** Frontend: one header for the week, month and year pages
- [x] **10.4** One place for each rule, third round, in steps:
    - [x] **10.4a** The service of an entry (its ticket's) looked up in one place for the entry views and the coding
      work
    - [x] **10.4b** Tests: one fixture for Hans and root Pascal (two-factor login, audit log)
    - [x] **10.4c** Tests: one fixture for the backup of a database with root and a fresh database with another root

## 11. Running and checking the app

- [x] **11.1** The local server (`python -m src`) answers requests side by side: `wsgiref` serves one at a time and
  drops what waits beyond 5, so a page that loads its ~20 modules at once sometimes stays empty ("Failed to fetch
  dynamically imported module", 3–4 of 10 dashboard loads; gunicorn with threads: 0 of 10). A threaded server with a
  longer queue
- [x] **11.2** A readable message for an invalid ticket key, e.g. when renaming a ticket: today pydantic's "String
  should
  match pattern '^[A-Z][A-Z0-9]*-[1-9]\d*$'"; instead e.g. "A ticket key is letters, a dash and a number, e.g. TNG-4138"
- [x] **11.3** End-to-end tests in the browser, with Playwright (`pytest-playwright`, the installed Chrome, headless)
  rather than Cypress: they run in pytest with the fixtures and personas of the API tests, a browser context per user
  (team admin, root and admin with 2FA), native `confirm()` handled, and axe-core for the WCAG checks of 6.5. A few
  flows, not every page: login with 2FA, setup, week (record a day, add and change an entry), review (split, rename),
  settings (a table row, delete), admin (one-time password dialog), team view; marked `e2e` so the quick suite stays
  quick. The run skill's driver stays for screenshots and before/after comparisons

## 12. Faster pages and more insight

- [x] **12.1** Faster dashboard and reports: `GET /api/review/counts` only counts the open review items (for the
  navigation badge and the dashboard tile; today both build the whole review, 41 DynamoDB queries per page); the year
  report computes its days once with a running balance (today 25 balances from the balance start, ~21,000 day
  summaries per call); the review page finds the entries imported together in one pass instead of a query per entry
- [x] **12.2** The review count in the navigation follows every review action (from the counts of 12.1)
- [x] **12.3** A full restore that takes over the backup's root login needs no two-factor setup before, while the
  database holds nobody but root (the backup's root login comes with its own); everything else still requires it
- [x] **12.4** Review entries with more context: the description (or note) and the original spreadsheet line in the
  row, and "Details" opening a dialog with the whole entry (date and weekday with the day's times, duration, ticket or
  activity, service, coding, description, flags, history, a link to the week); a button, not hover (keyboard, touch)
- [x] **12.5** Week, month and year: a date field with "Go" in the header opens the week, month or year of that date
- [x] **12.6** Month and year report beyond coding: "Other ticket work" (ticket entries not marked coding, by service
  and ticket) and "Activities" (by activity type, in the month with their notes), and the hours in entries next to
  the hours worked by the day times (e.g. "Entries 152:30 of 160:00 worked")
- [x] **12.7** Search: a page to find and sum up entries by text (ticket key or its start, words of description or
  note, service or activity type), activity type, service and period (all time, a preset or custom): total hours and
  entries, by ticket or
  activity type, by month, and the entries with links to their week (the newest 100, "Show all")
- [x] **12.8** A dark mode switch between the name and "Log out" in the navigation: turns dark mode on or off and
  saves it as the theme (Light or Dark; System stays in the settings)

## 13. Other ways of working

- [x] **13.1** The way of working (SPEC 5.11) as a setting: `work_mode` in the settings on both backends (existing
  users get `developer`), `/api/settings`, export and import (a file without it gets `developer`), and a choice on the
  settings page
- [x] **13.2** Setup: the way of working on the start step, the step "Services" only with ticket entries; new users
  get the default activity types Meeting, Travel, Planning, Documentation and Other (no Tool Management; existing
  users keep theirs), and the spreadsheet import adds an activity type the user does not have yet
- [x] **13.3** Week: the entry form per way of working (no Coding checkbox, no Ticket / Activity choice, no "Add
  entry" in "Times only"; an existing entry of another kind keeps its full form), and no warning for a day without
  entries in "Times only"
- [x] **13.4** Month and year report: parts per way of working or data in the period, "Ticket work" without coding,
  no work report in "Times only"; dashboard: "Coding hours" and "Top services" per way of working
- [x] **13.5** Navigation: "Review" only while items are open (with their count) and on the review page itself, for
  every way of working (SPEC 5.4); search: the search page without service and with "Words" when there are no
  ticket entries
- [x] **13.6** Team view: a member's pages in the member's way of working (after 13.9)
- [x] **13.7** One kind of entry (SPEC 4, 4.6): every entry has an activity type, an optional ticket and a
  description; activity types get "Ticket required", Coding is a default for Developer; the migration on both
  backends converts the former entries (coding → Coding, PR review → Coding, refinement → Meeting, the rest without
  activity type) with one shared conversion: SQLite rebuilds `entries`, DynamoDB rewrites the entry items in place in
  chunks, safe to repeat (its first migration, SPEC 7.2); the API, the entry form (activity type first, ticket and
  service per way of working), export version 2 (version 1 converted), the spreadsheet import and "Ticket required"
  in the settings' activity types
- [x] **13.8** Review: choose the activity type of entries without one, also for several at once
- [x] **13.9** Reports, dashboard and search by activity type (SPEC 5.0, 5.2, 5.3, 5.10, 5.11): the work report by
  activity type in place of coding / other ticket work, "Top activity types" in place of "Coding hours"; "Times
  only" with entries optional ("Add entry", the search field, the work report when the period holds entries)

## Later (to be discussed)

- [ ] **L.6** Overtime used in hours: record hours taken from the overtime balance on a work day (e.g.
  `2,0 PTO Dentist`, today only a day note) as a value, and show them in the year report next to the days off.
  On hold: kept as day notes for now, to see how hours off are used in practice
- [x] **L.7** Clean up - remove spreadsheet import functionality (the command and its tests; its ticket clean-up moved
  into the review, which still suggests splits for guessed tickets of imported data)
- [x] **L.8** i18n: switch the UI language between German, English and Spanish (SPEC 5.16), in steps:
    - [x] **L.8a** The mechanism and the frame: the language setting (account, both backends, export and backup;
      cookie and `Accept-Language` before it), `PUT /api/language`, the switch in the header (also before the login),
      the catalogs `static/locales/de.json` and `es.json` with their completeness test, the server rendering the
      frame (header, navigation, menu, footer) and the page titles in the language, `t`/`tn` in the scripts
    - [x] **L.8b** The pages' HTML texts (what the scripts write comes with L.8c); the component gallery stays English, a
      reference for developers, imprint and privacy policy come as a whole with L.8e
    - [x] **L.8c** The scripts' texts and formats, in steps:
        - [x] **L.8c1** The formats (month and weekday names in the page's language) and the shared parts: day types,
          ways of working, dialogs, forms, the API client's messages, the day and entry editors with the duration
          question, an entry's details and history, the audit log as whole sentences
        - [x] **L.8c2** The tracking pages: week, days off, month, year, dashboard, review, search; decimal comma for
          day counts, lists joined in the language (`A und B`), short month names in the year and the chart
        - [x] **L.8c3** Account and setup: login, register, password, two-factor login, setup, settings (with the
          editable tables of services and activity types, their messages as whole sentences); the setup's last button
          is "Start counting", as its first step is "Start"
        - [x] **L.8c4** Team and administration: admin, team, team report, team view, support, contact; a changed role
          as a whole sentence per role (`roleChanged`), lists of teams in the language
    - [x] **L.8d** The server's messages (refusals, errors) and the holiday names: what people meet is marked
      `text('…', key=value)` (`src/lib/texts.py`) and translated where the answer leaves the app (an error's
      description, a refused request's messages, the team report's notes), pieced messages became whole sentences; the
      scripts send the page's language as `Accept-Language`; holiday names, "Deleted user" and "Support" answered in it;
      the completeness test finds every `text(…)` and every holiday name of all federal states for the next ten years
    - [x] **L.8e** Imprint and privacy policy, with a note that the German text is the binding one: the German texts
      stay the originals (`imprint.html`, `privacy.html`), the translations beside them (`privacy.en.html`, …) with a
      link to the German one (`?lang=de`), the scripts' parts in the content's language (`legal.ts`); a test fails
      when a translation's outline or date no longer follows the German text; the German text names the German UI
      labels („Konto löschen“, „Gelöschter Benutzer“); default activity types stay as created, not translated
- [x] **L.9** Exact times, in steps:
    - [x] **L.9a** No more quarter-hour rule: an entry's duration may be any whole minutes, in the form and the API;
      the popup offering the two nearest quarter hours is gone
    - [x] **L.9b** "Start now" and "End now" on today's day in the week view save the current time, to the minute, at
      once. "Start now" shows while no start is set, "End now" while the day is open (a start without an end);
      corrections go through "Edit". An open day counts like a day without times (nothing worked yet) and shows the
      best end time as a placeholder: the time at which the day's target is reached with its break, so no overtime and
      no loss. A past day left open goes to the review with a warning until it has an end
- [x] **L.10** Ways of working: after 13.9, review whether the four are still needed, or two switches (ticket and
  service; entries expected) do the same. Result: three; "Developer" and "Tickets, no coding" became "Tickets and
  activities" (they differed only in Coding at the setup, now a checkbox there)
- [x] **L.11** Team report (SPEC 5.12), in steps:
    - [x] **L.11a** API: `GET /api/teams/{team_id}/report` for a month or a year: the team's totals, hours by activity
      type and by service and ticket, and each member's totals and hours per activity type. Access and days as in the
      team view (team admin: current members from the day they joined; active auditor: everyone, the days of each
      stay; others 403), no descriptions, notes or days off, not logged; on both backends
    - [x] **L.11b** Page `/team/report` in cards: the period header, the choice of team, the tab "Audit" in the
      navigation (only for team admins and active auditors, after Year; Settings and Admin stay last); the note on who
      counts; the sentence in the members' settings
    - [x] **L.11c** From the team to its members: a member's card opens their month or year report of the team view for
      that period, with a link back in its banner; the viewer's own card opens their own report
    - [x] **L.11d** CSV export (`GET /api/teams/{team_id}/report.csv`): one row per figure, semicolons, UTF-8 with a
      byte order mark, formulas neutralized; the period and the page's notes as rows; the button "Export CSV" on the
      page
    - [x] **L.11e** "Save as PDF": a print layout of the cards (light theme, no navigation or buttons) and the browser's
      print dialog, with the same file name as the CSV (`20261109_1430_team_report_Platform`)
- [x] **L.12** Clean up the review's import parts once no imported data needs them: guessed tickets and their splits,
  the original spreadsheet line, weekend-hour day flags (storage on both backends, export format, the split and flag
  endpoints)
- [x] **L.13** Burger menu (SPEC 5.5): Team, Settings, Admin and "Log out" move into a menu (☰) where "Log out" was;
  name and dark mode switch stay, the switch as a plain icon; on phones listed directly in the phone's menu
- [x] **L.14** Imprint (SPEC 5.13): `/imprint` in German (§ 5 DDG), open to everyone at any time, linked as "Imprint"
  in every page's footer; name, postal address and e-mail from the SSM parameter `/work-tracker-<stage>/imprint`
  (locally `$WORK_TRACKER_IMPRINT`) through the open `GET /api/imprint`; "not configured" without them
- [x] **L.15** Mobile view (SPEC 5.5a): the app stays desktop first, but offers a clean view on phones (below 40rem;
  the desktop does not change), in steps:
    - [x] **L.15a** Header: one row with name, review count and "Menu"; the menu holds the navigation, search, name,
      dark mode switch and "Log out"
    - [x] **L.15b** Week: one card per day (day, type, times and break; worked, target, overtime; entries), forms in
      the card
    - [x] **L.15c** Tables of the other pages as blocks of label and value, the month report's hours on the ticket's
      line
    - [x] **L.15d** No sideways scrolling (the dashboard's "This year"), fewer chart labels, 44 px touch targets,
      16 px fields; the end-to-end test of every page at 320 px also fails on a list table scrolling sideways
- [x] **L.16** Contact form and support role (SPEC 5.14): anyone writes on `/contact` (also the imprint's second fast
  way of contact), support users answer by e-mail and keep track on `/support`; done messages are anonymized after 90
  days into a searchable archive. In steps:
    - [x] **L.16a** Support flag (admins set it in the user list, audit-logged) and the messages' storage on both
      backends with their history, the anonymizing (color and animal) and the full backup
    - [x] **L.16b** Contact page and `POST /api/contact` (open; hidden field, pause for visitors), linked from the
      imprint
    - [x] **L.16c** Support page: messages and archive with search, status, notes, "Answer by e-mail", delete;
      "Support" in the menu with the badge of new messages
- [x] **L.17** custom domain: `dev.<app-domain>` (dev) and `<app-domain>` (prod), through CloudFront
- [x] **L.18** Privacy policy (Datenschutzerklärung, GDPR Art. 13): what personal data the app keeps, why and for how
  long, linked next to the imprint in the footer
- [x] **L.19** sticky nav bar
- [x] **L.20** Delete an account with all its data (GDPR Art. 17), e.g. by an admin on request: days, entries and their
  history, settings, team membership, audit log and report views about them; their contact messages anonymized
- [ ] **L.21** Anonymous data analysis: aggregate figures across users (e.g. hours by activity type), only for groups
  of at least 5 people, without free text (descriptions, notes); the privacy policy (SPEC 5.15) says what is analyzed,
  why and on what legal basis before it starts, and drops "keine Analyse" from its overview
- [x] **L.22** CloudFront caches the static files (`/static/*`: scripts, CSS, fonts) with a cache policy of its own,
  so a page runs the Lambda only for its API calls (a page's ~20 modules at once over HTTP/2 reached the Lambda's
  concurrency limit: 429); `deploy/zappa.sh` clears that cache after each update, so a new version shows at once
- [x] **L.23** Support secure connection: some browsers complain that the site does not support secure connection.
  HTTPS itself worked; the app now sends HSTS, so after the first visit the browser goes to HTTPS directly, plus
  `nosniff`, `Referrer-Policy: same-origin` and no framing (SPEC 7.4)
- [ ] **L.24** Infrastructure as Code: using Terraform/Terragrunt to easily deploy and update infrastructure on AWS
