# Work Tracker — Specification

Status: **agreed** (21.05.2026)

A small web app that replaces the Google Sheet used to track working time and
task entries. It consists of a REST API (Falcon) and a simple browser frontend, and runs locally (SQLite) or on
AWS Lambda (DynamoDB), see 7.

## 1. Goals

- Record working days (start, end, break) and the tasks worked on.
- Calculate worked time, target time and a running overtime balance.
- Produce the **monthly work report**: coding work grouped by service.
- Import the existing spreadsheet data (2024, 2025, 2026).

Out of scope for now: export.

## 2. Conventions

| Topic       | Rule                                                                                                                                                           |
|-------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------|
| UI language | English                                                                                                                                                        |
| Dates (UI)  | `DD.MM.YYYY`; weeks start on Monday                                                                                                                            |
| Dates (API) | ISO 8601 `YYYY-MM-DD`                                                                                                                                          |
| Times       | 24 h format `HH:MM`                                                                                                                                            |
| Durations   | Shown as `h:mm` (e.g. `1:30`); entered also as `1.5`, `1,5`, `1h30m`, `1h30`, `90m` (see 2.1); task entries in quarter-hour steps (`:00`, `:15`, `:30`, `:45`) |

### 2.1 Entering durations

- Every duration field (entry duration, break, hours per week, opening balance with a minus) takes `1:30`, `1.5`,
  `1,5`, `2` (hours), `1h30m`, `1h30`, `1h`, `1 h 30 min`, `90m` and `90min`; spaces and case do not matter. A field
  shows the normalized `h:mm` once left; the API reads the same formats and answers with `h:mm`.
- Limits: an entry is at most as long as the rest of its day (from 08:00 at most 16:00; without a start time 24:00),
  a break at most the day from start to end, the hours per week at most 168:00. Explicit units over the limit are
  refused, naming the limit.
- A plain number (`2`, `90`) means hours if that fits the limit; otherwise the form asks "Did you mean 90 minutes
  (1:30)?" before saving.
- Entries stay in quarter hours: for `1.1` (1:06) the form offers 1:00 and 1:15 (the nearest one first) or cancel.
  Breaks and hours per week need no quarter hours.

## 3. Days

A day has a **date**, **day type**, **start**, **end**, **break** and an optional **note**
(e.g. "Anreise LÜBECK", "Training: Developing on AWS").

### 3.1 Day types

| Type                    | Set by                         | Target (on a work day)                    | PTO used                                     |
|-------------------------|--------------------------------|-------------------------------------------|----------------------------------------------|
| Work                    | default (never set explicitly) | daily target, e.g. 8:00                   | 0                                            |
| PTO (full day)          | user                           | 0:00                                      | 1                                            |
| PTO (half day)          | user                           | half the daily target, e.g. 4:00          | 0.5                                          |
| Sick (full day)         | user                           | 0:00                                      | 0                                            |
| Sick (half day)         | user                           | half the daily target                     | 0                                            |
| Overtime off            | user                           | daily target (nothing worked → −8:00)     | 0                                            |
| Unpaid leave            | user                           | 0:00                                      | 0                                            |
| Public holiday          | automatic (state, 3.5)         | 0:00                                      | 0                                            |
| Heiligabend / Silvester | automatic (if set, 3.5)        | 0:00                                      | 0.5 (half PTO + half free by company policy) |

On days that are no work days of the work schedule (3.5), e.g. weekends, every type has target 0:00 and uses no PTO.

- Travel and training days are normal work days; details go into the day note.
- Taking a few hours off against overtime needs no day type: fewer hours are worked, and
  the reason can go into the day note (e.g. "2:00 overtime used: Zahnarzt").
- Days off of the schedule (e.g. weekends) are optional: such a day only exists if something was recorded.
- Public holidays of the federal state of the work schedule (3.5), e.g. Berlin: Neujahr, Internationaler Frauentag, Karfreitag, Ostermontag,
  Tag der Arbeit, Christi Himmelfahrt, Pfingstmontag, Tag der Deutschen Einheit,
    1. and 2. Weihnachtstag, plus one-off holidays (e.g. 08.05.2025).
- An automatic day type can be overridden by the user.

### 3.2 Break

If no break is entered, it defaults to the legal minimum (German ArbZG §4), based on
presence time = end − start:

| Presence    | Default break   |
|-------------|-----------------|
| ≤ 6:00      | 0:00            |
| 6:00 – 6:30 | presence − 6:00 |
| 6:30 – 9:30 | 0:30            |
| 9:30 – 9:45 | presence − 9:00 |
| > 9:45      | 0:45            |

The break can always be overridden (e.g. 3:00 on a long day).

### 3.3 Time calculation

- **Worked** = end − start − break
- **Overtime (day)** = worked − target; all hours on days off of the schedule (e.g. weekends) count as overtime.
- **Overtime balance** starts at **0:00 on 01.06.2024** and is carried over across years.
  Days before that date are ignored; future days are not counted. Today counts, even before times
  are entered (a work day without times is −8:00 until then, as in the spreadsheet).

### 3.4 PTO allowance

- Entered per year as data (`pto_years`, API `/api/pto-years`): **allowance**, **extra days** granted on top and
  an optional **fixed carry-over**, e.g. as stated by HR; a year without entry has no PTO account.
