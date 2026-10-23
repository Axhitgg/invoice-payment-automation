#!/usr/bin/env bash
# Start a separate synthetic-only PostgreSQL cluster; never use DATABASE_URL.
set -euo pipefail

project_dir="$(cd "$(dirname "$0")/.." && pwd)"
pg_bin="${INVOICE_PG_BIN:-/opt/homebrew/opt/postgresql@17/bin}"
test_root="$(mktemp -d /private/tmp/invoice-lifecycle-test-XXXXXX)"
mkdir "$test_root/socket"
chmod 700 "$test_root" "$test_root/socket"

cleanup() {
    if [[ -f "$test_root/data/postmaster.pid" ]]; then
        "$pg_bin/pg_ctl" -D "$test_root/data" -m fast -w stop
    fi
    printf 'Stopped test cluster; diagnostics retained at %s\n' "$test_root"
}
trap cleanup EXIT

"$pg_bin/initdb" -D "$test_root/data" -U invoice_test --auth-local=trust --auth-host=reject > "$test_root/initdb.log"
"$pg_bin/pg_ctl" -D "$test_root/data" -l "$test_root/postgres.log" \
    -o "-k $test_root/socket -c listen_addresses='' -p 55492" -w start
"$pg_bin/createdb" -h "$test_root/socket" -p 55492 -U invoice_test invoice_lifecycle_test
cd "$project_dir"
INVOICE_TEST_DATABASE_URL="host=$test_root/socket port=55492 dbname=invoice_lifecycle_test user=invoice_test" \
    .venv/bin/python -m pytest -q test_invoice_api.py test_invoice_database.py
