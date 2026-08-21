#!/usr/bin/env bash
# UI D1/D2/D3 verification: pages serve as HTML and every field the UI reads
# exists in the API response. Assumes a FRESH database.
API=http://127.0.0.1:8080
T=$(curl -s -X POST $API/api/auth/login -d "email=admin@demo.com&password=admin123" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

echo "=== A) Pages serve real HTML with Alpine ==="
for page in valuacion trazabilidad devoluciones; do
  code=$(curl -s -o /tmp/p_$page.html -w '%{http_code}' "$API/$page")
  ctype=$(curl -s -o /dev/null -w '%{content_type}' "$API/$page")
  size=$(wc -c < /tmp/p_$page.html)
  xdata=$(grep -c 'x-data=' /tmp/p_$page.html)
  directives=$(grep -o 'x-model\|@click\|x-text\|x-show\|x-for' /tmp/p_$page.html | wc -l)
  printf "  %-14s %s  %-25s %6s bytes  x-data:%s  directivas:%s\n" \
    "/$page" "$code" "$ctype" "$size" "$xdata" "$directives"
done

echo ""
echo "=== B) Seed data for the flows ==="
curl -s -X POST "$API/api/inventory/warehouses?token=$T" -d "name=Central&code=CEN" > /dev/null
curl -s -X POST "$API/api/clientes?token=$T" -d "nombre=Cliente UI&email=ui@x.com" > /dev/null
curl -s -X POST "$API/api/productos?token=$T" -d "codigo=UI-1&nombre=Producto UI&precio_unitario=100&cost=60" > /dev/null
curl -s -X POST "$API/api/inventory/stock/adjust?token=$T" \
  -d "product_id=1&warehouse_id=1&new_quantity=200&reason=seed" > /dev/null
curl -s -X POST "$API/api/valuation/layers?token=$T" \
  -d "producto_id=1&warehouse_id=1&quantity=200&unit_cost=60" > /dev/null
curl -s -X POST "$API/api/periods/generate-year?token=$T" -d "year=2026" > /dev/null
echo "  seeded"

echo ""
echo "=== C) Every endpoint the UI calls answers ==="
check() {
  local label="$1" url="$2"
  local out
  out=$(curl -s "$API$url&token=$T" 2>/dev/null)
  if echo "$out" | grep -q '"error":null'; then
    printf "  %-34s OK\n" "$label"
  else
    printf "  %-34s FAIL -> %s\n" "$label" "$(echo "$out" | head -c 110)"
  fi
}
check "valuation/layers"        "/api/valuation/layers?only_available=1"
check "valuation/stock-value"   "/api/valuation/stock-value?x=1"
check "valuation/cogs"          "/api/valuation/cogs?x=1"
check "periods"                 "/api/periods?x=1"
check "periods/check"           "/api/periods/check?date=2026-03-15"
check "fx/convert"              "/api/fx/convert?amount=100&from_currency=USD&to_currency=MXN"
check "fx/differences"          "/api/fx/differences?x=1"
check "fx/exposure"             "/api/fx/exposure?x=1"
check "accounting/currencies"   "/api/accounting/currencies?x=1"
check "lots"                    "/api/lots?only_available=1"
check "lots/expiring"           "/api/lots/expiring?days=30"
check "stock/availability"      "/api/stock/availability?producto_id=1&warehouse_id=1"
check "reservations"            "/api/reservations?status=active"
check "backorders"              "/api/backorders?status=pending"
check "reorder/suggestions"     "/api/reorder/suggestions?x=1"
check "reorder/rules"           "/api/reorder/rules?x=1"
check "sales-returns"           "/api/sales-returns?x=1"
check "credit-notes"            "/api/credit-notes?x=1"
check "credit/exposure"         "/api/credit/exposure?x=1"
check "credit/events"           "/api/credit/events?blocked_only=0"
check "credit/check"            "/api/credit/check?cliente_id=1&amount=100"
check "sales/orders by customer" "/api/sales/orders?cliente_id=1"
check "productos"               "/api/productos?x=1"
check "facturas"                "/api/facturas?x=1"

echo ""
echo "=== D) Fields the UI binds actually come back ==="
python3 - "$T" <<'PY'
import json, sys, urllib.request
T = sys.argv[1]
API = "http://127.0.0.1:8080"

def get(path):
    with urllib.request.urlopen(f"{API}{path}&token={T}") as r:
        return json.load(r).get("result")

# (endpoint, fields the UI reads)
checks = [
    ("/api/valuation/stock-value?x=1", ["total_value", "total_quantity", "by_product"]),
    ("/api/valuation/cogs?x=1", ["total_cogs", "gross_cogs", "returned_cost", "by_product"]),
    ("/api/fx/exposure?x=1", ["base_currency", "by_currency", "total_base"]),
    ("/api/fx/differences?x=1", ["total_gain", "total_loss", "net_effect", "differences"]),
    ("/api/lots/expiring?days=30", ["expired", "expiring_soon", "expired_count", "expiring_count"]),
    ("/api/stock/availability?producto_id=1&warehouse_id=1", ["on_hand", "reserved", "available"]),
    ("/api/reorder/suggestions?x=1", ["count", "suggestions"]),
    ("/api/credit/exposure?x=1", ["customers", "count", "over_limit_count"]),
    ("/api/credit/events?blocked_only=0", ["events", "count"]),
    ("/api/credit/check?cliente_id=1&amount=100", ["allowed", "credit_limit", "exposure", "projected"]),
    ("/api/periods/check?date=2026-03-15", ["allowed", "period"]),
]
gaps = 0
for path, fields in checks:
    try:
        data = get(path)
    except Exception as e:
        print(f"  {path[:44]:46} ERROR {e}")
        gaps += 1
        continue
    missing = [f for f in fields if not isinstance(data, dict) or f not in data]
    if missing:
        print(f"  {path[:44]:46} GAP -> {missing}")
        gaps += 1
    else:
        print(f"  {path[:44]:46} {len(fields)}/{len(fields)} MATCH")
print()
print("TOTAL GAPS:", gaps)
PY
