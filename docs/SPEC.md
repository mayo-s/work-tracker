# Work Tracker — Specification

Status: **agreed** (21.05.2026)

A small local web app that replaces the Google Sheet used to track working time and
task entries. It consists of a REST API (Falcon) and a simple browser frontend.

## 1. Goals

- Record working days (start, end, break) and the tasks worked on.
- Calculate worked time, target time and a running overtime balance.
- Produce the **monthly work report**: coding work grouped by service.
- Import the existing spreadsheet data (2024, 2025, 2026).

Out of scope for now: export, multiple users, authentication, hosting.

## 2. Conventions

| Topic       | Rule                                                                                  |
|-------------|---------------------------------------------------------------------------------------|
| UI language | English                                                                               |
| Dates (UI)  | `DD.MM.YYYY`; weeks start on Monday                                                   |
| Dates (API) | ISO 8601 `YYYY-MM-DD`                                                                 |
| Times       | 24 h format `HH:MM`                                                                   |
| Durations   | `h:mm` (e.g. `1:30`); task entries in quarter-hour steps (`:00`, `:15`, `:30`, `:45`) |

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
- Coming up in the next 60 days: public holidays, company half days and planned days off (days in a row combined).
- This year: days worked and average, sick days, overtime-off days, coding hours and the top three services.

### 5.1 Week

- Shows the work days of the current week (e.g. Mon–Fri); other days only if they hold data. Prev / next / today
  navigation.
- Per day: day type, start / end / break, worked vs. target, overtime, the task entries and the warning.
- Add, edit and delete days and entries inline; open an entry's history (4.5).
- **Book days off** as a range (from, to, full-day type: PTO, sick, unpaid leave or overtime off; optional note): only
  the work days of the schedule get the type, public holidays and company half days stay automatic. A preview shows
  the days and the PTO used; days that already hold times or entries are listed in a popup to skip them, book them too
  (keeping times and entries) or cancel. Clearing a range is not offered: single days can be deleted.
- Week totals and the overtime balance at the end of the week.

### 5.2 Month report

- **Coding work by service → ticket**: hours plus the entry descriptions. Unassigned entries are listed separately.
- Worked vs. target, overtime for the month, balance at month end.
- PTO, sick and overtime-off days in the month.

### 5.3 Year report

Replaces the spreadsheet dashboard:

- Per year: worked total, target, average per day worked, overtime for the year, balance carried in and out.
- Per month: worked, target, overtime.
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
  the light or dark setting of the system.
- Text contrast is at least 4.5:1 on its background, except the warning highlight color, which is
  only used for large or bold text, borders and icons. A test checks every text color on background, surface and
  its tint, in both themes.
- **Accessibility**: WCAG 2.2 AA (checked with axe-core on all pages, both themes). Links in text are underlined;
  hints and errors describe their field (`aria-describedby`); every field has a visible label; Escape closes inline
  forms, and focus returns to the button that opened them; "Skip to content" is the first link on each page.
  Narrow screens and zoom follow in TASKS.md L.9.

### 5.6 Login

- A user has a username and an e-mail address (both unique, ignoring case), a first name, an optional last name and a
  password (at least 12 characters, stored as a salted scrypt hash). Log in with the username or the e-mail address.
- A login is a session: a random token in an `HttpOnly`, `SameSite=Strict` cookie (`Secure` over HTTPS), stored only as
  a hash. It stays valid for 24 hours since the last activity (renewed at most every 30 minutes); "Log out" ends it,
  a new password ends all other sessions. After 5 failed logins within a minute, logins pause for a minute.
- Every page and the API need a login (pages forward to `/login?next=…`, the API answers 401); `/login`, `/health`,
  the API docs and the static files stay open. A new database creates the first user in the setup, an existing one
  once on `/login`. A command on the computer running the app resets a forgotten password.
- `WORK_TRACKER_AUTH=off` switches the login off for local development. All users share the data (TASKS.md L.8a).

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

- Python 3.15, Falcon (WSGI), spectree + pydantic for validation and OpenAPI docs.
- SQLite file database; storage behind a repository interface so it can be replaced for a
  later AWS Lambda deployment via zappa (SQLite does not persist there).
- Frontend: static HTML / CSS served by the app, TypeScript compiled locally to JavaScript (`npm run build`).
- Runs locally with a single command.
- Tests with pytest; code quality checked with flake8 (radon max CC 6, max line length 127).

## 8. Future ideas

- Export (CSV / spreadsheet format).
- Deployment as AWS Lambda (zappa) with a persistent storage backend and authentication.
- Settings page with overtime balance, PTO years, work schedules and holiday rules is done (TASKS.md, L.1a–L.1c).
- Initial setup of a new database on `/setup` is done (TASKS.md, L.3).
