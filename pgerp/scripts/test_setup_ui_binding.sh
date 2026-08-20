#!/usr/bin/env bash
# Verify the wizard UI markup binds to the exact fields the API returns.
API=http://127.0.0.1:8080
PAGE=/tmp/setup_page.html
curl -s $API/setup > $PAGE

echo "1) Fields the UI reads from /api/setup/status"
for f in progress_pct completed total is_ready steps; do
  ui=$(grep -c -- "$f" $PAGE)
  api=$(curl -s "$API/api/setup/status" | grep -c -- "\"$f\"")
  printf "   %-14s ui:%s api:%s %s\n" "$f" "$ui" "$api" \
    "$([ "$ui" -gt 0 ] && [ "$api" -gt 0 ] && echo MATCH || echo GAP)"
done

echo "2) Fields the UI reads from /api/setup/countries"
for f in country currency language localization_module module_state; do
  ui=$(grep -c -- "$f" $PAGE)
  api=$(curl -s "$API/api/setup/countries" | grep -c -- "\"$f\"")
  printf "   %-20s ui:%s api:%s %s\n" "$f" "$ui" "$api" \
    "$([ "$ui" -gt 0 ] && [ "$api" -gt 0 ] && echo MATCH || echo GAP)"
done

echo "3) Fields the UI reads from /api/system/readiness"
for f in areas operational blocking_areas ready; do
  ui=$(grep -c -- "$f" $PAGE)
  api=$(curl -s "$API/api/system/readiness" | grep -c -- "\"$f\"")
  printf "   %-16s ui:%s api:%s %s\n" "$f" "$ui" "$api" \
    "$([ "$ui" -gt 0 ] && [ "$api" -gt 0 ] && echo MATCH || echo GAP)"
done

echo "4) Interactive controls present"
for c in x-model @click x-text x-for x-if; do
  printf "   %-10s %s\n" "$c" "$(grep -c -- "$c" $PAGE)"
done

echo "5) Step labels rendered in Spanish"
grep -o "'[A-ZÁÉÍÓÚ][^']*': '[^']*'" $PAGE | head -6 || true
grep -o "chart_of_accounts: '[^']*'" $PAGE || true
