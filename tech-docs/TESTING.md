# Testing

## Layers

| Layer | Location | CI |
|-------|----------|----|
| Unit | `tests/unit/` (+ offline fixture parse under `tests/integration/todo/`) | every PR |
| Contract | `tests/contract/` | every PR |
| Integration | `tests/integration/test_todo_*.py` | opt-in via `./start_integration_test.sh` |

## Running

```bash
uv sync --extra dev   # or: pip install -e '.[dev]'
uv run pytest tests/unit tests/contract tests/integration/todo
./start_integration_test.sh
```

Default CI runs unit + contract only. The Compose demo is **opt-in** and not part of plain `pytest` without env vars.

Requires a sibling [`datoriumdb`](https://github.com/JohnAD/datoriumdb) checkout at **v0.0.5+**, or set `DATORIUMDB_SRC`.

## Dev token minting

JWT minting for local integration lives under `tests/integration/mint_token.py` and is **not** part of the public runtime API. The harness calls it as a CLI:

```bash
.venv/bin/python tests/integration/mint_token.py \
  --auth tests/integration/todo/fixtures/server1/.config/__auth.json \
  --key tests/integration/todo/secrets/dev-signing-key.pem \
  --subject todo-integration
```

## Todo integration story

`./start_integration_test.sh` brings up a disposable two-shard DatoriumDB
cluster, runs the canonical live tests through this client library, then
tears everything down. Step titles below are printed live as
`[STEP_NAME]` so you can follow progress in the terminal.

Canonical live tests:

| File | Coverage |
|------|----------|
| `tests/integration/test_todo_integration.py` | Full sync raw + typed Todo story (refs, front-page, cache, search, dotted IDs) |
| `tests/integration/test_todo_async_integration.py` | Focused `AsyncClient` / `bind_async` typed CRUD |

Offline fixture validation (no Docker): `tests/integration/todo/test_fixtures.py`.

### Harness (`start_integration_test.sh`)

| Step | What happens |
|------|----------------|
| `CHECK_PREFLIGHT` | Verifies `docker`, `docker compose`, `curl`, Docker daemon access, and Python deps. Resolves `DATORIUMDB_SRC` (default: sibling `../datoriumdb`) and checks that source includes recursive `FindRefFields` (`collectRefFields`). Reports the checked-out datoriumdb revision. |
| `COMPOSE_UP` | Builds image `datoriumdb:local` from that source and starts a unique Compose project with **server1** (`00-7F`) and **server2** (`80-FF`). |
| `WAIT_CLUSTER` | Polls `GET /datoriumdb/v1/health` on both host ports (`18081` / `18082`) and `GET /datoriumdb/v1/ready` on server1. |
| `MINT_TOKEN` | Signs a short-lived client JWT (`datoriumdb.kind=client`, active `kid`). |
| `RUN_SCENARIO` | Runs the live Todo pytest files with `DATORIUM_TOKEN` and host base URLs (Docker-internal URLs rewritten). |
| `SNAPSHOT_DBS` | Before teardown, replaces `tests/integration/todo/analysis/server{1,2}/` with each container's `/db/` tree and writes `MANIFEST.txt`. |
| `COMPOSE_DOWN` | Always runs: `docker compose down -v --remove-orphans`. |

### Post-run DB analysis

```text
tests/integration/todo/analysis/
  MANIFEST.txt          # project, timestamps, URLs, exit code
  server1/              # copy of server1 container /db
  server2/              # copy of server2 container /db
```

Browse with normal tools:

```bash
ls tests/integration/todo/analysis/server1
find tests/integration/todo/analysis/server1 -type f | head
```

Typical contents under each `serverN/`: `.config/`, collection document trees, `.search/` precompiled results, and cache / pending work-item directories.

### Scenario (`test_todo_integration.py`)

The establishment starts **empty** (schemas and search definitions only). The test picks deterministic document IDs that land in both shard ranges.

| Step | What happens |
|------|----------------|
| `WAIT_READY` | Polls readiness until server1 reports `ready: true`. |
| `ESTABLISH` | Catalog-checked establish for Users / TodoLists / Todos. |
| `BIND_TYPED` | Bind typed collection clients. |
| `PICK_IDS` | Five IDs across low + high shards. |
| `CREATING_USERS_RAW` / `CREATING_USERS_TYPED` | Ada (raw) + Grace (typed). |
| `CREATING_LIST_TYPED` | TodoList with live `@` + cached `@@` owner refs. |
| `LINK_LIST_TO_USER_RAW` | Append cached TodoList ref onto Grace’s `todoLists`. |
| `READ_USER_FRONT_PAGE` / `WAIT_FRONT_PAGE_UPDATE` | Front-page cache summaries. |
| `PATCH_LIST_TITLE_TYPED` | Typed patch-from-changes. |
| `RESOLVE_LIVE_REF` / `READ_CACHED_REF` / `PATCH_CACHED_TARGET_TYPED` / `WAIT_CACHE_UPDATE` | Live + cached ref story. |
| `CREATING_TODO_RAW` / `PATCHING_TODO_RAW` | Raw Todo CRUD; asserts `version_before` / `version`. |
| `WAIT_SEARCH` | `Todos.byStatus` until match appears. |
| `DELETING_TODO_RAW` / `TYPED_TODO_CRUD` | Delete + typed create/get/patch/delete. |
| `DOTTED_ID_CRUD` | Create/read/delete a `prefix.settings` document ID. |
| `PASSED` | Sync scenario finished. |

Cache-update note: datoriumdb completes pending cache work as a no-op when the
read member has no stub file yet. Seed with a referring `cacheSummaries` read
before patching the cached target.
