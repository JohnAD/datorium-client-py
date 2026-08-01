#!/usr/bin/env bash
# Start a two-shard DatoriumDB Compose stack, run the Todo integration pytest
# through the Python client library, then tear the stack down.
#
# Step titles match tech-docs/TESTING.md ("Todo integration story").
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="${ROOT}/tests/integration/todo"
COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.yml"
ANALYSIS_ROOT="${COMPOSE_DIR}/analysis"
PROJECT="datorium-todo-py-$(date +%s)-$$"
DATORIUMDB_SRC="${DATORIUMDB_SRC:-$(cd "${ROOT}/../datoriumdb" 2>/dev/null && pwd || true)}"

SERVER1_URL="${DATORIUM_SERVER1_URL:-http://127.0.0.1:18081}"
SERVER2_URL="${DATORIUM_SERVER2_URL:-http://127.0.0.1:18082}"

COMPOSE_STARTED=0
ANALYSIS_DIR=""

step() { printf '[%s]\n' "$1"; }
detail() { printf '  %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

compose() {
  docker compose -f "${COMPOSE_FILE}" -p "${PROJECT}" "$@"
}

# Copy each server's /db tree to the host for post-run inspection.
# Overwrites the fixed analysis/server{1,2} dirs (last run only; no history).
# Runs before COMPOSE_DOWN so volumes still exist on success or failure.
snapshot_dbs() {
  if (( COMPOSE_STARTED != 1 )); then
    return 0
  fi
  step "SNAPSHOT_DBS"
  ANALYSIS_DIR="${ANALYSIS_ROOT}"
  rm -rf "${ANALYSIS_DIR}/server1" "${ANALYSIS_DIR}/server2"
  mkdir -p "${ANALYSIS_DIR}/server1" "${ANALYSIS_DIR}/server2"

  local ok=1
  if ! compose cp "server1:/db/." "${ANALYSIS_DIR}/server1/" >/dev/null 2>&1; then
    detail "warning: could not copy server1:/db"
    ok=0
  fi
  if ! compose cp "server2:/db/." "${ANALYSIS_DIR}/server2/" >/dev/null 2>&1; then
    detail "warning: could not copy server2:/db"
    ok=0
  fi

  {
    echo "project=${PROJECT}"
    echo "captured_at=$(date -Iseconds)"
    echo "datoriumdb_src=${DATORIUMDB_SRC}"
    echo "server1_url=${SERVER1_URL}"
    echo "server2_url=${SERVER2_URL}"
    echo "exit_code_at_snapshot=${1:-unknown}"
  } >"${ANALYSIS_DIR}/MANIFEST.txt"

  if (( ok == 1 )); then
    detail "host copy: ${ANALYSIS_DIR}"
    detail "  server1/  ← container server1:/db"
    detail "  server2/  ← container server2:/db"
  else
    detail "partial snapshot under ${ANALYSIS_DIR} (see warnings above)"
  fi
}

cleanup() {
  local ec=$?
  set +e
  if [[ -n "${PROJECT:-}" ]] && [[ -f "${COMPOSE_FILE}" ]]; then
    snapshot_dbs "${ec}"
    step "COMPOSE_DOWN"
    detail "project ${PROJECT}"
    compose down -v --remove-orphans >/dev/null 2>&1 || true
  fi
  if [[ -n "${ANALYSIS_DIR}" && -d "${ANALYSIS_DIR}" ]]; then
    detail "DB analysis retained at ${ANALYSIS_DIR}"
  fi
  exit "${ec}"
}
trap cleanup EXIT INT TERM

step "CHECK_PREFLIGHT"
command -v docker >/dev/null || die "docker is required"
docker compose version >/dev/null 2>&1 || die "docker compose (v2 plugin) is required"
command -v curl >/dev/null || die "curl is required"
if ! docker info >/dev/null 2>&1; then
  die "cannot talk to the Docker daemon (permission denied or daemon down). Add this user to the docker group or fix DOCKER_HOST, then retry."
fi
[[ -n "${DATORIUMDB_SRC}" && -f "${DATORIUMDB_SRC}/Dockerfile" ]] || \
  die "DatoriumDB source not found. Clone it next to this repo or set DATORIUMDB_SRC."
[[ -f "${COMPOSE_FILE}" ]] || die "missing ${COMPOSE_FILE}"
# Front-page Users.todoLists needs recursive FindRefFields (array @@ refs).
if ! grep -q 'func collectRefFields' "${DATORIUMDB_SRC}/internal/agents/cache/projection.go" 2>/dev/null; then
  die "DATORIUMDB_SRC lacks recursive FindRefFields (collectRefFields). Checkout datoriumdb main (or a branch with the cache-ref recursion fix), then retry."
fi

PYTHON=""
if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PYTHON="${ROOT}/.venv/bin/python"
elif command -v python3 >/dev/null; then
  PYTHON="$(command -v python3)"
else
  die "python3 is required (prefer a project .venv with: pip install -e '.[dev]')"
fi
"${PYTHON}" -c "import jwt, cryptography, pytest, datorium_client" >/dev/null 2>&1 || \
  die "Python deps missing. From ${ROOT}: python -m pip install -e '.[dev]'"

export DATORIUMDB_SRC
mkdir -p "${ANALYSIS_ROOT}"
detail "DATORIUMDB_SRC=${DATORIUMDB_SRC}"
detail "expected DatoriumDB v0.0.5+"
if command -v git >/dev/null && [[ -d "${DATORIUMDB_SRC}/.git" ]]; then
  detail "datoriumdb $(git -C "${DATORIUMDB_SRC}" rev-parse --short HEAD) ($(git -C "${DATORIUMDB_SRC}" describe --tags --always 2>/dev/null || echo untagged))"
fi
detail "compose project=${PROJECT}"
detail "python=${PYTHON}"

step "COMPOSE_UP"
compose up -d --build
COMPOSE_STARTED=1

step "WAIT_CLUSTER"
detail "health/ready on ${SERVER1_URL} and ${SERVER2_URL}"
deadline=$((SECONDS + 180))
ready=0
while (( SECONDS < deadline )); do
  if curl -fsS "${SERVER1_URL}/datoriumdb/v1/health" >/dev/null 2>&1 \
    && curl -fsS "${SERVER2_URL}/datoriumdb/v1/health" >/dev/null 2>&1; then
    if curl -fsS "${SERVER1_URL}/datoriumdb/v1/ready" 2>/dev/null | grep -q '"ready":true'; then
      ready=1
      break
    fi
  fi
  sleep 2
done
(( ready == 1 )) || die "servers did not become ready in time"

step "MINT_TOKEN"
TOKEN="$("${PYTHON}" "${ROOT}/tests/integration/mint_token.py" \
  --auth "${COMPOSE_DIR}/fixtures/server1/.config/__auth.json" \
  --key "${COMPOSE_DIR}/secrets/dev-signing-key.pem" \
  --subject "todo-integration")"
[[ -n "${TOKEN}" ]] || die "failed to mint client token"

step "RUN_SCENARIO"
export DATORIUM_TOKEN="${TOKEN}"
export DATORIUM_SERVER1_URL="${SERVER1_URL}"
export DATORIUM_SERVER2_URL="${SERVER2_URL}"
# -s so [STEP] prints from the scenario are visible.
(cd "${ROOT}" && "${PYTHON}" -m pytest \
  tests/integration/test_todo_integration.py \
  tests/integration/test_todo_async_integration.py \
  -m integration \
  -s \
  --tb=short)

detail "integration demonstration succeeded"