- Current values: **30 days**; **2024: 17.5 days** (pro rata for June–December); **2025 and 2026: 30 + 1 extra day**
  (not permanent).
- Unused days are **carried over** into the next year, unless a fixed carry-over is entered (later years build on it).
- The year report shows carried-over days, allowance, days used and days remaining.

### 3.5 Work schedules

- **Hours per week** and **work days** (e.g. 40 h, Monday to Friday), split evenly into the **daily target**
  (40 h / 5 days = 8:00; 32 h / 4 days = 8:00; rounded down to whole minutes). Half days get half of it.
- Each schedule is **valid from a date** until the next one starts: a change counts from that day on and never
  rewrites earlier days. Days before the first schedule follow the first one; at least one schedule always exists.
- **Holidays**: each schedule names the German **federal state** whose public holidays apply (via `holidays`, e.g.
  `BE`, `BY`, `HH`) and whether 24.12. and 31.12. are **company half days** (half PTO, half free). A new employer or
  a move starts a new schedule.
- Initially one schedule: 40 h, Monday to Friday, Berlin, with company half days, from the balance start (the former
  fixed rules).
- The spreadsheet import keeps the sheet's own rule (`Sum` − 8:00 per day), independent of the schedules.

## 4. Task entries

Task entries belong to a day. The sum of entries does **not** need to match the worked
time (meetings, breaks etc. are not logged). Two kinds:

### 4.1 Ticket entry

| Field       | Notes                                                                                             |
|-------------|---------------------------------------------------------------------------------------------------|
| Ticket      | One ticket per entry, format `PREFIX-NUMBER` (e.g. `ENGINE-461`); required when entered in the UI |
| Service     | From the managed service list; may be unassigned                                                  |
| Duration    | `h:mm`, quarter-hour steps                                                                        |
| Description | Free text                                                                                         |
| Coding      | Checkbox, **unchecked by default**                                                                |

- Known prefixes: **KP** (Kundenportal), **TNG**, **ENGINE**, **AGA**, **MSI**.
- PR reviews are ticket entries (marked as coding).
- The service is stored **per ticket**: picking a known ticket pre-fills its service, and
  changing it applies to all entries of that ticket.
