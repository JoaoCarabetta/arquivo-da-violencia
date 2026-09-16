#!/bin/bash
# Regression test: staging backend deploy/sync must not start or health-wait
# the worker. Production deploy must still start api + worker.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/lib/deploy-common.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

echo "==> unit: backend_runtime_services / backend_waits_for_worker"
[ "$(backend_runtime_services staging)" = "api" ] || fail "staging services should be 'api'"
[ "$(backend_runtime_services production)" = "api worker" ] || fail "prod services should be 'api worker'"
[ "$(backend_runtime_services)" = "api worker" ] || fail "default services should be 'api worker'"
backend_waits_for_worker staging && fail "staging should not wait for worker"
backend_waits_for_worker production || fail "production should wait for worker"
pass "helpers"

run_with_stubs() {
    local label="$1"
    shift
    local work
    work="$(mktemp -d)"
    local stubs="$work/bin"
    local log="$work/docker.log"
    mkdir -p "$stubs" "$work/repo"
    printf 'POSTGRES_PASSWORD=test\n' > "$work/repo/.env"
    git -C "$work/repo" init -q
    git -C "$work/repo" config user.email test@example.com
    git -C "$work/repo" config user.name test
    git -C "$work/repo" checkout -q -b develop
    git -C "$work/repo" checkout -q -b master
    echo stub > "$work/repo/README"
    git -C "$work/repo" add README
    git -C "$work/repo" commit -q -m init

    cat > "$stubs/docker" <<'EOF'
#!/bin/bash
echo "docker $*" >> "${DOCKER_LOG:?}"
if [[ " $* " == *" inspect "* ]]; then
    echo "healthy"
fi
if [[ " $* " == *" pg_dump "* ]]; then
    echo "DUMP"
fi
if [[ " $* " == *" psql "* ]]; then
    echo "ok"
fi
exit 0
EOF
    cat > "$stubs/curl" <<'EOF'
#!/bin/bash
exit 0
EOF
    cat > "$stubs/git" <<'EOF'
#!/bin/bash
exit 0
EOF
    cat > "$stubs/df" <<'EOF'
#!/bin/bash
echo "ok"
exit 0
EOF
    chmod +x "$stubs"/*

    local status=0
    PATH="$stubs:/usr/bin:/bin" \
        REPO_DIR="$work/repo" \
        DOCKER_LOG="$log" \
        "$@" >"$work/stdout.txt" 2>"$work/stderr.txt" || status=$?

    echo "$work" "$log" "$status"
}

assert_no_worker_up() {
    local log="$1"
    local label="$2"
    if grep -E 'up -d( --no-deps)? api worker' "$log" >/dev/null; then
        echo "---- docker log ($label) ----"
        cat "$log"
        fail "$label started worker via compose up"
    fi
    if grep -E 'up -d( --no-deps)? worker(\s|$)' "$log" >/dev/null; then
        echo "---- docker log ($label) ----"
        cat "$log"
        fail "$label started worker as a named service"
    fi
}

assert_api_up() {
    local log="$1"
    local label="$2"
    if ! grep -E 'up -d( --no-deps)? api( |$)' "$log" >/dev/null; then
        echo "---- docker log ($label) ----"
        cat "$log"
        fail "$label did not start api"
    fi
}

assert_no_worker_inspect() {
    local log="$1"
    local label="$2"
    if grep -E "inspect .*staging-arquivo-worker" "$log" >/dev/null; then
        echo "---- docker log ($label) ----"
        cat "$log"
        fail "$label waited on staging worker health"
    fi
}

echo "==> integration: deploy-backend.sh staging"
read -r work log status < <(run_with_stubs staging bash "$ROOT/scripts/deploy-backend.sh" staging)
[ "$status" = "0" ] || { echo "---- stdout ----"; cat "$work/stdout.txt"; echo "---- stderr ----"; cat "$work/stderr.txt"; fail "staging deploy exited $status"; }
assert_api_up "$log" "staging deploy"
assert_no_worker_up "$log" "staging deploy"
assert_no_worker_inspect "$log" "staging deploy"
grep -q 'Skipping worker health check' "$work/stdout.txt" || fail "staging deploy did not skip worker health"
pass "staging deploy starts api only and skips worker health"
rm -rf "$work"

echo "==> integration: deploy-backend.sh production"
read -r work log status < <(run_with_stubs production bash "$ROOT/scripts/deploy-backend.sh" production)
[ "$status" = "0" ] || { echo "---- stdout ----"; cat "$work/stdout.txt"; echo "---- stderr ----"; cat "$work/stderr.txt"; fail "production deploy exited $status"; }
if ! grep -E 'up -d --no-deps api worker' "$log" >/dev/null; then
    echo "---- docker log (production deploy) ----"
    cat "$log"
    fail "production deploy did not start api worker"
fi
if ! grep -E 'inspect .*arquivo-worker' "$log" >/dev/null; then
    echo "---- docker log (production deploy) ----"
    cat "$log"
    fail "production deploy did not wait for worker health"
fi
if grep -q 'Skipping worker health check' "$work/stdout.txt"; then
    fail "production deploy skipped worker health"
fi
pass "production deploy still starts api+worker and waits for worker"
rm -rf "$work"

echo "==> integration: sync-staging-db.sh"
read -r work log status < <(run_with_stubs sync-staging bash "$ROOT/scripts/sync-staging-db.sh")
[ "$status" = "0" ] || { echo "---- stdout ----"; cat "$work/stdout.txt"; echo "---- stderr ----"; cat "$work/stderr.txt"; fail "sync-staging-db exited $status"; }
assert_api_up "$log" "staging sync"
assert_no_worker_up "$log" "staging sync"
assert_no_worker_inspect "$log" "staging sync"
pass "staging DB sync starts api only and skips worker health"
rm -rf "$work"

echo ""
echo "✅ All deploy-backend staging worker checks passed"
