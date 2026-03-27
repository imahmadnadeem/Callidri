#!/bin/bash
sleep 5
curl -X POST http://localhost:8000/join-room \
  -H "Content-Type: application/json" \
  -d '{"room": "test-room"}'