- **Renaming a ticket** (e.g. during review) moves all its entries to the new key; each entry's
  history records it (4.5). Renaming to a ticket that already exists merges both; the existing
  ticket keeps its service (it takes the renamed ticket's service only if it has none).

### 4.2 Activity entry

| Field         | Notes                                                                           |
|---------------|---------------------------------------------------------------------------------|
| Activity type | Managed list, initially **Tool Management**, **Meeting**, **Travel**, **Other** |
| Duration      | `h:mm`, quarter-hour steps                                                      |
| Note          | Free text (e.g. "new computer setup", "Hackathon Picard")                       |

### 4.3 Services (managed list)

Editable in the UI; initially:

| Short name | Full name                   |
|------------|-----------------------------|
| O365       | office-integration-service  |
| MSB        | microsoft-bookings-service  |
| ImmoDrop   | —                           |
| HiS        | history-service             |
| TTS        | text-transformation-service |

### 4.4 Warnings

A warning is shown only for a **past work day of the schedule (e.g. Mon–Fri, day type Work) without any entry**.

### 4.5 Entry history

Every change to a task entry is recorded, so it can be checked later what changed and why.

| Field   | Example                                                                                   |
|---------|-------------------------------------------------------------------------------------------|
| When    | 27.10.2026 14:05                                                                          |
| Action  | `created`, `imported`, `updated`, `renamed`, `merged`, `split`, `deleted`                 |
| Changes | only the changed fields, old → new: `ticket: TNG-4321 → KP-1234`, `duration: 1:00 → 1:30` |
| Detail  | optional, e.g. the original spreadsheet line on import (`3,0 TNG-5213, TNG-5214`)         |

- Written by the app (not by database triggers), so each line states the reason of the change.
- The history of a deleted entry is kept; entry ids are never reused.
- Visible on the entry (week view, review page); entries with changes after creation show a marker.
- Days have no history for now.

## 5. Views

### 5.0 Dashboard (start page)

- At `/` (a new database first goes through `/setup`); the week view is at `/week`, and former links like
  `/?week=…&edit=…` forward there.
- Key figures, each linking to its page: overtime balance today and its change this year, PTO left and planned, this
  week's worked of target, open review items.
- The overtime balance over time as a line (plain SVG, both themes; below zero in the warning color) with a switch:
  this month by day; this year, the last 12 months and everything since the balance start by month. Hover or the
  arrow keys show each value; all values also as a table.
- Coming up in the next 60 days: public holidays, company half days and planned days off (days in a row combined);
  a company half day says that it takes 0.5 PTO by itself.
- This year: days worked and average, sick days, overtime-off days, coding hours and the top three services.

### 5.1 Week

- Shows the work days of the current week (e.g. Mon–Fri); other days only if they hold data. Prev / next / today
  navigation, and a date field whose "Go" opens the week of that date.
- Per day: day type (a company half day as "Company half day · 0.5 PTO (half free)"), start / end / break, worked
  vs. target, overtime, the task entries and the warning.
- Add, edit and delete days and entries inline; open an entry's history (4.5).
- **Book days off** as a range (from, to, full-day type: PTO, sick, unpaid leave or overtime off; optional note): only
  the work days of the schedule get the type, public holidays and company half days stay automatic. A preview shows
  the days and the PTO used, and names company half days in the range with their 0.5 PTO, booked automatically; days that already hold times or entries are listed in a popup to skip them, book them too
  (keeping times and entries) or cancel. Clearing a range is not offered: single days can be deleted.
- Week totals and the overtime balance at the end of the week.

### 5.2 Month report

- **Coding work by service → ticket**: hours plus the entry descriptions. Unassigned entries are listed separately.
- **Other ticket work** (ticket entries not marked as coding) the same way, by service → ticket.
- **Activities** by activity type: hours plus the notes.
- Worked vs. target, overtime for the month, balance at month end; the hours in entries next to the hours worked
  ("Entries 152:30 of 160:00 worked", the same days: up to today).
- Previous / next / current month, and a date field whose "Go" opens the month of that date.
- PTO, sick and overtime-off days in the month.

### 5.3 Year report

Replaces the spreadsheet dashboard:

- Per year: worked total, target, average per day worked, overtime for the year, balance carried in and out.
- Per month: worked, target, overtime.
- Coding work and other ticket work by service, activities by type (hours and totals); the hours in entries next to
  the hours worked.
- Previous / next / current year, and a date field whose "Go" opens the year of that date.
- PTO carried over / allowance / used / remaining; sick, overtime-off and unpaid days.

### 5.4 Review

Lists everything that needs attention, each with its reason:

- Ticket entries whose ticket has **no service**; services can be assigned per ticket,
  also for several selected tickets at once.
- Entries with duration **0:00**.
- Ticket entries **without a ticket** (imported PR reviews).
- Entries and days **flagged during import** (uncertain ticket ids, weekend hours, …; see 6).
- Guessed tickets are grouped by ticket: confirm the key, rename (or merge) the ticket, or **split** its
  entries among several tickets when the spreadsheet line named an alias (`#4347 aka #1482`) or "ff";
  the hours are split evenly in quarter hours. Each of these clears the flags of the ticket's entries.
- A spreadsheet line the import already split among several tickets shows that split under the original
  line ("Split on import: TNG-4138 3:00 · TNG-4139 3:00"), so it is not split a second time.
- Each entry shows its description (or note) and the original spreadsheet line; "Details" (a button, for keyboard
  and touch) opens a dialog with the whole entry: date and weekday with the day's times, duration, ticket or activity,
  service, coding, description, flags, history and a link to its week. For a guessed ticket, all its entries.

An item leaves the list once the reason is fixed or the flag is cleared.

### 5.5 UI style

White, blueish and clean: generous whitespace, thin borders instead of heavy shadows, 6 px rounded
corners, one accent color. Warnings are the only loud element.

| Role             | Light     | Dark      | Use                                                 |
|------------------|-----------|-----------|-----------------------------------------------------|
| Text             | `#36454F` | `#E3E8EE` | All body text                                       |
| Muted text       | `#66737D` | `#9AA6B2` | Secondary information (weekday, target, notes)      |
| Background       | `#FFFFFF` | `#16191D` | Page                                                |
| Surface          | `#F4F7FB` | `#1F242A` | Cards, table headers, weekend columns               |
| Border           | `#DCE4EE` | `#333C46` | Lines between rows and cards                        |
| Accent           | `#2C69CB` | `#6EA2F0` | Links, primary buttons, active navigation, today    |
| Accent light     | `#E8F0FC` | `#1E2F48` | Hover, selected row                                 |
| Text on accent   | `#FFFFFF` | `#10233F` | Text of primary buttons                             |
| Warning          | `#E62E6B` | `#F06A93` | Highlights: borders, badges, bold text, icons       |
| Warning text     | `#C81E57` | `#FF8FB0` | Small warning text (better contrast than warning)   |
| Warning light    | `#FDECF2` | `#3A1F2B` | Background of warning rows                          |
| Positive         | `#1A7B5E` | `#4CC59A` | Positive overtime and balance (mint green)          |
| Positive light   | `#E6F6F0` | `#173A2F` | Background of positive badges                       |

- **Negative** overtime and balance are shown as a warning (including −8:00 on a work day without
  times yet), **positive** ones in mint green, zero in normal text.
- Warnings: a past work day without entries, review flags and the review count.
- Font: **Inter**, stored in the project (woff2 files with their OFL license); no external font or CDN
  requests. Tabular digits for times and durations, so columns line up.
- All colors, sizes and spacings are CSS variables in one stylesheet. **Dark mode** is a second set of color
  values; the theme (System, Light, Dark) is chosen on the settings page and stored in the database. System follows
  the light or dark setting of the system. A switch between the name and "Log out" in the navigation (a moon in light
  mode, a sun in dark mode) turns dark mode on or off and saves it as Light or Dark.
- Text contrast is at least 4.5:1 on its background, except the warning highlight color, which is
  only used for large or bold text, borders and icons. A test checks every text color on background, surface and
  its tint, in both themes.
- **Accessibility**: WCAG 2.2 AA (checked with axe-core on all pages, both themes). Links in text are underlined;
  hints and errors describe their field (`aria-describedby`); every field has a visible label; Escape closes inline
  forms, and focus returns to the button that opened them; "Skip to content" is the first link on each page.
  Narrow screens and zoom follow in TASKS.md 6.7.

### 5.6 Login

- A user has a username and an e-mail address (both unique, ignoring case), a first name, an optional last name and a
  password (stored as a salted scrypt hash). A new password needs at least 12 characters with letters, digits and a
  special character (anything but letters, digits and spaces); existing ones keep working. Log in with the username
  or the e-mail address.
- A login is a session: a random token in an `HttpOnly`, `SameSite=Strict` cookie (`Secure` over HTTPS), stored only as
  a hash. It stays valid for 24 hours since the last activity, root's for 1 hour (renewed at most every 30 minutes,
  root's every 5); "Log out" ends it, a new password ends all other sessions. After 5 failed logins or registrations within a minute, both pause for a
  minute.
- Every page and the API need a login (pages forward to `/login?next=…`, the API answers 401); `/login`, `/register`,
  `/health`, the API docs and the static files stay open. A new database creates root in the setup (5.7); one with
  users but no root offers "Create root admin" once on `/login`; on AWS Lambda both only with the setup token (7.4).
  Locally, a command resets a forgotten password; on AWS Lambda, where nobody has a shell, an admin sets a one-time
  password for a user or team admin, root for an admin, and root resets its own with a new setup token (7.4). The
  one-time password is changed at the next login:
  - It is set in its own section of the admin page by the user's e-mail address (ignoring case), after a question.
    The app makes it (four groups of four letters and digits, e.g. `k7Qm-3xTp-9wLs-Rf2c`) and shows it only once, to
    pass on. The user's sessions end and their password no longer works.
  - After logging in with it, every page forwards to `/password` and the API answers 403, until the user chose their
    own password there. The admin page shows "One-time password" next to the user's status until then.
  - Not for the own account (409): that password is changed in the settings. It stays valid until it is used. It
    does not switch off two-factor login.
- Two-factor login (TOTP, an authenticator app): root and admins must use it, users and team admins may switch it on
  in their settings.
  - Setting it up shows a QR code (an SVG made on the server) and the secret as text; a first code confirms it. Root
    sets it up right after the setup, an admin at the next login after being appointed: until then every page
    forwards to `/2fa` and the API answers 403, as with a one-time password.
  - Codes have 6 digits and change every 30 seconds; one step before or after is accepted, and each code works only
    once. A wrong code counts as a failed login (5 per minute).
  - Setting it up shows 10 recovery codes once, stored only as hashes; each replaces a code once. Without them, an
    admin resets two-factor login for a user or team admin, root for an admin, and root its own with a new setup
    token (7.4); it is then set up again at the next login.
  - A new authenticator app (e.g. a new phone) in the settings, also for root and admins: with the password and a
    current code (or a recovery code; a wrong one counts as a failed login), a new secret is shown as for the setup;
    it replaces the old one once a code of the new app confirms it, until then the old app keeps working. The
    recovery codes stay.
  - "Remember this browser" skips the code for 30 days in that browser (its own `HttpOnly` cookie, a random token
    stored as a hash), never for root. A new password or a reset of two-factor login forgets all browsers.
- `WORK_TRACKER_AUTH=off` switches the login off for local development (`STAGE=Local` only, see 7.1); the app then
  works on the first user's data who is not root.

### 5.7 Data per user

- Each user has their own days, entries with their history, review flags, tickets with their service, services,
  activity types, work schedules, PTO years and settings (balance start, opening balance, theme, setup done).
  Nobody sees or changes another user's records, root and admins neither; an unknown or foreign id answers 404, using
  another user's service or activity type 409.
- A user is identified by a random UUID and has one app role; in a team, the membership has a team role; an auditor
  is assigned to teams. The first user who is not root takes over all records of a database used without users. A
  new user (not root) starts with the four default activity types and goes through the setup; "Log out" is there
  during the setup too, and after the next login the setup continues.
- App roles:
  - **root** runs the app: exactly one, created once (in the setup of a new database, or with "Create root admin"
    on `/login` of one with users; on Lambda with the setup token, 7.4); it cannot be demoted or deactivated, and
    nobody is made root. Root switches registration on and off, appoints and removes admins, sets one-time passwords for
    admins, resets their two-factor login, deactivates and reactivates them, and makes and restores the full backup
    (5.9). Root tracks no work: no setup, days or reports, never in a team. It reaches `/admin` and its settings
    (profile, password, color theme); other pages forward to `/admin`, the rest of the API answers 403.
    Its start page is `/admin`.
  - **admin** organizes and tracks their own work: manages users and team admins (one-time password, two-factor
    reset, deactivate, reactivate), teams, team services, team admins and auditors. Admins do not appoint admins and
    do not deactivate them.
  - **user** tracks their own work and sees their own reports.
- Team roles (on the membership, for admins and users alike): **member** and **team admin**. A team admin manages
  the team they are in (invitations, members, team services) and has its team view; leaving the team ends the role.
  Nobody changes their own team role, so no admin makes themselves the one who sees the members' reports.
- **Auditor**: an admin assigns a user or another admin (never themselves, nor root) to one or more teams, optionally
  until an end date (the access ends by itself then), otherwise until removed; deleting a team ends its assignments.
  An auditor has the team view of those teams read-only, of everyone who was ever in the team, each for the days they
  belonged to it (several stays each count). Being auditor changes nothing else.
- Registration: while root has switched it on (off by default), the login page links to `/register`. A new user
  enters the fields of the login, is logged in at once (no e-mail confirmation) and goes through the setup. Off, or
  with the login off, `/register` answers 404.
- Admin page `/admin` (linked in the navigation for root and admins; its API answers 403 to others): the users with
  username, name, e-mail address, app role, team and team role, status, registration and last login, none of their
  time data; roles and the status (Active or Deactivated, a deactivation asked first) are dropdowns in the table, a
  one-time password has a section of its own. Root sees registration, the admins and the full backup; admins see
  users, teams and auditors. Deactivated users are logged out at once and refused at login, their data kept. Nobody demotes or deactivates
  themselves; users are not deleted. Locally, a forgotten password is also reset with the command.
- Audit log: every change of roles, team admins and auditors, deactivation and reactivation, one-time password,
  two-factor reset, registration switch, team change, full backup and restore is logged with who, what, whom and when
  (no personal records); so are everyone's changes to their own login: a new password (also with the `set-password`
  command), two-factor login switched on or off, new recovery codes, a new authenticator app. Root and admins see the whole log on `/admin`, every user the entries about their own
  account in the settings.
