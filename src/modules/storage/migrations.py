"""Schema migrations. Each script runs once, in order; the database tracks the count in PRAGMA user_version.

Never change a released script: add a new one instead.
"""

MIGRATIONS = (
    # 1: initial schema and seed data
    """
    CREATE TABLE settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );

    CREATE TABLE pto_allowances (
        year INTEGER PRIMARY KEY,
        days TEXT    NOT NULL
    );

    CREATE TABLE services (
        id         INTEGER PRIMARY KEY,
        short_name TEXT NOT NULL UNIQUE COLLATE NOCASE,
        name       TEXT NOT NULL DEFAULT ''
    );

    CREATE TABLE activity_types (
        id   INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE COLLATE NOCASE
    );

    CREATE TABLE tickets (
        key        TEXT PRIMARY KEY,
        service_id INTEGER REFERENCES services (id) ON DELETE SET NULL
    );

    CREATE TABLE days (
        date          TEXT PRIMARY KEY,
        day_type      TEXT,
        start_time    INTEGER,
        end_time      INTEGER,
        break_minutes INTEGER,
        note          TEXT NOT NULL DEFAULT ''
    );

    CREATE TABLE entries (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,  -- ids are never reused: history outlives entries
        date             TEXT    NOT NULL,
        kind             TEXT    NOT NULL CHECK (kind IN ('ticket', 'activity')),
        ticket_key       TEXT    REFERENCES tickets (key) ON UPDATE CASCADE,
        activity_type_id INTEGER REFERENCES activity_types (id),
        duration         INTEGER NOT NULL,
        text             TEXT    NOT NULL DEFAULT '',
        coding           INTEGER NOT NULL DEFAULT 0,
        CHECK (
            (kind = 'ticket' AND activity_type_id IS NULL)
            OR (kind = 'activity' AND activity_type_id IS NOT NULL AND ticket_key IS NULL)
        )
    );
    CREATE INDEX entries_by_date ON entries (date);

    CREATE TABLE entry_history (
        id         INTEGER PRIMARY KEY,
        entry_id   INTEGER NOT NULL,  -- no foreign key: the history of deleted entries is kept
        changed_at TEXT    NOT NULL,
        action     TEXT    NOT NULL,
        changes    TEXT    NOT NULL DEFAULT '{}',  -- JSON: {"field": [old, new]}
        detail     TEXT    NOT NULL DEFAULT ''     -- e.g. the original spreadsheet line
    );
    CREATE INDEX entry_history_by_entry ON entry_history (entry_id);

    CREATE TABLE review_flags (
        id       INTEGER PRIMARY KEY,
        entry_id INTEGER REFERENCES entries (id) ON DELETE CASCADE,
        date     TEXT,
        reason   TEXT NOT NULL,
        detail   TEXT NOT NULL DEFAULT '',
        CHECK ((entry_id IS NULL) != (date IS NULL))
    );

    INSERT INTO settings (key, value) VALUES ('balance_start', '2024-06-01'), ('opening_balance', '0');
    INSERT INTO pto_allowances (year, days) VALUES (2024, '18'), (2025, '30');
    INSERT INTO services (short_name, name) VALUES
        ('O365', 'office-integration-service'),
        ('MSB', 'microsoft-bookings-service'),
        ('ImmoDrop', ''),
        ('HiS', 'history-service'),
        ('TTS', 'text-transformation-service');
    INSERT INTO activity_types (name) VALUES ('Tool Management'), ('Meeting'), ('Travel'), ('Other');
    """,
    # 2: 2024 pro rata (30 × 7/12), one extra PTO day granted in 2025 and 2026 (not permanent: 30 again from 2027)
    """
    INSERT INTO pto_allowances (year, days) VALUES (2024, '17.5'), (2025, '31'), (2026, '31'), (2027, '30')
        ON CONFLICT (year) DO UPDATE SET days = excluded.days;
    """,
    # 3: PTO years as data: allowance, extra days and an optional fixed carry-over; no "valid from that year on"
    """
    CREATE TABLE pto_years (
        year         INTEGER PRIMARY KEY,
        allowance    TEXT NOT NULL,
        extra_days   TEXT NOT NULL DEFAULT '0',
        carried_over TEXT,  -- NULL: the remainder of the year before
        note         TEXT NOT NULL DEFAULT ''
    );
    INSERT INTO pto_years (year, allowance) SELECT year, days FROM pto_allowances;
    DROP TABLE pto_allowances;
    """,
    # 4: work schedules valid from a date; the first one keeps the former fixed rule (40 h, Monday to Friday)
    """
    CREATE TABLE work_schedules (
        id             INTEGER PRIMARY KEY,
        valid_from     TEXT    NOT NULL UNIQUE,
        weekly_minutes INTEGER NOT NULL CHECK (weekly_minutes BETWEEN 0 AND 10080),
        work_days      TEXT    NOT NULL  -- ISO weekdays, e.g. '1,2,3,4,5' for Monday to Friday
    );
    INSERT INTO work_schedules (valid_from, weekly_minutes, work_days)
        SELECT value, 2400, '1,2,3,4,5' FROM settings WHERE key = 'balance_start';
    """,
    # 5: holiday rules per work schedule; existing schedules keep the former fixed rule (Berlin, company half days)
    """
    ALTER TABLE work_schedules ADD COLUMN state TEXT NOT NULL DEFAULT 'BE';
    ALTER TABLE work_schedules
        ADD COLUMN company_half_days INTEGER NOT NULL DEFAULT 1 CHECK (company_half_days IN (0, 1));
    """,
    # 6: initial setup: a database holding days or entries counts as set up and stays as it is; an empty one starts
    # clean (without the original setup's PTO years and services) and is set up on /setup
    """
    INSERT INTO settings (key, value)
        SELECT 'setup_done', CASE WHEN EXISTS (SELECT 1 FROM days) OR EXISTS (SELECT 1 FROM entries) THEN '1' ELSE '0' END;
    DELETE FROM pto_years WHERE (SELECT value FROM settings WHERE key = 'setup_done') = '0';
    DELETE FROM services WHERE (SELECT value FROM settings WHERE key = 'setup_done') = '0';
    """,
    # 7: users who log in, their sessions (only a hash of the token) and failed logins (to pause guessing)
    """
    CREATE TABLE users (
        id            INTEGER PRIMARY KEY,
        username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
        email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
        first_name    TEXT NOT NULL,
        last_name     TEXT NOT NULL DEFAULT '',
        password_hash TEXT NOT NULL
    );

    CREATE TABLE sessions (
        token_hash TEXT    PRIMARY KEY,  -- SHA-256 of the cookie's token
        user_id    INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        expires_at TEXT    NOT NULL,
        renewed_at TEXT    NOT NULL
    );

    CREATE TABLE failed_logins (
        at TEXT NOT NULL
    );
    """,
    # 8: data per user (TASKS.md L.8a.1); all existing records go to the only user, who becomes admin. Without a user,
    # they get user 0 (no owner yet) until the first user is created. `settings` stays for app-wide settings.
    """
    CREATE TEMP TABLE owner AS SELECT COALESCE(MIN(id), 0) AS id FROM users;
    CREATE TEMP TABLE entry_sequence AS SELECT COALESCE(MAX(seq), 0) AS seq FROM sqlite_sequence WHERE name = 'entries';

    ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'team_admin', 'user'));
    UPDATE users SET role = 'admin' WHERE id = (SELECT id FROM owner);

    CREATE TABLE user_settings (
        user_id INTEGER NOT NULL,  -- 0: no owner yet (also in the tables below)
        key     TEXT    NOT NULL,
        value   TEXT    NOT NULL,
        PRIMARY KEY (user_id, key)
    );
    INSERT INTO user_settings SELECT (SELECT id FROM owner), key, value FROM settings;
    DELETE FROM settings;

    CREATE TABLE new_services (
        id         INTEGER PRIMARY KEY,
        user_id    INTEGER NOT NULL,
        short_name TEXT    NOT NULL COLLATE NOCASE,
        name       TEXT    NOT NULL DEFAULT '',
        UNIQUE (user_id, short_name)
    );
    INSERT INTO new_services SELECT id, (SELECT id FROM owner), short_name, name FROM services;

    CREATE TABLE new_activity_types (
        id      INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL,
        name    TEXT    NOT NULL COLLATE NOCASE,
        UNIQUE (user_id, name)
    );
    INSERT INTO new_activity_types SELECT id, (SELECT id FROM owner), name FROM activity_types;

    CREATE TABLE new_tickets (
        user_id    INTEGER NOT NULL,
        key        TEXT    NOT NULL,
        service_id INTEGER REFERENCES services (id) ON DELETE SET NULL,
        PRIMARY KEY (user_id, key)
    );
    INSERT INTO new_tickets SELECT (SELECT id FROM owner), key, service_id FROM tickets;

    CREATE TABLE new_days (
        user_id       INTEGER NOT NULL,
        date          TEXT    NOT NULL,
        day_type      TEXT,
        start_time    INTEGER,
        end_time      INTEGER,
        break_minutes INTEGER,
        note          TEXT    NOT NULL DEFAULT '',
        PRIMARY KEY (user_id, date)
    );
    INSERT INTO new_days SELECT (SELECT id FROM owner), date, day_type, start_time, end_time, break_minutes, note FROM days;

    CREATE TABLE new_entries (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,  -- ids are never reused: history outlives entries
        user_id          INTEGER NOT NULL,
        date             TEXT    NOT NULL,
        kind             TEXT    NOT NULL CHECK (kind IN ('ticket', 'activity')),
        ticket_key       TEXT,
        activity_type_id INTEGER REFERENCES activity_types (id),
        duration         INTEGER NOT NULL,
        text             TEXT    NOT NULL DEFAULT '',
        coding           INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (user_id, ticket_key) REFERENCES tickets (user_id, key) ON UPDATE CASCADE,
        CHECK (
            (kind = 'ticket' AND activity_type_id IS NULL)
            OR (kind = 'activity' AND activity_type_id IS NOT NULL AND ticket_key IS NULL)
        )
    );
    INSERT INTO new_entries SELECT id, (SELECT id FROM owner), date, kind, ticket_key, activity_type_id, duration, text, coding
        FROM entries;

    CREATE TABLE new_pto_years (
        user_id      INTEGER NOT NULL,
        year         INTEGER NOT NULL,
        allowance    TEXT    NOT NULL,
        extra_days   TEXT    NOT NULL DEFAULT '0',
        carried_over TEXT,  -- NULL: the remainder of the year before
        note         TEXT    NOT NULL DEFAULT '',
        PRIMARY KEY (user_id, year)
    );
    INSERT INTO new_pto_years SELECT (SELECT id FROM owner), year, allowance, extra_days, carried_over, note FROM pto_years;

    CREATE TABLE new_work_schedules (
        id                INTEGER PRIMARY KEY,
        user_id           INTEGER NOT NULL,
        valid_from        TEXT    NOT NULL,
        weekly_minutes    INTEGER NOT NULL CHECK (weekly_minutes BETWEEN 0 AND 10080),
        work_days         TEXT    NOT NULL,  -- ISO weekdays, e.g. '1,2,3,4,5' for Monday to Friday
        state             TEXT    NOT NULL DEFAULT 'BE',
        company_half_days INTEGER NOT NULL DEFAULT 1 CHECK (company_half_days IN (0, 1)),
        UNIQUE (user_id, valid_from)
    );
    INSERT INTO new_work_schedules
        SELECT id, (SELECT id FROM owner), valid_from, weekly_minutes, work_days, state, company_half_days FROM work_schedules;

    ALTER TABLE entry_history ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0;
    UPDATE entry_history SET user_id = (SELECT id FROM owner);
    ALTER TABLE review_flags ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0;
    UPDATE review_flags SET user_id = (SELECT id FROM owner);

    DROP TABLE entries;
    DROP TABLE tickets;
    DROP TABLE days;
    DROP TABLE services;
    DROP TABLE activity_types;
    DROP TABLE pto_years;
    DROP TABLE work_schedules;
    ALTER TABLE new_services RENAME TO services;
    ALTER TABLE new_activity_types RENAME TO activity_types;
    ALTER TABLE new_tickets RENAME TO tickets;
    ALTER TABLE new_days RENAME TO days;
    ALTER TABLE new_entries RENAME TO entries;
    ALTER TABLE new_pto_years RENAME TO pto_years;
    ALTER TABLE new_work_schedules RENAME TO work_schedules;
    CREATE INDEX entries_by_user_and_date ON entries (user_id, date);
    CREATE INDEX review_flags_by_user ON review_flags (user_id);

    DELETE FROM sqlite_sequence WHERE name = 'entries';
    INSERT INTO sqlite_sequence (name, seq)
        SELECT 'entries', MAX((SELECT seq FROM entry_sequence), COALESCE((SELECT MAX(id) FROM entries), 0));
    DROP TABLE temp.owner;
    DROP TABLE temp.entry_sequence;
    """,
    # 9: user ids become random UUIDs (version 4, as text); records without an owner get the nil UUID instead of 0
    """
    CREATE TEMP TABLE user_ids (old INTEGER PRIMARY KEY, new TEXT NOT NULL);
    INSERT INTO user_ids VALUES (0, '00000000-0000-0000-0000-000000000000');
    INSERT INTO user_ids SELECT id, lower(
        hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' || substr(hex(randomblob(2)), 2) || '-'
        || substr('89AB', 1 + abs(random()) % 4, 1) || substr(hex(randomblob(2)), 2) || '-' || hex(randomblob(6))
    ) FROM users ORDER BY id;
    CREATE TEMP TABLE entry_sequence AS SELECT COALESCE(MAX(seq), 0) AS seq FROM sqlite_sequence WHERE name = 'entries';

    CREATE TABLE new_users (
        id            TEXT PRIMARY KEY,  -- random UUID
        username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
        email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
        first_name    TEXT NOT NULL,
        last_name     TEXT NOT NULL DEFAULT '',
        password_hash TEXT NOT NULL,
        role          TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'team_admin', 'user'))
    );
    INSERT INTO new_users SELECT (SELECT new FROM user_ids WHERE old = id), username, email, first_name, last_name,
        password_hash, role FROM users ORDER BY id;

    CREATE TABLE new_sessions (
        token_hash TEXT PRIMARY KEY,  -- SHA-256 of the cookie's token
        user_id    TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        expires_at TEXT NOT NULL,
        renewed_at TEXT NOT NULL
    );
    INSERT INTO new_sessions SELECT token_hash, (SELECT new FROM user_ids WHERE old = user_id), expires_at, renewed_at
        FROM sessions;

    CREATE TABLE new_user_settings (
        user_id TEXT NOT NULL,  -- nil UUID: no owner yet (also in the tables below)
        key     TEXT NOT NULL,
        value   TEXT NOT NULL,
        PRIMARY KEY (user_id, key)
    );
    INSERT INTO new_user_settings SELECT (SELECT new FROM user_ids WHERE old = user_id), key, value FROM user_settings;

    CREATE TABLE new_services (
        id         INTEGER PRIMARY KEY,
        user_id    TEXT    NOT NULL,
        short_name TEXT    NOT NULL COLLATE NOCASE,
        name       TEXT    NOT NULL DEFAULT '',
        UNIQUE (user_id, short_name)
    );
    INSERT INTO new_services SELECT id, (SELECT new FROM user_ids WHERE old = user_id), short_name, name FROM services;

    CREATE TABLE new_activity_types (
        id      INTEGER PRIMARY KEY,
        user_id TEXT    NOT NULL,
        name    TEXT    NOT NULL COLLATE NOCASE,
        UNIQUE (user_id, name)
    );
    INSERT INTO new_activity_types SELECT id, (SELECT new FROM user_ids WHERE old = user_id), name FROM activity_types;

    CREATE TABLE new_tickets (
        user_id    TEXT    NOT NULL,
        key        TEXT    NOT NULL,
        service_id INTEGER REFERENCES services (id) ON DELETE SET NULL,
        PRIMARY KEY (user_id, key)
    );
    INSERT INTO new_tickets SELECT (SELECT new FROM user_ids WHERE old = user_id), key, service_id FROM tickets;

    CREATE TABLE new_days (
        user_id       TEXT    NOT NULL,
        date          TEXT    NOT NULL,
        day_type      TEXT,
        start_time    INTEGER,
        end_time      INTEGER,
        break_minutes INTEGER,
        note          TEXT    NOT NULL DEFAULT '',
        PRIMARY KEY (user_id, date)
    );
    INSERT INTO new_days SELECT (SELECT new FROM user_ids WHERE old = user_id), date, day_type, start_time, end_time,
        break_minutes, note FROM days;

    CREATE TABLE new_entries (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,  -- ids are never reused: history outlives entries
        user_id          TEXT    NOT NULL,
        date             TEXT    NOT NULL,
        kind             TEXT    NOT NULL CHECK (kind IN ('ticket', 'activity')),
        ticket_key       TEXT,
        activity_type_id INTEGER REFERENCES activity_types (id),
        duration         INTEGER NOT NULL,
        text             TEXT    NOT NULL DEFAULT '',
        coding           INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (user_id, ticket_key) REFERENCES tickets (user_id, key) ON UPDATE CASCADE,
        CHECK (
            (kind = 'ticket' AND activity_type_id IS NULL)
            OR (kind = 'activity' AND activity_type_id IS NOT NULL AND ticket_key IS NULL)
        )
    );
    INSERT INTO new_entries SELECT id, (SELECT new FROM user_ids WHERE old = user_id), date, kind, ticket_key,
        activity_type_id, duration, text, coding FROM entries;

    CREATE TABLE new_entry_history (
        id         INTEGER PRIMARY KEY,
        user_id    TEXT    NOT NULL,
        entry_id   INTEGER NOT NULL,  -- no foreign key: the history of deleted entries is kept
        changed_at TEXT    NOT NULL,
        action     TEXT    NOT NULL,
        changes    TEXT    NOT NULL DEFAULT '{}',  -- JSON: {"field": [old, new]}
        detail     TEXT    NOT NULL DEFAULT ''     -- e.g. the original spreadsheet line
    );
    INSERT INTO new_entry_history SELECT id, (SELECT new FROM user_ids WHERE old = user_id), entry_id, changed_at, action,
        changes, detail FROM entry_history;

    CREATE TABLE new_review_flags (
        id       INTEGER PRIMARY KEY,
        user_id  TEXT    NOT NULL,
        entry_id INTEGER REFERENCES entries (id) ON DELETE CASCADE,
        date     TEXT,
        reason   TEXT    NOT NULL,
        detail   TEXT    NOT NULL DEFAULT '',
        CHECK ((entry_id IS NULL) != (date IS NULL))
    );
    INSERT INTO new_review_flags SELECT id, (SELECT new FROM user_ids WHERE old = user_id), entry_id, date, reason, detail
        FROM review_flags;

    CREATE TABLE new_pto_years (
        user_id      TEXT    NOT NULL,
        year         INTEGER NOT NULL,
        allowance    TEXT    NOT NULL,
        extra_days   TEXT    NOT NULL DEFAULT '0',
        carried_over TEXT,  -- NULL: the remainder of the year before
        note         TEXT    NOT NULL DEFAULT '',
        PRIMARY KEY (user_id, year)
    );
    INSERT INTO new_pto_years SELECT (SELECT new FROM user_ids WHERE old = user_id), year, allowance, extra_days,
        carried_over, note FROM pto_years;

    CREATE TABLE new_work_schedules (
        id                INTEGER PRIMARY KEY,
        user_id           TEXT    NOT NULL,
        valid_from        TEXT    NOT NULL,
        weekly_minutes    INTEGER NOT NULL CHECK (weekly_minutes BETWEEN 0 AND 10080),
        work_days         TEXT    NOT NULL,  -- ISO weekdays, e.g. '1,2,3,4,5' for Monday to Friday
        state             TEXT    NOT NULL DEFAULT 'BE',
        company_half_days INTEGER NOT NULL DEFAULT 1 CHECK (company_half_days IN (0, 1)),
        UNIQUE (user_id, valid_from)
    );
    INSERT INTO new_work_schedules SELECT id, (SELECT new FROM user_ids WHERE old = user_id), valid_from, weekly_minutes,
        work_days, state, company_half_days FROM work_schedules;

    DROP TABLE sessions;
    DROP TABLE users;
    DROP TABLE user_settings;
    DROP TABLE review_flags;
    DROP TABLE entry_history;
    DROP TABLE entries;
    DROP TABLE tickets;
    DROP TABLE days;
    DROP TABLE services;
    DROP TABLE activity_types;
    DROP TABLE pto_years;
    DROP TABLE work_schedules;
    ALTER TABLE new_users RENAME TO users;
    ALTER TABLE new_sessions RENAME TO sessions;
    ALTER TABLE new_user_settings RENAME TO user_settings;
    ALTER TABLE new_services RENAME TO services;
    ALTER TABLE new_activity_types RENAME TO activity_types;
    ALTER TABLE new_tickets RENAME TO tickets;
    ALTER TABLE new_days RENAME TO days;
    ALTER TABLE new_entries RENAME TO entries;
    ALTER TABLE new_entry_history RENAME TO entry_history;
    ALTER TABLE new_review_flags RENAME TO review_flags;
    ALTER TABLE new_pto_years RENAME TO pto_years;
    ALTER TABLE new_work_schedules RENAME TO work_schedules;
    CREATE INDEX entries_by_user_and_date ON entries (user_id, date);
    CREATE INDEX entry_history_by_entry ON entry_history (entry_id);
    CREATE INDEX review_flags_by_user ON review_flags (user_id);

    DELETE FROM sqlite_sequence WHERE name = 'entries';
    INSERT INTO sqlite_sequence (name, seq)
        SELECT 'entries', MAX((SELECT seq FROM entry_sequence), COALESCE((SELECT MAX(id) FROM entries), 0));
    DROP TABLE temp.user_ids;
    DROP TABLE temp.entry_sequence;
    """,
    # 10: registration and user administration (TASKS.md L.8a.2): users can be deactivated and show when they registered
    # and last logged in; registrations count towards the pause after failed logins
    """
    ALTER TABLE users ADD COLUMN active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1));
    ALTER TABLE users ADD COLUMN registered_at TEXT;  -- NULL: registered before it was recorded
    ALTER TABLE users ADD COLUMN last_login_at TEXT;
    ALTER TABLE failed_logins RENAME TO login_attempts;
    ALTER TABLE login_attempts ADD COLUMN kind TEXT NOT NULL DEFAULT 'failed_login'
        CHECK (kind IN ('failed_login', 'registration'));
    """,
    # 11: teams (TASKS.md L.8a.3): memberships kept as history, invitations by e-mail address, and services of a team
    """
    CREATE TABLE teams (
        id         INTEGER PRIMARY KEY,
        name       TEXT    NOT NULL COLLATE NOCASE,
        deleted_at TEXT  -- deleted teams stay for the membership history
    );
    CREATE UNIQUE INDEX team_names ON teams (name) WHERE deleted_at IS NULL;

    CREATE TABLE team_memberships (
        id        INTEGER PRIMARY KEY,
        team_id   INTEGER NOT NULL REFERENCES teams (id),
        user_id   TEXT    NOT NULL REFERENCES users (id),
        joined_on TEXT    NOT NULL,
        left_on   TEXT,  -- the first day no longer in the team; NULL: still a member
        CHECK (left_on IS NULL OR left_on >= joined_on)
    );
    CREATE UNIQUE INDEX one_team_per_user ON team_memberships (user_id) WHERE left_on IS NULL;
    CREATE INDEX team_memberships_by_team ON team_memberships (team_id);

    CREATE TABLE team_invitations (
        id         INTEGER PRIMARY KEY,
        team_id    INTEGER NOT NULL REFERENCES teams (id) ON DELETE CASCADE,
        email      TEXT    NOT NULL COLLATE NOCASE,  -- no user id: an invitation does not tell whether the user exists
        invited_by TEXT    NOT NULL REFERENCES users (id),
        invited_at TEXT    NOT NULL,
        UNIQUE (team_id, email)
    );

    CREATE TABLE new_services (
        id         INTEGER PRIMARY KEY,
        user_id    TEXT,     -- a personal service
        team_id    INTEGER REFERENCES teams (id),  -- or a service of a team
        short_name TEXT    NOT NULL COLLATE NOCASE,
        name       TEXT    NOT NULL DEFAULT '',
        CHECK ((user_id IS NULL) != (team_id IS NULL)),
        UNIQUE (user_id, short_name),
        UNIQUE (team_id, short_name)
    );
    INSERT INTO new_services (id, user_id, short_name, name) SELECT id, user_id, short_name, name FROM services;
    DROP TABLE services;
    ALTER TABLE new_services RENAME TO services;
    """,
    # 12: team view (TASKS.md L.10): which team admin looked at which report of a member, shown to the member
    """
    CREATE TABLE report_views (
        id        INTEGER PRIMARY KEY,
        member_id TEXT    NOT NULL REFERENCES users (id),
        viewer_id TEXT    NOT NULL REFERENCES users (id),
        report    TEXT    NOT NULL CHECK (report IN ('dashboard', 'week', 'month', 'year')),
        period    TEXT    NOT NULL DEFAULT '',  -- e.g. 2026-W44, 2026-10, 2026; empty for the dashboard
        viewed_at TEXT    NOT NULL
    );
    CREATE INDEX report_views_by_member ON report_views (member_id, viewed_at);
    """,
)
