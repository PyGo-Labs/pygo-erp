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

if ! curl -s -o /dev/null http://127.0.0.1:8080/health; then
  echo "FAIL: server did not come up. See /tmp/verify_srv.log"
  kill $SRV 2>/dev/null
  exit 1
fi

FAILED=0
for script in test_b2_purchasing test_b3_accounting test_b4_hr test_b5_mrp \
              test_a_modules test_c_setup test_ui1 test_ui2 test_ui3 test_ui4 \
              test_users_perms test_setup_ui test_setup_ui_binding; do
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
echo "Totals:"
bash scripts/stats.sh
kill $SRV 2>/dev/null
exit $FAILED
