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

- [x] **L.1a** Settings page `/settings`, data only (no change to the calculations): overtime balance start date and
  opening balance (h:mm, signed) via `GET/PUT /api/settings`; PTO years (allowance, extra days, fixed carry-over,
  note) as an editable table on the existing `/api/pto-years`; services and activity types moved here from `/lists`
  (which forwards to `/settings#services`)
- [x] **L.1b** Work schedules valid from a date (a change counts from that day on, never rewrites the past): hours per
  week and work days (e.g. Mon–Fri), split evenly into the daily target (40 h / 5 days = 8:00; half days: half of
  it); replaces the fixed 8:00 in `src/lib/daytypes.py`; API `/api/work-schedules` (GET, POST, PUT, DELETE) and a
  section on the settings page; the first schedule is 40 h Mon–Fri from the balance start. The importer keeps the
  spreadsheet's own 8:00 rule
- [x] **L.1c** Holidays in the work schedule: federal state (`holidays` subdivision, e.g. `BE`) and whether 24.12. and
  31.12. are company half days (0.5 PTO each); replaces the fixed Berlin calendar in `src/lib/public_holidays.py`
- [x] **L.2** Days off as a range: "Book days off" button on the week page opens a form (from, to, full-day type: PTO,
  sick, unpaid leave or overtime off; optional note). Only the work days of the schedule get the type; weekends, days off
  of the schedule, public holidays and company half days stay automatic. A preview shows the days and the PTO used before
  saving; future days are allowed (planned PTO). If days in the range hold times or entries, a popup lists them: skip
  these days, book them too (times and entries are kept), or cancel. Saved in one transaction via
  `POST /api/days/range`; afterwards the week of the first day is shown. Clearing a range is not part of it (single
  days can be deleted)
- [x] **L.3** Initial setup: a new database starts clean (a migration marks a database holding days or entries as set
  up and leaves it unchanged; an empty one loses the original setup's PTO years and services and is marked not set
  up). Until set up, every page forwards to `/setup` (the API stays reachable), a guided page in five steps with
  defaults: 1. start day (today) and opening balance (0:00); 2. work schedule (40 h, Mon–Fri, Berlin, company half
  days); 3. PTO days per year (30) and for the first year, with a proposed pro-rata number (the start month counts if
  starting by the 15th, rounded up to half days) that can be changed; 4. services (optional); 5. summary and "Start",
  saving everything at once and opening the week view. A side note points to the spreadsheet import instead. The
  README's "start from zero" shrinks to starting on a new database file
- [x] **L.4** Dark mode: a second set of the color variables (WCAG AA contrast, checked by a test), previewed on
  the component gallery; the theme (System, Light, Dark) is chosen on the settings page and stored in the database
  (`GET/PUT /api/theme`); pages are rendered with the theme, so nothing flashes
- [x] **L.5** Accessibility, WCAG 2.2 AA (found with axe-core on all pages, both themes): light accent `#2C69CB` and
  mint `#1A7B5E` (all text pairs at least 4.5:1, the contrast test checks light mode fully too); entry actions always
  visible in muted text instead of dimmed; links in body text underlined; error messages connected to their field
  (`aria-describedby`); visible labels for the "add" forms of the settings tables; Escape closes inline forms and the
  booking form, and focus returns to the button that opened them; a "Skip to content" link first on each page; the
  gallery's code blocks focusable. No separate axe script and no screen-reader checklist
- [ ] **L.6** Overtime used in hours: record hours taken from the overtime balance on a work day (e.g.
  `2,0 PTO Dentist`,
  today only a day note) as a value, and show them in the year report next to the days off. On hold: kept as day
  notes for now, to see how hours off are used in practice
- [x] **L.7** Dashboard as the start page `/` (until the database is set up, `/setup` as before); the week view moves to
  `/week`, and old links like `/?week=2026-W44&edit=…` forward there with their parameters. Content: key figures
  (balance today and this year's change, PTO left and planned, this week worked of target, open review items; each
  links to its page), a chart of the overtime balance with a switch (current month by day; year, last 12 months and
  all since the balance start by month; below zero in the warning color; plain SVG, both themes), coming up in the
  next 60 days (public holidays, company half days and planned days off, days in a row combined), and this year's
  figures (days worked and average, sick days, overtime-off days, coding hours, top services). Data from
  `GET /api/dashboard` in one transaction
