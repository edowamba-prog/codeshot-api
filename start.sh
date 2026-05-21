#!/bin/bash
# CodeShot API — Start server
cd "$(dirname "$0")"
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