- Teams: a user is in at most one team; the membership history (joined on, left on) keeps which team a user was in on
  each day. An admin creates, renames and deletes teams (only without members; a deleted team stays in the history)
  and makes members team admins.
- Invitations: an admin, or a team admin for their team, invites by the exact e-mail address (ignoring case); the
  answer and the list of open invitations never tell whether such a user exists. Users never see which teams exist.
  The invited user accepts or declines in the settings (a badge on Settings while one is open); accepting one declines
  the others and leaves the current team. The inviter can withdraw an open invitation.
- Services: a service is personal or belongs to a team. Members choose their team's services next to their personal
  ones; only admins and the team's admins change team services. On leaving (or being removed), the team services
  the user's tickets use are copied into their personal services, or a personal service with the same short name is
  used, so the tickets keep their service.
- Team view: a team admin chooses a current member of their team on the dashboard and sees their dashboard, week,
  month and year read-only, from the day the member joined the team (earlier days show as "not in this team"). Entry
  descriptions and notes are shown, day notes and the review are not; the overtime balance and PTO left are running
  figures over the whole time. Admins get no such view unless they are team admin or auditor of that team; former
  members drop out (auditors still see them, see above). Members see in their settings which team admins and
  auditors can look, and a log of who looked at which report and when.

### 5.8 Export and import (own data)

