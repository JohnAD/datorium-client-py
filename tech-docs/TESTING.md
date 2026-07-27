# Testing

## Layers

| Layer | Location | CI |
|-------|----------|----|
| Unit | `tests/unit/` | every PR |
| Contract | `tests/contract/` | every PR |
| Integration | `tests/integration/` | opt-in via `./start_integration_test.sh` |

## Running

```bash
uv sync --extra dev   # or: pip install -e '.[dev]'
uv run pytest tests/unit tests/contract
./start_integration_test.sh
```

Default CI runs unit + contract only. The Compose demo is **opt-in** and not part of plain `pytest`.

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
cluster, runs `tests/integration/test_todo_integration.py` through this client
library, then tears everything down. Step titles below are printed live as
`[STEP_NAME]` so you can follow progress in the terminal.

### Harness (`start_integration_test.sh`)

| Step | What happens |
|------|----------------|
| `CHECK_PREFLIGHT` | Verifies `docker`, `docker compose`, `curl`, Docker daemon access, and Python deps (`pytest`, `PyJWT`, `cryptography`, editable `datorium_client`). Resolves `DATORIUMDB_SRC` (default: sibling `../datoriumdb`) and checks that source includes recursive `FindRefFields` (`collectRefFields`, needed for `Users.todoLists` array cached refs). |
| `COMPOSE_UP` | Builds image `datoriumdb:local` from that source and starts a unique Compose project with **server1** (`00-7F`) and **server2** (`80-FF`). Each server is dual-role SOT + read member for its range. Establishment config mounts an empty Todo app (Users, TodoLists, Todos + `Todos.byStatus` search). |
| `WAIT_CLUSTER` | Polls `GET /datoriumdb/v1/health` on both host ports (`18081` / `18082`) and `GET /datoriumdb/v1/ready` on server1 until the cluster is usable. |
| `MINT_TOKEN` | Signs a short-lived client JWT with the fixture Ed25519 key matching `__auth.json` (`datoriumdb.kind=client`, active `kid`). |
| `RUN_SCENARIO` | Runs the live Todo pytest with `DATORIUM_TOKEN` and host base URLs. Docker-internal `http://serverN:8080` URLs are rewritten to localhost for the host client. |
| `SNAPSHOT_DBS` | Before teardown (success or failure), replaces `tests/integration/todo/analysis/server{1,2}/` with each container's `/db/` tree and writes `MANIFEST.txt`. Last run only (no history). Gitignored. |
| `COMPOSE_DOWN` | Always runs (shell `trap` on success, failure, or interrupt): `docker compose down -v --remove-orphans` for that project name. |

### Post-run DB analysis

```text
tests/integration/todo/analysis/
  MANIFEST.txt          # project, timestamps, URLs, exit code
  server1/              # copy of server1 container /db
  server2/              # copy of server2 container /db
```

### Scenario (`test_todo_integration.py`)

The establishment starts **empty** (schemas and search definitions only; no
documents). The test picks deterministic document IDs that land in both shard
ranges so routing is exercised for real.

| Step | What happens |
|------|----------------|
| `WAIT_READY` | Polls readiness through the client until server1 reports `ready: true`. |
| `ESTABLISH` | `GET /establish` with catalog `Users` / `TodoLists` / `Todos`, caches config. |
| `BIND_TYPED` | Bind typed `CollectionClient`s for Users, TodoLists, Todos. |
| `PICK_IDS` | Chooses five IDs: two Users (low + high), one TodoList (low), two Todos (high). |
| `CREATING_USERS_RAW` | Raw `Client.create` for **Ada**. |
| `CREATING_USERS_TYPED` | Typed `create_doc` for **Grace**. |
| `CREATING_LIST_TYPED` | Typed `create_doc` for a TodoList titled "Ship client" with live `@` + cached `@@` owner refs to Grace. |
| `LINK_LIST_TO_USER_RAW` | Raw `patch` via `patch_detail_appending_cached_ref` appends `@@__TodoLists__{listLow}` onto Grace's `todoLists`. |
| `READ_USER_FRONT_PAGE` | Raw read of Users/Grace with `cacheSummaries` until front-page summaries show the list title (up to ~45s). |
| `PATCH_LIST_TITLE_TYPED` | Typed get → mutate title → `create_patch_from_changes` → `patch_doc` (`"Ship client v2"`). |
| `WAIT_FRONT_PAGE_UPDATE` | Re-reads Grace until the front-page cached list title updates (max ~15s). |
| `RESOLVE_LIVE_REF` | Typed `get_doc_opts` of the list + `resolve_direct_ref` for the live `@` owner. |
| `READ_CACHED_REF` | Raw `cacheSummaries` read of the TodoList to create the local cache stub for Grace. |
| `PATCH_CACHED_TARGET_TYPED` | Typed hand-built RFC 6902 via `create_patch` / `patch_doc` (`displayName` → `"Grace Hopper"`). |
| `WAIT_CACHE_UPDATE` | Re-reads the TodoList until `cacheSummaries.Users.{Grace}.displayName` updates (max ~15s). |
| `CREATING_TODO_RAW` | Raw create of a high-shard Todo (`status: open`) with live + cached refs to the list. |
| `PATCHING_TODO_RAW` | Raw RFC 6902 patch `status` open → done; asserts version advanced. |
| `WAIT_SEARCH` | Polls `search Todos byStatus {status: done}` until the raw todo ID appears. |
| `DELETING_TODO_RAW` | Raw delete (retry once); expects `documentNotFound` on re-read. |
| `TYPED_TODO_CRUD` | Typed create / get / patch-from-changes / delete on a second Todo (also proves private baseline ignores a mutated `original_doc`). |
| `PASSED` | Scenario finished successfully. |

Cache-update note: datoriumdb completes pending cache work as a no-op when the
read member has no stub file yet. So a referring `cacheSummaries` read must
seed the stub before patching the cached target if you expect the summary to update.
