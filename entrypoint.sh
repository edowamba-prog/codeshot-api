#!/bin/bash
set -e
echo "=== CodeShot API ==="
echo "Installing Chromium (this takes ~30s on first boot)..."
python3 -m playwright install --with-deps chromium 2>&1 | tail -3
echo "Chromium ready. Starting server..."
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
