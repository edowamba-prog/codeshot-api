#!/bin/sh
# Docker entrypoint — ensures /data is writable by the app user,
# then drops privileges and starts the application.
set -e

# Create data dir if it doesn't exist (volume mount creates it root-owned)
mkdir -p /data

# Grant the app user ownership so SQLite/JSON writes work
chown -R app:app /data 2>/dev/null || true

# Drop to app user and start
exec su -s /bin/sh app -c "python3 -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
