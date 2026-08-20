#!/usr/bin/env bash
# Verify the user-management + per-user permission cycle end to end
API=http://127.0.0.1:8080
T=$(curl -s -X POST $API/api/auth/login -d "email=admin@demo.com&password=admin123" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

echo "1) users list (token must reach the handler now)"
curl -s "$API/api/auth/users?token=$T" | head -c 220; echo ""

echo ""
echo "2) create a non-admin user"
curl -s -X POST "$API/api/auth/users?token=$T" -H "Content-Type: application/json" \
  -d '{"email":"vendedor@demo.com","password":"test1234","full_name":"Vendedor","role":"user"}' | head -c 200; echo ""

echo ""
echo "3) productos.create still works (token must NOT reach the INSERT)"
curl -s -X POST "$API/api/productos?token=$T" \
  -d "codigo=TOK-1&nombre=Prueba Token&precio_unitario=99" | head -c 180; echo ""

echo ""
echo "4) check permission for the new user BEFORE granting (expect denied)"
NEWUID=$(curl -s "$API/api/auth/users?token=$T" | python3 -c "
import json,sys
d=json.load(sys.stdin)['result']
users=d if isinstance(d,list) else d.get('users',[])
print(next((u['id'] for u in users if u.get('email')=='vendedor@demo.com'), ''))
")
echo "   new user id: $NEWUID"
curl -s "$API/api/permissions/check?user_id=$NEWUID&module=accounting&action=delete&token=$T" | head -c 160; echo ""

echo ""
echo "5) grant sales.read then re-check (expect allowed)"
curl -s -X POST "$API/api/permissions/grant?token=$T" -H "Content-Type: application/json" \
  -d "{\"user_id\":$NEWUID,\"module\":\"sales\",\"action\":\"read\"}" | head -c 120; echo ""
curl -s "$API/api/permissions/check?user_id=$NEWUID&module=sales&action=read&token=$T" | head -c 160; echo ""

echo ""
echo "6) revoke then re-check (expect denied again)"
curl -s -X POST "$API/api/permissions/revoke?token=$T" -H "Content-Type: application/json" \
  -d "{\"user_id\":$NEWUID,\"module\":\"sales\",\"action\":\"read\"}" | head -c 120; echo ""
curl -s "$API/api/permissions/check?user_id=$NEWUID&module=sales&action=read&token=$T" | head -c 160; echo ""
