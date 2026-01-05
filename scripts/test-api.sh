#!/bin/bash
# Test script for QuBot REST API
# Usage: ./scripts/test-api.sh [API_URL] [API_KEY]

API_URL="${1:-http://localhost:3001}"
API_KEY="${2:-testkey}"

echo "🧪 Testing QuBot REST API at $API_URL"
echo "========================================"

# Health check (no auth required)
echo -n "Health check... "
HEALTH=$(curl -s "$API_URL/health")
if echo "$HEALTH" | grep -q '"status":"ok"'; then
    echo "✓ OK"
else
    echo "✗ FAIL: $HEALTH"
fi

# Test auth failure
echo -n "Auth rejection (no key)... "
AUTH_FAIL=$(curl -s "$API_URL/api/status")
if echo "$AUTH_FAIL" | grep -q '"error":"Unauthorized"'; then
    echo "✓ OK"
else
    echo "✗ FAIL: $AUTH_FAIL"
fi

# AI Settings
echo -n "GET /api/ai/settings... "
AI_SETTINGS=$(curl -s -H "Authorization: Bearer $API_KEY" "$API_URL/api/ai/settings")
if echo "$AI_SETTINGS" | grep -q 'provider\|error'; then
    echo "✓ Response received"
else
    echo "✗ FAIL: $AI_SETTINGS"
fi

# AI Providers
echo -n "GET /api/ai/providers... "
PROVIDERS=$(curl -s -H "Authorization: Bearer $API_KEY" "$API_URL/api/ai/providers")
if echo "$PROVIDERS" | grep -q '"providers"'; then
    echo "✓ OK"
else
    echo "✗ FAIL: $PROVIDERS"
fi

# AI Chats
echo -n "GET /api/ai/chats... "
CHATS=$(curl -s -H "Authorization: Bearer $API_KEY" "$API_URL/api/ai/chats")
if echo "$CHATS" | grep -q '"chats"'; then
    echo "✓ OK"
else
    echo "✗ FAIL: $CHATS"
fi

# RSS Subscriptions
echo -n "GET /api/rss/subscriptions... "
RSS=$(curl -s -H "Authorization: Bearer $API_KEY" "$API_URL/api/rss/subscriptions")
if echo "$RSS" | grep -q '"subscriptions"'; then
    echo "✓ OK"
else
    echo "✗ FAIL: $RSS"
fi

# Monitor Sources
echo -n "GET /api/monitor/sources... "
MON=$(curl -s -H "Authorization: Bearer $API_KEY" "$API_URL/api/monitor/sources")
if echo "$MON" | grep -q 'channels\|error'; then
    echo "✓ Response received"
else
    echo "✗ FAIL: $MON"
fi

# System Status
echo -n "GET /api/status... "
STATUS=$(curl -s -H "Authorization: Bearer $API_KEY" "$API_URL/api/status")
if echo "$STATUS" | grep -q '"services"'; then
    echo "✓ OK"
else
    echo "✗ FAIL: $STATUS"
fi

echo ""
echo "========================================"
echo "Done! Check results above."
echo ""
echo "To test AI chat:"
echo "  curl -X POST -H 'Authorization: Bearer $API_KEY' \\"
echo "       -H 'Content-Type: application/json' \\"
echo "       -d '{\"message\": \"Hello!\"}' \\"
echo "       $API_URL/api/ai/chat"
