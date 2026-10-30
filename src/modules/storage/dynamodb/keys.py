"""Keys of the items in the one table (SPEC 7.2): partition key `PK`, sort key `SK`.

| PK               | SK                      | Item                                                              |
|------------------|-------------------------|-------------------------------------------------------------------|
| `META`           | `SCHEMA`                | the schema version (`version`)                                    |
| `COUNTER`        | the kind, e.g. `entry`  | the last id given to that kind of record (`value`), never reused  |
| `APP`            | `SETTINGS`              | app-wide settings, e.g. `registration`                            |
| `USERS`          | `USER#<user id>`        | a user's profile, role, password hash and registration `number`   |
| `LOGIN`          | `USERNAME#<lower case>` | the user id of a username, kept unique (also `EMAIL#…`)           |
| `SESSION#<hash>` | `SESSION`               | a session by the hash of its token (time to live `expires_at`)    |
| `ATTEMPTS`       | `AT#<time>#<random>`    | a failed login or registration; `CLEARED`: failed ones up to then |
| `USER#<user id>` | e.g. `DAY#2026-10-30`   | a user's records: one partition per user, so only their own data  |

In a user's partition: `SETTINGS` (balance, setup, theme), `SESSION#<hash>` (to end all their sessions) and
`ACTIVITY_TYPE#<id>`.
"""

META, SCHEMA = 'META', 'SCHEMA'
COUNTER = 'COUNTER'
APP, SETTINGS = 'APP', 'SETTINGS'
USERS, LOGIN, ATTEMPTS = 'USERS', 'LOGIN', 'ATTEMPTS'


def user_partition(user_id: str) -> str:
    """The partition of a user's own records."""
    return f'USER#{user_id}'
