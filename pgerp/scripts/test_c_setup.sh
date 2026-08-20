#!/usr/bin/env bash
# Fase C: setup wizard from scratch, audit trail, attachments, readiness, demo data
API=http://127.0.0.1:8080
T=$(curl -s -X POST $API/api/auth/login -d "email=admin@demo.com&password=admin123" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

echo "1) Setup status on a fresh DB (should be partially complete from seeds)"
curl -s "$API/api/setup/status?token=$T" | head -c 400; echo ""

echo "2) Available country presets"
curl -s "$API/api/setup/countries?token=$T" | head -c 400; echo ""

echo "3) Reset wizard state (business data untouched)"
curl -s -X POST "$API/api/setup/reset?token=$T" -d "confirm=yes"; echo ""

echo "4) Step 1 - company identity"
curl -s -X POST "$API/api/setup/company?token=$T" \
  -d "name=Ander Labs SA&legal_name=Ander Labs Sociedad Anonima&tax_id=AAA010101AAA&email=hola@anderlabs.example&address=Av Reforma 100, CDMX"; echo ""

echo "5) Step 2 - localization MX (auto-installs l10n_mx)"
curl -s -X POST "$API/api/setup/localization?token=$T" -d "country=MX&install_module=1" | head -c 500; echo ""

echo "6) Settings after localization"
curl -s "$API/api/setup/settings?token=$T"; echo ""

echo "7) Finalize (seeds anything still missing)"
curl -s -X POST "$API/api/setup/finalize?token=$T"; echo ""

echo "8) Setup status must now be 100% ready"
curl -s "$API/api/setup/status?token=$T" | python3 -c "
import sys,json
d=json.load(sys.stdin)['result']
print('completed:',d['completed'],'/',d['total'],'->',d['progress_pct'],'%  ready:',d['is_ready'])
for s in d['steps']: print('  ',s['status'].ljust(8),s['step'])
"; echo ""

echo "9) System readiness by area"
curl -s "$API/api/system/readiness?token=$T" | python3 -c "
import sys,json
d=json.load(sys.stdin)['result']
print('operational:',d['operational'],' blocking:',d['blocking_areas'])
for k,v in d['areas'].items(): print('  ',('OK ' if v['ready'] else 'GAP'),k)
"; echo ""

echo "10) Audit: record a create then an update with real diff"
curl -s -X POST "$API/api/audit?token=$T" -H "Content-Type: application/json" \
  -d '{"entity_type":"producto","entity_id":1,"action":"create","user_id":1,"user_email":"admin@demo.com","new_values":{"nombre":"Laptop 14in","precio_unitario":1200}}'; echo ""
curl -s -X POST "$API/api/audit?token=$T" -H "Content-Type: application/json" \
  -d '{"entity_type":"producto","entity_id":1,"action":"update","user_id":1,"user_email":"admin@demo.com","old_values":{"nombre":"Laptop 14in","precio_unitario":1200},"new_values":{"nombre":"Laptop 14in Pro","precio_unitario":1450}}'; echo ""

echo "11) Invalid audit action must be rejected"
curl -s -X POST "$API/api/audit?token=$T" -d "entity_type=producto&entity_id=1&action=hack" | head -c 200; echo ""

echo "12) Audit history for producto 1 (diff must show both fields)"
curl -s "$API/api/audit/history?entity_type=producto&entity_id=1&token=$T" | python3 -c "
import sys,json
d=json.load(sys.stdin)['result']
print('entries:',d['count'])
for e in d['entries']:
    print('  ',e['action'],'by',e['user_email'],'changes:',json.dumps(e['changes']))
"; echo ""

echo "13) Audit by user + summary"
curl -s "$API/api/audit/by-user?user_id=1&token=$T" | python3 -c "
import sys,json
d=json.load(sys.stdin)['result']
print('user entries:',d['count'],'by_action:',d['by_action'])
"; echo ""

echo "14) Attach a file to an arbitrary entity (works for any record)"
curl -s -X POST "$API/api/attachments?token=$T" \
  -d "entity_type=producto&entity_id=1&filename=datasheet.pdf&mime_type=application/pdf&size_bytes=204800&description=Product datasheet&uploaded_by=1"; echo ""
curl -s -X POST "$API/api/attachments?token=$T" \
  -d "entity_type=sales_order&entity_id=1&filename=signed_po.pdf&mime_type=application/pdf&size_bytes=51200&uploaded_by=1"; echo ""

echo "15) List attachments for producto 1"
curl -s "$API/api/attachments?entity_type=producto&entity_id=1&token=$T" | head -c 350; echo ""

echo "16) Attachment summary by entity"
curl -s "$API/api/attachments/summary?token=$T"; echo ""

echo "17) Attaching created an audit entry automatically"
curl -s "$API/api/audit/history?entity_type=producto&entity_id=1&token=$T" | python3 -c "
import sys,json
d=json.load(sys.stdin)['result']
print('entries now:',d['count'])
"; echo ""

echo "18) Demo data requires explicit confirmation"
curl -s -X POST "$API/api/demo/load?token=$T" | head -c 220; echo ""

echo "19) Load demo data"
curl -s -X POST "$API/api/demo/load?token=$T" -d "confirm=yes"; echo ""

echo "20) Verify demo data is queryable through normal endpoints"
curl -s "$API/api/clientes?token=$T" | head -c 250; echo ""
curl -s "$API/api/suppliers?token=$T" | head -c 200; echo ""

echo "21) Audit summary at the end"
curl -s "$API/api/audit/summary?token=$T" | head -c 350; echo ""