- Export: "Export my data" on the settings page downloads one JSON file of the user's own records: days, entries with
  their history (also of deleted entries), review flags, tickets, services, activity types, work schedules, PTO years,
  settings and theme. It starts with `{"format": "work-tracker", "version": 1, "exported_at": …}`; every record has a
  file id (1, 2, …), and references inside the file use them, also in history lines. Team services the tickets use are
  included by short name, name and team.
- Not in the file: password, sessions, users, teams, memberships, invitations and the report view log.
- Import: in `/setup`, a user without days and entries may upload such a file instead of entering the setup data.
  Settings, work schedules and PTO years come from the file, its activity types replace the four defaults, team
  services become personal services (as on leaving a team), and the setup is done. A summary shows the counts per
  type.
- A file of an unknown format or a newer version is refused, and so is a file referring to records it does not hold;
  both are checked before anything is written, so nothing is.
- SQLite imports in one transaction: if it fails, nothing stays. DynamoDB writes atomic chunks; an import that stops
  halfway (e.g. a timeout on AWS) marks the account, the setup stays open, and importing the file again first removes
  what the unfinished import wrote. Finishing the setup is the last step and clears the mark.
- Exporting, importing into a new user and exporting again gives the same file (apart from `exported_at`, and team
  services, which come back as personal ones).

### 5.9 Full backup and restore (root)

- Root downloads one file of the whole database on `/admin`: all users (with password hashes and two-factor
  secrets), teams, memberships, invitations, auditors, every user's records with their history, the report view log,
  the audit log and the app settings. Not in it: sessions, remembered browsers, failed logins, the used setup tokens.
  It works across backends (e.g. local SQLite to DynamoDB).
- The file is compressed (gzip) and encrypted with a passphrase root enters (at least 12 characters): AES-256-GCM
  with a key from scrypt; the header (`{"format": "work-tracker-backup", "version": 1, …}`) holds the salt and the
  nonce, nothing personal. The passphrase is stored nowhere: without it the file is useless.
- Restore, on `/admin` with the file and its passphrase: a database holding nobody but root restores at once.
  Otherwise root is asked whether to purge the current state first and confirms by typing `purge`; everything but
  root goes, then the backup comes in. Root stays as it is (the backup's root is skipped, and what it did is credited
  to the current root); everyone else has their password and two-factor login from the backup, and all other sessions
  end. Optionally root takes over the login of the backup's root (username, e-mail address, name, password, two-factor
  login): it keeps its account and what it did, its sessions end, and it logs in again with that login.
- A new root restores before setting up two-factor login, on `/2fa`, while the database holds nobody but root: only
  taking over the backup's root login, which comes with its own two-factor login. Everything else still requires it.
- A wrong passphrase, a damaged file, an unknown format or a newer version is refused before anything is written.
  SQLite restores in one transaction. DynamoDB purges and restores in atomic chunks; one that stops halfway marks the
  database: only root can use the app until restoring the file again finishes it.
