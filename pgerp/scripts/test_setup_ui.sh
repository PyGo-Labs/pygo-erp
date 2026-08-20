#!/usr/bin/env bash
# Verify the setup wizard UI is served correctly and wired to the real API
API=http://127.0.0.1:8080

echo "1) HTTP status of /setup"
curl -s -o /tmp/setup_page.html -w "   status: %{http_code}  bytes: %{size_download}\n" $API/setup

echo "2) Alpine component and API wiring present in served HTML"
for pat in 'function wizard' 'x-data="wizard()"' \
           '/api/setup/status' '/api/setup/countries' '/api/setup/company' \
           '/api/setup/localization' '/api/setup/finalize' '/api/setup/settings' \
           '/api/system/readiness' '/api/demo/load' '/api/demo/clear'; do
  n=$(grep -c -- "$pat" /tmp/setup_page.html)
  if [ "$n" -gt 0 ]; then mark="OK "; else mark="MISS"; fi
  printf "   %s %-28s (%s)\n" "$mark" "$pat" "$n"
done

echo "3) Brand colors from the project palette"
for c in 2563EB 10B981 F59E0B 0F172A; do
  n=$(grep -c -- "$c" /tmp/setup_page.html)
  printf "   #%s -> %s\n" "$c" "$n"
done

echo "4) HTMX + Alpine + Tailwind loaded"
for lib in htmx.org alpinejs tailwindcss; do
  n=$(grep -c -- "$lib" /tmp/setup_page.html)
  printf "   %-14s %s\n" "$lib" "$n"
done

echo "5) Other views still serve (no regression)"
for v in / /productos /clientes /facturas /inventory; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "$API$v")
  printf "   %-12s %s\n" "$v" "$code"
done
