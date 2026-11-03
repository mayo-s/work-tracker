"""Keys of the items in the one table (SPEC 7.2): partition key `PK`, sort key `SK`.

| PK               | SK                      | Item                                                              |
|------------------|-------------------------|-------------------------------------------------------------------|
| `META`           | `SCHEMA`                | the schema version (`version`)                                    |
| `APP`            | `SETTINGS`              | app-wide settings, e.g. `registration`                            |
| `APP`            | `TOKEN#<hash>`          | a setup token used once (SHA-256), refused afterwards             |
| `USERS`          | `USER#<user id>`        | a user's profile, role, password hash and registration `order`    |
| `USERS`          | `ROOT`                  | the user id of root, kept unique: there is only one               |
| `LOGIN`          | `USERNAME#<lower case>` | the user id of a username, kept unique (also `EMAIL#…`)           |
| `SESSION#<hash>` | `SESSION`               | a session by the hash of its token (time to live `expires_at`)    |
| `ATTEMPTS`       | `AT#<time>#<random>`    | a failed login or registration; `CLEARED`: failed ones up to then |
| `TEAMS`          | `TEAM#<id>`             | a team (`deleted_at` once deleted; `NAME#…` keeps names unique)   |
| `TEAM#<id>`      | `MEMBER#<user id>`      | a current member (team role); also `INVITE#<id>`, team services   |
| `TEAM#<id>`      | `STAY#<membership id>`  | every stay in the team, current or former (for its auditors)      |
| `TEAM#<id>`      | `AUDITOR#<user id>`     | an auditor of the team (also as `AUDITS#<team id>` in theirs)     |
| `INVITES#<mail>` | `TEAM#<id>`             | an invitation to an e-mail address (lower case), for that user    |
| `AUDIT`          | `AT#<time>#<id>`        | an audit log entry (one about a user also as `AUDIT#…` in theirs) |
| `USER#<user id>` | e.g. `DAY#2026-10-30`   | a user's records: one partition per user, so only their own data  |

In a user's partition: `SETTINGS` (balance, setup, theme), `SESSION#<hash>` (to end all their sessions),
`SERVICE#<id>` and `ACTIVITY_TYPE#<id>` (names unique by `SERVICE_NAME#…` / `ACTIVITY_TYPE_NAME#<lower case>`),
`TICKET#<key>`, `DAY#<date>`, `ENTRY#<date>#<id>` with `ENTRY_ID#<id>` (its date), `HISTORY#<entry id>#<id>`,
`FLAG#<id>`, `SCHEDULE#<id>` (one per day by `SCHEDULE_FROM#<date>`), `PTO#<year>`, `MEMBERSHIP#<id>` (the teams they
were in), `VIEW#<time>#<id>` (who looked at their reports), `AUDIT#<time>#<id>` (changes to their account) and
`BROWSER#<hash>` (browsers remembered for two-factor login, time to live). Ids
are UUIDv7s (SPEC 7.2a), so sort keys holding them keep the order of creation.
"""

META, SCHEMA = 'META', 'SCHEMA'
APP, SETTINGS = 'APP', 'SETTINGS'
USERS, ROOT, LOGIN, ATTEMPTS = 'USERS', 'ROOT', 'LOGIN', 'ATTEMPTS'


def user_partition(user_id: str) -> str:
    """The partition of a user's own records."""
    return f'USER#{user_id}'
