#!/bin/bash
# Test Dashboard Endpoints

echo "Testing /dashboard/stats"
curl -s http://localhost:8000/dashboard/stats | jq

echo ""
echo "Testing /dashboard/calls"
curl -s http://localhost:8000/dashboard/calls | jq
