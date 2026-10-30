"""Keys of the items in the one table (SPEC 7.2): partition key `PK`, sort key `SK`.

| PK               | SK                      | Item                                                              |
|------------------|-------------------------|-------------------------------------------------------------------|
| `META`           | `SCHEMA`                | the schema version (`version`)                                    |
| `COUNTER`        | the kind, e.g. `entry`  | the last id given to that kind of record (`value`), never reused  |
| `APP`            | `SETTINGS`              | app-wide settings, e.g. `registration`                            |
| `USER#<user id>` | e.g. `DAY#2026-10-30`   | a user's records: one partition per user, so only their own data  |
"""

META, SCHEMA = 'META', 'SCHEMA'
COUNTER = 'COUNTER'
APP, SETTINGS = 'APP', 'SETTINGS'