- Both downloads and requests stay below Lambda's 6 MB (compressed, the data of a few users is far smaller); larger
  databases would need S3 (later).

### 5.10 Search

- A search field in the navigation on every page (except the search page itself; not for root): Enter opens the
  search page with the text.
- The search page: words or ticket key, a service ("No service" too) or an activity type, and the period: All time
  (default), This year, Last year, Last 12 months (from the first of the month eleven months back to today), This
  month or Custom (From and To, each optional). It searches on "Search" or Enter, and the criteria go into the URL
  (bookmarks, Back).
- An entry matches when every word, ignoring case, starts its ticket key (`ENGINE-59` finds ENGINE-590…599) or is a
  part of its description or note, of its service (short name or name: `MSB`, `bookings`) or of its activity type.
- Results: total hours and number of entries, by ticket or activity type (most hours first) and by month (linking to
  the month report), and the entries, newest first, each linking to its week and with "Details" (5.4). The list
  shows the newest 100 entries and "Show all" for the rest; the sums always count all.

## 6. Import (spreadsheet CSV)

Run locally as a command, one CSV per year (e.g. `Time_tracking_DK - 2026_Data.csv`).
Columns: `Date` (` DD.MM.YYYY Ddd`), `Start`, `End`, `Pause` (minutes), `Sum`, `Comment`.

### 6.1 Days

- Rows with no start / end and no comment are skipped (future days).
- The placeholder `08:00–16:00` on weekends, PTO and holidays is ignored.
- Day comment → day type:

  | Comment | Day type |
    |---|---|
  | `PTO`, `<8> PTO` | PTO (full day) |
  | `PTO` with `Sum` 0:00 (e.g. 30.05.2025) | Overtime off |
  | `Off sick`, `PTO (off sick)` | Sick (full day) |
  | holiday names, `Public Holiday …` | Public holiday (cross-checked with the automatic list) |
  | `0,5 PTO / Heiligabend`, `0,5 PTO / Silvester` | automatic Heiligabend / Silvester |

- **Half days**: a line `4,0 PTO …` or `0,5 PTO` (→ PTO half day), or `4,0 PTO (off sick)` /
  `4,0 off sick …` (→ sick half day), on a day whose `Sum` is at least 8:00. The sheet
  extended the end time by the absence, so the import moves the end back by 4:00 (20.06.2024: 07:15–16:00 → 07:15–12:
  00).
- **Overtime used**: any other `<hours> PTO …` line (e.g. `2,0 PTO Zahnarzt`, `3,0 PTO TTU`,
  `4,0 PTO (Wohnungsbesichtigung)` with `Sum` 4:00) is a reminder only → day note; times unchanged.
- **Weekends**: the sheet stores weekend work as `Sum` − 8:00 (06.12.2025: 08:00–19:30 = 3:30
  worked). The import keeps those numbers (start, end = start + worked, no break) and **flags**
  every weekend day with worked time or entries (incl. 09.11.2024 and 25.01.2025, whose
  hours were not counted in the sheet).
- An empty `Pause` with start and end set is stored as an explicit 0:00 break (the sheet value is the truth).

### 6.2 Comment lines (one line = one entry)

| Line                                                                                                             | Result                                                                                                                               |
|------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| `<hours> … <ticket> …`                                                                                           | Ticket entry, no service; tickets may appear anywhere in the line; coding checked for known prefixes (4.1)                           |
| several tickets (`<t1>, <t2>`, `<t1>/<t2>`, `<t1> and <t2>`)                                                     | One ticket entry per ticket, hours split evenly in quarter hours, remainder on the first entries (1:30 / 4 → 0:30, 0:30, 0:15, 0:15) |
| `<hours> PR review …` or `<hours> PR …` without a ticket                                                         | Ticket entry **without ticket**, coding checked → review                                                                             |
| `<hours> Meeting: <text>`                                                                                        | Activity "Meeting", note = text (tickets stay in the note)                                                                           |
| `<hours> Meeting(s) …`, `Tactical Meeting`, `Teamstufe Meeting`, `Standup`, `Retro`, `Retrospective`, `Planning` | Activity "Meeting", note = whole text                                                                                                |
| `<hours> TM`, `Tool Management (TM)`, `GCC (Tool Management)`                                                    | Activity "Tool Management"                                                                                                           |
| `<hours> Anreise / Abreise / Anfahrt / Abfahrt …`                                                                | Activity "Travel", note = text                                                                                                       |
| `<hours> <other text>`                                                                                           | Activity "Other", note = text                                                                                                        |
| `<ticket> <text>` (no hours)                                                                                     | Ticket entry with 0:00 → review                                                                                                      |
| text without hours or ticket                                                                                     | Appended to the day note                                                                                                             |

- Hours use a decimal comma (`1,5` → `1:30`, `0,75` → `0:45`).

### 6.3 Ticket clean-up

