#!/usr/bin/env bash
# UI-4 verification: module manager, tax engine, audit, permissions, system
API=http://127.0.0.1:8080
T=$(curl -s -X POST $API/api/auth/login -d "email=admin@demo.com&password=admin123" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

echo "=== A) Page serves real HTML ==="
read -r code ctype < <(curl -s -o /tmp/p4.html -w "%{http_code} %{content_type}\n" "$API/admin")
printf "  /admin  %s  %s  %sB  alpine:%s\n" "$code" "$ctype" \
  "$(wc -c < /tmp/p4.html)" "$(grep -c 'x-data=' /tmp/p4.html)"

echo ""
echo "=== B) Module manager (the extensibility proof) ==="
echo "  scan disk:"
curl -s -X POST "$API/api/modules/scan?token=$T" | head -c 200; echo ""
echo "  list:"
curl -s "$API/api/modules?token=$T" | head -c 260; echo ""
echo "  handler count BEFORE install:"
curl -s -X POST "$API/api/module/call?token=$T" \
  -H "Content-Type: application/json" -d '{"handler":"l10n_mx.compute_tax","amount":1000}' | head -c 120; echo ""
echo "  install l10n_mx:"
curl -s -X POST "$API/api/modules/install?token=$T" \
  -H "Content-Type: application/json" -d '{"name":"l10n_mx"}' | head -c 260; echo ""
echo "  same call AFTER install:"
curl -s -X POST "$API/api/module/call?token=$T" \
  -H "Content-Type: application/json" -d '{"handler":"l10n_mx.compute_tax","amount":1000}' | head -c 240; echo ""
echo "  module info (hooks + migrations):"
curl -s "$API/api/modules/info?name=l10n_mx&token=$T" | head -c 320; echo ""
echo "  disable -> hooks must stop firing:"
curl -s -X POST "$API/api/modules/disable?token=$T" \
  -H "Content-Type: application/json" -d '{"name":"l10n_mx"}' | head -c 180; echo ""
curl -s -X POST "$API/api/hooks/run?token=$T" -H "Content-Type: application/json" \
  -d '{"hook_point":"invoice.before_create","payload":{"probe":true}}' | head -c 180; echo ""
echo "  enable -> hooks fire again:"
curl -s -X POST "$API/api/modules/enable?token=$T" \
  -H "Content-Type: application/json" -d '{"name":"l10n_mx"}' | head -c 180; echo ""
curl -s -X POST "$API/api/hooks/run?token=$T" -H "Content-Type: application/json" \
  -d '{"hook_point":"invoice.before_create","payload":{"probe":true}}' | head -c 180; echo ""
echo "  hooks list:"
curl -s "$API/api/hooks?token=$T" | head -c 240; echo ""

echo ""
echo "=== C) Tax engine from the UI ==="
echo "  create cascade tax:"
curl -s -X POST "$API/api/tax?token=$T" -H "Content-Type: application/json" \
  -d '{"name":"Impuesto Verde","code":"VERDE","computation":"percent","amount":3,"sequence":5,"include_base_amount":1,"scope":"both"}' | head -c 180; echo ""
echo "  create withholding:"
curl -s -X POST "$API/api/tax?token=$T" -H "Content-Type: application/json" \
  -d '{"name":"Retencion Servicios","code":"RET10","computation":"percent","amount":10,"sequence":30,"is_withholding":1,"scope":"purchase"}' | head -c 180; echo ""
echo "  tax list count:"
curl -s "$API/api/tax?token=$T" | grep -o '"id"' | wc -l
echo "  simulate 1000 with cascade + withholding (GET endpoint):"
IDS=$(curl -s "$API/api/tax?token=$T" | python3 -c "
import json,sys
d=json.load(sys.stdin)['result']
ids=[str(t['id']) for t in d if t.get('code') in ('VERDE','RET10')]
print(','.join(ids))
")
curl -s "$API/api/tax/compute?amount=1000&quantity=1&tax_ids=$IDS&token=$T" | head -c 420; echo ""
echo "  tax groups:"
curl -s "$API/api/tax/groups?token=$T" | head -c 200; echo ""

echo ""
echo "=== D) Audit trail ==="
curl -s -X POST "$API/api/productos?token=$T" -d "codigo=ADM-1&nombre=Producto Admin&precio_unitario=500" > /dev/null
echo "  record an update with old/new values (real contract):"
curl -s -X POST "$API/api/audit?token=$T" -H "Content-Type: application/json" \
  -d '{"entity_type":"producto","entity_id":1,"action":"update","user_email":"admin@demo.com","old_values":{"precio_unitario":500,"nombre":"Producto Admin"},"new_values":{"precio_unitario":650,"nombre":"Producto Admin Pro"}}' | head -c 220; echo ""
echo "  invalid action must be rejected:"
curl -s -X POST "$API/api/audit?token=$T" -H "Content-Type: application/json" \
  -d '{"entity_type":"producto","entity_id":1,"action":"hackear"}' | head -c 200; echo ""
echo "  history for producto 1:"
curl -s "$API/api/audit/history?entity_type=producto&entity_id=1&token=$T" | head -c 340; echo ""
echo "  summary:"
curl -s "$API/api/audit/summary?token=$T" | head -c 260; echo ""

echo ""
echo "=== E) Permissions (granted per USER, not per role) ==="
echo "  grant sales.read to user 1:"
curl -s -X POST "$API/api/permissions/grant?token=$T" -H "Content-Type: application/json" \
  -d '{"user_id":1,"module":"sales","action":"read"}' | head -c 180; echo ""
echo "  grant field-level permission:"
curl -s -X POST "$API/api/permissions/grant?token=$T" -H "Content-Type: application/json" \
  -d '{"user_id":1,"module":"sales","action":"update","field":"discount"}' | head -c 180; echo ""
echo "  check allowed:"
curl -s "$API/api/permissions/check?user_id=1&module=sales&action=read&token=$T" | head -c 160; echo ""
echo "  check denied:"
curl -s "$API/api/permissions/check?user_id=1&module=accounting&action=delete&token=$T" | head -c 160; echo ""
echo "  list:"
curl -s "$API/api/permissions?token=$T" | head -c 240; echo ""

echo ""
echo "=== F) System status ==="
echo "  readiness:"
curl -s "$API/api/system/readiness?token=$T" | head -c 300; echo ""
echo "  attachments summary:"
curl -s "$API/api/attachments/summary?token=$T" | head -c 200; echo ""
