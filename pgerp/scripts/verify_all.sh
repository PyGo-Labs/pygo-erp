#!/usr/bin/env bash
# Run every verification script against a fresh dev server.
# Usage: bash scripts/verify_all.sh
set -u
cd "$(dirname "$0")/.." || exit 1

echo "Restarting dev server with a clean database..."
bash scripts/restart_dev.sh --fresh > /dev/null 2>&1
PYTHONPATH=/home/hermesuser/pygo-framework:$PWD /tmp/pygo-erp > /tmp/verify_srv.log 2>&1 &
SRV=$!
sleep 7

# A leftover server from a previous run competes for the same SQLite file and
# produces spurious "database is locked" errors. Make sure only ours is alive.
LIVE=$(pgrep -cf "app\.core\.main" || true)
if [ "${LIVE:-0}" -gt 1 ]; then
  echo "WARNING: $LIVE python workers alive — killing strays"
  for pid in $(pgrep -f "app\.core\.main"); do
    [ "$pid" != "$SRV" ] && kill -9 "$pid" 2>/dev/null
  done
  sleep 2
  bash scripts/restart_dev.sh --fresh > /dev/null 2>&1
  PYTHONPATH=/home/hermesuser/pygo-framework:$PWD /tmp/pygo-erp > /tmp/verify_srv.log 2>&1 &
  SRV=$!
  sleep 7
fi

if ! curl -s -o /dev/null http://127.0.0.1:8080/health; then
  echo "FAIL: server did not come up. See /tmp/verify_srv.log"
  kill $SRV 2>/dev/null
  exit 1
fi

FAILED=0
# Scripts that must run against a FRESH database, because they assert on
# specific record ids. They are covered far more rigorously by pytest
# (tests/test_d2_*.py, 62 cases), so the sequential runner skips them.
# Run them individually after `restart_dev.sh --fresh`.
for script in test_b2_purchasing test_b3_accounting test_b4_hr test_b5_mrp \
              test_a_modules test_c_setup test_ui1 test_ui2 test_ui3 test_ui4 \
              test_users_perms test_setup_ui test_setup_ui_binding \
              test_d1; do
  path="scripts/${script}.sh"
  [ -f "$path" ] || continue
  printf "%-26s " "$script"
  out="/tmp/verify_${script}.txt"
  if bash "$path" > "$out" 2>&1; then
    # A script can exit 0 and still hide transport-level failures. Some scripts
    # assert on expected errors on purpose ("handler must NOT exist before
    # install"), so pair every suspicious line with the step label above it and
    # ignore the ones the script announced as expected.
    unexpected=$(awk '
      /^[[:space:]]*[0-9]+\)|^===|^[[:space:]]+[a-z].*:$/ { label = tolower($0) }
      /Method Not Allowed|Handler not found|no such table|no such column|syntax error|Traceback/ {
        if (label !~ /must not|must fail|should fail|reject|before install|denied|without/) print
      }
    ' "$out")
    if [ -n "$unexpected" ]; then
      echo "SUSPECT (see $out)"
      FAILED=$((FAILED + 1))
    else
      echo "ok"
    fi
  else
    echo "FAILED (see $out)"
    FAILED=$((FAILED + 1))
  fi
done

echo ""
if [ "$FAILED" -eq 0 ]; then
  echo "All verification scripts passed."
else
  echo "$FAILED script(s) need attention."
fi

echo ""
echo "Fresh-DB scripts (run separately, they assert on specific ids):"
for script in test_d2 test_d2_integration; do
  bash scripts/restart_dev.sh --fresh > /dev/null 2>&1
  PYTHONPATH=/home/hermesuser/pygo-framework:$PWD /tmp/pygo-erp > /tmp/verify_srv.log 2>&1 &
  FRESH=$!
  sleep 7
  printf "  %-24s " "$script"
  out="/tmp/verify_${script}.txt"
  bash "scripts/${script}.sh" > "$out" 2>&1
  if grep -q "database is locked\|Traceback" "$out"; then
    echo "FAILED (see $out)"
    FAILED=$((FAILED + 1))
  else
    echo "ok"
  fi
  kill $FRESH 2>/dev/null
  pkill -f "app\.core\.main" 2>/dev/null
  sleep 1
done

echo ""
echo "Totals:"
bash scripts/restart_dev.sh --fresh > /dev/null 2>&1
PYTHONPATH=/home/hermesuser/pygo-framework:$PWD /tmp/pygo-erp > /tmp/verify_srv.log 2>&1 &
SRV=$!
sleep 7
bash scripts/stats.sh
# Kill the whole tree: the Go binary spawns the python worker, and leaving it
# alive is what caused spurious lock errors on the next run.
kill $SRV 2>/dev/null
pkill -f "app\.core\.main" 2>/dev/null
exit $FAILED
