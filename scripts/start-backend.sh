#!/usr/bin/env bash
# Start the RESQNET API on :8000
cd "$(dirname "$0")/../backend" && python -m uvicorn app.api.main:app --port 8000 --reload
