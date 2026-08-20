#!/usr/bin/env bash
# Fase A: module system + generic tax engine + real extensibility proof
API=http://127.0.0.1:8080
T=$(curl -s -X POST $API/api/auth/login -d "email=admin@demo.com&password=admin123" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

echo "1) Generic taxes seeded (country-agnostic, no MX yet)"
curl -s "$API/api/tax?token=$T" | head -c 320; echo ""

echo "2) Generic compute: 1000 @ 16% excluded"
curl -s "$API/api/tax/compute?amount=1000&tax_ids=\[1\]&token=$T"; echo ""

echo "3) Price-INCLUDED tax: 1160 already contains 16% -> untaxed must be 1000"
curl -s "$API/api/tax/compute?amount=1160&tax_ids=\[4\]&token=$T"; echo ""

echo "4) Cascade: include_base_amount raises the base for later taxes"
curl -s -X POST "$API/api/tax?token=$T" \
  -d "name=Cascade Excise 8pct&code=CAS8&computation=percent&amount=8&sequence=5&include_base_amount=1&scope=both" > /dev/null
CAS=$(curl -s "$API/api/tax?token=$T" | grep -o '"code":"CAS8"[^}]*' | grep -o '"id":[0-9]*' | head -1 | cut -d: -f2)
if [ -z "$CAS" ]; then CAS=$(python3 -c "
import sqlite3;c=sqlite3.connect('/tmp/pgerp.db')
r=c.execute(\"SELECT id FROM taxes WHERE code='CAS8'\").fetchone();print(r[0] if r else '')
"); fi
curl -s -X POST "$API/api/tax/compute-document?token=$T" -H "Content-Type: application/json" \
  -d "{\"lines\":[{\"amount\":1000,\"tax_ids\":[$CAS,1]}]}"; echo ""

echo "5) Withholding: 16% added, 10% retained"
curl -s -X POST "$API/api/tax?token=$T" \
  -d "name=Withhold 10pct&code=WH10&computation=percent&amount=10&is_withholding=1&sequence=20&scope=purchase" > /dev/null
WH=$(python3 -c "
import sqlite3;c=sqlite3.connect('/tmp/pgerp.db')
r=c.execute(\"SELECT id FROM taxes WHERE code='WH10'\").fetchone();print(r[0] if r else '')
")
curl -s -X POST "$API/api/tax/compute-document?token=$T" -H "Content-Type: application/json" \
  -d "{\"lines\":[{\"amount\":1000,\"tax_ids\":[1,$WH]}]}"; echo ""

echo "6) MODULE SCAN (should discover l10n_mx on disk)"
curl -s -X POST "$API/api/modules/scan?token=$T"; echo ""

echo "7) Module list (l10n_mx must be 'uninstalled')"
curl -s "$API/api/modules?token=$T" | head -c 400; echo ""

echo "8) MX tax group before install must NOT exist"
curl -s -X POST "$API/api/module/call?token=$T" -d "handler=l10n_mx.compute_tax&amount=1000&tax_group_code=MX_IVA16"; echo ""

echo "9) INSTALL l10n_mx (runs its migrations, loads its code)"
curl -s -X POST "$API/api/modules/install?token=$T" -d "name=l10n_mx"; echo ""

echo "10) Module info (hooks + migrations registered)"
curl -s "$API/api/modules/info?name=l10n_mx&token=$T" | head -c 500; echo ""

echo "11) MX taxes now present in the GENERIC engine"
curl -s "$API/api/tax?country=MX&token=$T" | head -c 350; echo ""

echo "12) Module handler works: MX IVA16 on 1000"
curl -s -X POST "$API/api/module/call?token=$T" -d "handler=l10n_mx.compute_tax&amount=1000&tax_group_code=MX_IVA16"; echo ""

echo "13) MX services group: IVA 16% + retentions IVA/ISR"
curl -s -X POST "$API/api/module/call?token=$T" -d "handler=l10n_mx.compute_tax&amount=10000&tax_group_code=MX_SERV"; echo ""

echo "14) RFC validation via module handler (valid then invalid)"
curl -s -X POST "$API/api/module/call?token=$T" -d "handler=l10n_mx.validate_rfc&rfc=AAA010101AAA"; echo ""
curl -s -X POST "$API/api/module/call?token=$T" -d "handler=l10n_mx.validate_rfc&rfc=BADRFC"; echo ""

echo "15) HOOK fires the module from the core (invoice.before_create)"
curl -s -X POST "$API/api/hooks/run?token=$T" -H "Content-Type: application/json" \
  -d '{"hook_point":"invoice.before_create","payload":{"rfc":"XAXX010101000"}}'; echo ""

echo "16) SAT catalog shipped by the module"
curl -s -X POST "$API/api/module/call?token=$T" -d "handler=l10n_mx.catalog&catalog=metodo_pago"; echo ""

echo "17) DISABLE l10n_mx -> hooks must stop firing"
curl -s -X POST "$API/api/modules/disable?token=$T" -d "name=l10n_mx"; echo ""
curl -s -X POST "$API/api/hooks/run?token=$T" -H "Content-Type: application/json" \
  -d '{"hook_point":"invoice.before_create","payload":{"rfc":"XAXX010101000"}}'; echo ""

echo "18) RE-ENABLE -> hooks fire again"
curl -s -X POST "$API/api/modules/enable?token=$T" -d "name=l10n_mx"; echo ""
curl -s -X POST "$API/api/hooks/run?token=$T" -H "Content-Type: application/json" \
  -d '{"hook_point":"invoice.before_create","payload":{"rfc":"XAXX010101000"}}'; echo ""

echo "19) Dependency graph"
curl -s "$API/api/modules/graph?token=$T" | head -c 300; echo ""

echo "20) CFDI prepare + simulated stamp (module-owned tables)"
curl -s -X POST "$API/api/facturas?token=$T" -d "cliente_id=1&total=11600" > /dev/null
curl -s -X POST "$API/api/module/call?token=$T" \
  -d "handler=l10n_mx.prepare_cfdi&invoice_id=1&rfc_emisor=AAA010101AAA&rfc_receptor=XAXX010101000"; echo ""
curl -s -X POST "$API/api/module/call?token=$T" -d "handler=l10n_mx.stamp_cfdi&cfdi_id=1"; echo ""

echo "21) Uninstall protection: core cannot be removed"
curl -s -X POST "$API/api/modules/uninstall?token=$T" -d "name=core"; echo ""
