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
)
