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
)
