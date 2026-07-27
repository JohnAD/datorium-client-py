# Protocol mapping

API prefix: `/datoriumdb/v1`

| Method | Path | Auth | Client API |
|--------|------|------|------------|
| GET | `/health` | no | `health` |
| GET | `/ready` | no | `ready` |
| GET | `/establish` | Bearer | `establish` |
| GET | `/schema/{c}/{v}` | Bearer | `schema` |
| POST | `/command` | Bearer | CRUD / search / `command` |

Command body: `text/plain; charset=utf-8`

```
{word} {target} {parm} {strict-json-object}
```

Application outcomes use HTTP 200 envelopes (`ok` / `errors`). Non-2xx are transport failures.

Out of scope: `/datoriumdb/v1/sys/*`, machine-token bootstrap.