| Found                            | Stored                                               | Flagged |
|----------------------------------|------------------------------------------------------|---------|
| `EINGINE-461`                    | `ENGINE-461`                                         | no      |
| `TNG 5212`, `TNG4840`, `KP1895`  | `TNG-5212`, `TNG-4840`, `KP-1895`                    | no      |
| `TNG TNG-4828`                   | `TNG-4828`                                           | no      |
| `MSI-02`                         | `MSI-2`                                              | no      |
| `#KP-1494`                       | `KP-1494`                                            | no      |
| `#4138`, `# 4251` (number only)  | `TNG-4138`, `TNG-4251` (≥ 4000 → TNG, lower → KP)    | yes     |
| `#4347 aka #1482`, `#4347/#1482` | one entry `TNG-4347`, description gets "aka KP-1482" | yes     |
| `TNG-2035ff` ("fortfolgend")     | `TNG-2035`; the flag keeps the original text         | yes     |

### 6.4 Safety and reconciliation

- Re-importing a year that already holds data is refused unless replacing is requested explicitly.
- The data goes to the only user (without users: to the first one created later); with several users the user is
  named (`--user`, username or e-mail address).
- The import prints a summary: days, entries, corrections, flagged items.
- Every imported entry gets an `imported` history line with its original spreadsheet line.
- **Reconciliation**: per year, the app's overtime is compared with the sheet's (`Sum` − 8:00 per calendar day); days
  that differ are listed. Expected differences are only
  the known corrections below.

### 6.5 Known data corrections

- 2024 unpaid leave (marked "PTO" in the sheet): 08.08., 09.08., 04.10., 27.12. and 30.12.2024.
- 2024 PTO: 17.5 days allowance, 17.5 used → nothing carried over into 2025; 3 days carried over into 2026.
- The 2026 sheet dashboard already includes 27.10.2026 (6:30) in its total but not in its target;
  the balance up to 26.10.2026 is 13:45, not 20:15.

## 7. Technical

- Python 3.14 (the newest Python runtime on AWS Lambda), Falcon (WSGI), spectree + pydantic for validation and
  OpenAPI docs.
- Frontend: static HTML / CSS served by the app, TypeScript compiled locally to JavaScript (`npm run build`).
- Runs locally with a single command.
- Tests with pytest; code quality checked with flake8 (radon max CC 6, max line length 127).

### 7.1 Stages

- The stage chooses the storage backend once, on start:
  - `STAGE=Local`: the SQLite file `$WORK_TRACKER_DB` (default `work_tracker.db`). `STAGE` comes from `.env`, which
    pipenv loads; `.env` is git-ignored, `.env.example` (`STAGE=Local`) is committed and copied once.
  - On AWS Lambda, recognized by `AWS_LAMBDA_FUNCTION_NAME` (set by Lambda itself): always the DynamoDB table
    `$WORK_TRACKER_TABLE`; `STAGE` is not needed there.
  - Anything else stops the app on start with a clear message: no `STAGE` outside Lambda (e.g. `STAGE is not set: put
    STAGE=Local into .env to run locally; on AWS Lambda the stage is detected`), an unknown value, `STAGE=Local` on
    Lambda, or `WORK_TRACKER_AUTH=off` on Lambda. The container (`Dockerfile`, `compose.yaml`) stops too, until it is
    fixed or removed.
- The command line tools (importer, `set-password`) work on the local SQLite database only. Tests choose their backend
  themselves and do not depend on `STAGE`.

### 7.2 Storage

- Both backends implement the same repository interfaces (days, entries with history, review flags, tickets, services,
  activity types, schedules, PTO years, settings, users, sessions, teams, invitations, report views). Resources and
  reports use only these interfaces and a backend-neutral transaction, never SQL; the importer and the command line
  tools work on SQLite only (7.1). The same contract tests run against both backends (DynamoDB through `moto` in the
  tests).
