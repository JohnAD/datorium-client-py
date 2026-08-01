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

`wrongMachine` refusals echo command context (`command`, `collection`, `id` or search identity) and may include diagnostic `configVersion` (what that refusing server believes). They do **not** include retry-target hints (`correctServer`, `baseURL`, `shardSlot`). Clients always re-fetch establishment and recompute the next hop locally.

Out of scope: `/datoriumdb/v1/sys/*`, machine-token bootstrap.
