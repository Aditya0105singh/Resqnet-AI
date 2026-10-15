#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/../backend" && python -m pytest tests -q -p no:asyncio
cd ../frontend && npx tsc -b && npx vite build
