"""Keys of the items in the one table (SPEC 7.2): partition key `PK`, sort key `SK`.

| PK               | SK                      | Item                                                              |
|------------------|-------------------------|-------------------------------------------------------------------|
| `META`           | `SCHEMA`                | the schema version (`version`)                                    |
| `APP`            | `SETTINGS`              | app-wide settings, e.g. `registration`                            |
| `USERS`          | `USER#<user id>`        | a user's profile, role, password hash and registration `order`    |
| `LOGIN`          | `USERNAME#<lower case>` | the user id of a username, kept unique (also `EMAIL#…`)           |
| `SESSION#<hash>` | `SESSION`               | a session by the hash of its token (time to live `expires_at`)    |
| `ATTEMPTS`       | `AT#<time>#<random>`    | a failed login or registration; `CLEARED`: failed ones up to then |
| `TEAMS`          | `TEAM#<id>`             | a team (`deleted_at` once deleted; `NAME#…` keeps names unique)   |
| `TEAM#<id>`      | `MEMBER#<user id>`      | a current member (team role); also `INVITE#<id>`, team services   |
| `INVITES#<mail>` | `TEAM#<id>`             | an invitation to an e-mail address (lower case), for that user    |
| `USER#<user id>` | e.g. `DAY#2026-10-30`   | a user's records: one partition per user, so only their own data  |

In a user's partition: `SETTINGS` (balance, setup, theme), `SESSION#<hash>` (to end all their sessions),
`SERVICE#<id>` and `ACTIVITY_TYPE#<id>` (names unique by `SERVICE_NAME#…` / `ACTIVITY_TYPE_NAME#<lower case>`),
`TICKET#<key>`, `DAY#<date>`, `ENTRY#<date>#<id>` with `ENTRY_ID#<id>` (its date), `HISTORY#<entry id>#<id>`,
`FLAG#<id>`, `SCHEDULE#<id>` (one per day by `SCHEDULE_FROM#<date>`), `PTO#<year>`, `MEMBERSHIP#<id>` (the teams they
were in) and `VIEW#<time>#<id>` (who looked at their reports). Ids are UUIDv7s (SPEC 7.2a), so sort keys holding them
keep the order of creation.
"""

META, SCHEMA = 'META', 'SCHEMA'
APP, SETTINGS = 'APP', 'SETTINGS'
USERS, LOGIN, ATTEMPTS = 'USERS', 'LOGIN', 'ATTEMPTS'


def user_partition(user_id: str) -> str:
    """The partition of a user's own records."""
    return f'USER#{user_id}'
