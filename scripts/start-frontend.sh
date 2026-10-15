#!/usr/bin/env bash
# Start the RESQNET UI on :5173 (proxies /api and /ws to :8000)
cd "$(dirname "$0")/../frontend" && npm install && npm run dev
