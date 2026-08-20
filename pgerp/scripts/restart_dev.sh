#!/usr/bin/env bash
# Robust restart for PyGo ERP dev server.
# Avoids the classic pkill self-kill: the pattern would match this script's own
# command line, so we resolve PIDs with pgrep and exclude $$ / $PPID explicitly.
FRAMEWORK=/home/hermesuser/pygo-framework
PROJECT=/home/hermesuser/pygo-erp/pgerp
BIN=/tmp/pygo-erp
SOCK=/tmp/pgerp.sock
DB=/tmp/pgerp.db

kill_pattern() {
  local pat="$1"
  for pid in $(pgrep -f "$pat" 2>/dev/null); do
    if [ "$pid" != "$$" ] && [ "$pid" != "$PPID" ]; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  done
}

kill_pattern "app\.core\.main"
kill_pattern "^${BIN}$"
for pid in $(lsof -t -i:8080 2>/dev/null); do
  [ "$pid" != "$$" ] && kill -9 "$pid" 2>/dev/null || true
done

sleep 2
rm -f "$SOCK"
if [ "$1" = "--fresh" ]; then
  rm -f "$DB"
fi

remaining=$(pgrep -cf "app\.core\.main" 2>/dev/null || echo 0)
echo "remaining python workers: $remaining"

cd "$PROJECT" || exit 1
go build -o "$BIN" ./app/web/ || exit 1
echo "build ok"
