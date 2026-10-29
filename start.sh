#!/bin/sh
# Guardrail Manager launcher. ACCESS_CODE must be set in the environment.
set -e
cd "$(dirname "$0")"
if [ -z "$ACCESS_CODE" ]; then
  echo "Refusing to start: ACCESS_CODE env var is not set." >&2
  exit 2
fi
exec python3 server.py
