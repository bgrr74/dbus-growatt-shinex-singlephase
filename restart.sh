#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="$(basename "$SCRIPT_DIR")"
SERVICE_LINK="/service/$SERVICE_NAME"

if [ ! -L "$SERVICE_LINK" ]; then
  echo "$SERVICE_NAME is not installed. Run install.sh first."
  exit 1
fi

if ! command -v svc >/dev/null 2>&1 || ! command -v svstat >/dev/null 2>&1; then
  echo "runit commands svc and svstat are required."
  exit 1
fi

svc -d "$SERVICE_LINK"
stopped=0
for attempt in 1 2 3 4 5; do
  if svstat "$SERVICE_LINK" 2>/dev/null | grep -q ': down'; then
    stopped=1
    break
  fi
  sleep 1
done

if [ "$stopped" -ne 1 ]; then
  echo "Failed to stop $SERVICE_NAME cleanly."
  exit 1
fi

svc -u "$SERVICE_LINK"
started=0
for attempt in 1 2 3 4 5; do
  if svstat "$SERVICE_LINK" 2>/dev/null | grep -q ': up'; then
    started=1
    break
  fi
  sleep 1
done

if [ "$started" -ne 1 ]; then
  echo "Failed to start $SERVICE_NAME."
  exit 1
fi

echo "Restarted $SERVICE_NAME cleanly"