- [x] **L.8** Login: a user has a username and an e-mail address (both unique, ignoring case), a first name, an optional
  last name and a password (at least 12 characters, stored as a salted scrypt hash). Login with username or e-mail
  address; the session is a random token in an `HttpOnly`, `SameSite=Strict` cookie (`Secure` over HTTPS), stored hashed
  in a table, valid for 24 h since the last activity (each request extends it to 24 h from now; the stored expiry is
  renewed at most every 30 minutes); log out ends it, a password change ends all sessions; after 5 wrong attempts logins
  pause for a minute. Pages forward to `/login?next=…`, the API answers 401; `/login`, static files, `/health` and the
  API docs stay open. The first user is created in the setup (new databases) or once on the next visit (existing ones);
  the settings page changes the profile and password; a command resets a forgotten password. `WORK_TRACKER_AUTH=off`
  switches the login off for local development
- [x] **L.8a** Multi-user app, run locally (a later AWS Lambda deployment stays possible; it is a task of its own):
  several users with their own time tracking in one database, data per user. Ownership: days, entries, history, review
  flags, settings (balance start, opening balance, theme), work schedules, PTO years, tickets with their service and
  activity types belong to a user; services belong to a user (personal) or to a team (shared with its members);
  users, teams and memberships are app-wide. Nobody sees someone else's days and entries, the admin neither (technical
  support works on the database directly; team admins get a read-only view in L.10). Roles: admin, team admin, user. In
  three steps:
  - [x] **L.8a.1** Data per user: `user_id` (a random UUID) on every personal table; a migration gives all existing
    records to the only user and makes that user admin (a database with data but no user: the first user created takes
    over everything without an owner). Repositories, reports, review, dashboard, setup and the importer work per user
    (`--user` for the importer); a new user starts with the four default activity types and goes through the setup for
    their own data
  - [x] **L.8a.2** Registration and roles:
    - `/register` with the fields of the login: the new user is logged in at once and goes through the setup (no
      e-mail confirmation). Registrations share the pause of the failed logins (5 per minute). The login page links to
      it only while registration is on; otherwise `/register` answers 404, and it does not exist with the login off
    - Admin page `/admin` (an "Admin" link in the navigation for admins only; the admin API answers 403 to others):
      registration on or off (off by default), and the users with username, name, e-mail address, role, active,
      registered on and last login (new columns), but nothing of their time data
    - Change the role (admin or user; team admin comes with L.8a.3), deactivate and reactivate: a deactivated user
      cannot log in, their sessions end at once, their data is kept. Nobody deactivates or demotes themselves, so an
      active admin always remains. Users are not deleted
    - Forgotten passwords stay with the command on the computer running the app
  - [x] **L.8a.3** Teams:
    - A user is a member of at most one team. Memberships are kept as history (team, joined on, left on), so it stays
      known which team a user was in on each day (e.g. for L.10)
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
- [x] **L.8b** Password rules: a new password (registration, first user, password change, `set-password`) has at least
  12 characters with letters, digits and at least one special character (anything but letters, digits and spaces).
  Existing passwords keep working
- [ ] **L.9** Narrow screens and zoom (WCAG 1.4.10 Reflow, 320 CSS px / 200 % zoom): wide tables scroll in their own
  container, the navigation wraps, form grids fall back to one column
- [ ] **L.10** Team view for team admins (after L.8a.3, to be discussed): on the dashboard, a team admin switches to a
  member of their team and sees that member's summary and reports, read-only, only for the days the member was in their
  team (membership history from L.8a.3). To decide: which reports (dashboard, week, month with the coding work and its
  descriptions, year), whether members see who looked at their data, and whether admins get the same view
- [ ] **L.11** AWS Lambda deployment (to be discussed); with it, the admin sets a one-time password for a user who
  forgot theirs (changed at the next login), since nobody has a shell on the computer running the app