- SQLite: as before, migrated on start.
- DynamoDB: one table in `eu-central-1` (Frankfurt), on-demand capacity, point-in-time recovery on; a command creates it.
  - Composite key `PK` / `SK`. A user's records live in their own partition `PK = USER#<user id>` (e.g.
    `SK = DAY#2026-10-30`, `ENTRY#…`, `TICKET#TNG-5213`). App-wide records (users, teams, memberships, invitations,
    sessions, failed logins, app settings) have their own key prefixes; unique usernames and e-mail addresses are kept
    by conditional writes on `USERNAME#…` / `EMAIL#…` items.
  - Sessions and failed logins also expire through DynamoDB's time to live; the app still checks the expiry on reading,
    since the deletion can come late.
  - A schema version item takes the place of `PRAGMA user_version`: the app refuses a table written by a newer
    version, and later data changes are numbered scripts like the SQLite migrations.
  - A transaction collects its writes and sends them at its end, so its reads see them and a failure writes
    nothing; ids are random UUIDv7, in the order of creation.
  - A change touching at most 100 items is atomic, as in SQLite (DynamoDB's transaction limit). Larger changes
    (renaming or merging a ticket, assigning a service to many tickets, leaving a team) are written in atomic chunks,
    e.g. an entry together with its history line, and end with the step that closes them (deleting the old ticket,
    ending the membership). Repeating a change that stopped halfway completes it.
  - Lists are read in full; DynamoDB's paging stays inside the repositories.
- One table holds all users. Data reaches it through the export and import of 5.8, e.g. a local database: import the
  spreadsheets locally, export, then import the file in the setup on AWS.

### 7.2a Ids

- Records get a UUIDv7 as id: entries, history lines, review flags, services, activity types, work schedules, teams,
  memberships, invitations and report views. Its start is the time of creation, so ids sort in the order the records
  were created; the rest is random, so an id neither can be guessed nor tells how many records the app holds (integer
  ids counting up would show other users' activity to anyone who creates a record now and then).
- Users keep their random UUID (version 4); tickets, days and PTO years keep their natural keys (ticket key, date,
  year), sessions the hash of their token.
- The API takes and gives these ids as strings, e.g. `/api/entries/0190a3c4-…`.
- A migration gives the records of an existing SQLite database UUIDv7 ids in the order of their old ids, also where
  they are referred to: tickets (service), entries (activity type), history lines (entry; activity types in the changes,
  "Split from entry …"), review flags, team services, memberships, invitations and report views.
- DynamoDB needs no id counters any more; sort keys hold the ids, which keep the order of creation.
- The export file keeps its own ids (1, 2, …, now written as text; numbers are read too) and its version 1; the import
  gives the records new UUIDv7 ids.
- The history shows an activity type that was deleted since as "deleted activity type".

### 7.3 Access to data

- The rules of 5.7 hold on both backends and are enforced by the app: the user id comes from the session only, never
  from the request, and every repository of personal records is bound to that user id (`user_id = ?` in SQLite, the
  partition `USER#<user id>` in DynamoDB). A team admin reads a member's data only through the team view's check
  (current member of their team, from the day they joined), an auditor only through the same view with the
  assignment's check (team and end date, the days of each stay); root and admins get users and teams, never time
  data. Only the full backup (5.9) holds everybody's data, encrypted with root's passphrase.
- Tests on both backends: another user's id answers 404 for every repository and API resource (team and admin routes
  403); the API tests run the whole app on each backend.
- AWS: the Lambda's IAM role may read and write only this one table and its indexes, and read only the setup token
  parameter (7.4); the app hands out no AWS credentials.

### 7.4 Deployment (AWS Lambda via zappa)

- Two stages, `dev` and `prod`: zappa deploys each as a Lambda function `work-tracker-<stage>` in `eu-central-1`,
  runtime `python3.14`, from `zappa_settings.json` (committed; no secrets, no account id). Both extend its `base`
  settings and differ only in the S3 bucket for the packages (`work-tracker-deploy-<stage>`).
- Each stage has its own table `work-tracker-<stage>` and setup token `/work-tracker-<stage>/setup-token`: the app takes
  both names from the function's name (`WORK_TRACKER_TABLE` and `WORK_TRACKER_SETUP_TOKEN_PARAMETER` can name others).
- A function is reached by its Function URL (HTTPS, no API Gateway: no path prefix the app's links would miss, no 29 s
  limit; no CORS, the app only talks to itself).
- Environment: `TZ=CET-1CEST,M3.5.0,M10.5.0/3` (Berlin time as a rule, so "today" is right even without time zone
  files in the image; Lambda runs in UTC).
- zappa logs at WARNING: its default, DEBUG, writes every request with its cookies and body to CloudWatch.
- Each function runs as the role `work-tracker-<stage>-ZappaLambdaExecutionRole` (the name zappa looks up; it creates
  no role of its own), made from `deploy/lambda-policy.json`: read and write the stage's table, read the stage's
  parameter (decrypting it only through SSM), write its logs. Besides Lambda, only the stage's keep-warm rule may use
  it (`deploy/lambda-trust-policy.json`): zappa's EventBridge rule calls the function every few minutes, so it rarely
  starts cold, and zappa hands the rule the function's role.
- Setup token: the URL is public, so on Lambda root is created only with the setup token. It is
  a `SecureString` in the SSM Parameter Store of `eu-central-1`, created once by hand and never in the repository:
  `aws ssm put-parameter --name /work-tracker-<stage>/setup-token --type SecureString --value "$(python -c "import
  secrets; print(secrets.token_urlsafe(32))")"` (at least 32 characters).
  - While there is no root, `/setup` (or `/login` of a database with users) asks for it; the app reads the parameter
    only then, not on every start, and creating root in any way needs it. A wrong token is refused and counts as a
    failed login (5 per minute, 5.6), and the comparison takes the same time for every token. Without the parameter,
    no root is created and the page says so.
  - Each token works once: the app keeps a hash of every token it used and refuses it afterwards, so a forgotten
    parameter is harmless; deleting it afterwards is still the rule (README).
  - Root forgot its password or lost its authenticator: create the parameter again with a new token; "Reset root
    login" on `/login` takes it, sets a new password and resets two-factor login (set up again right after).
  - Registration stays off until root switches it on, so nobody else gets an account. Locally (`STAGE=Local`), no
    token is needed.
- The package leaves out `examples/` (the real spreadsheet data), `*.db`, `.env`, the tests, `node_modules` and
  `.venv`; the compiled JavaScript is built before deploying (`npm run build`). `deploy/zappa.sh` packages from a
  virtualenv outside the project that holds only what the app needs (no moto, pytest, …): about 26 MB. zappa copies the
  active virtualenv's packages apart from the project files, so excluding `.venv` would not keep the dev tools out.
- Expected costs for a single user: a few cents per month (Lambda and DynamoDB on demand, no VPC, no NAT gateway).

## 8. Future ideas

- Export (CSV / spreadsheet format).
- Settings page with overtime balance, PTO years, work schedules and holiday rules is done (TASKS.md, 6.1a–6.1c).
- Initial setup of a new database on `/setup` is done (TASKS.md, 6.3).
