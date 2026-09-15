#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="$(basename "$SCRIPT_DIR")"
SERVICE_LINK="/service/$SERVICE_NAME"

if [ ! -L "$SERVICE_LINK" ]; then
  echo "$SERVICE_NAME is not installed. Run install.sh first."
  exit 1
fi

svc -t "$SERVICE_LINK"
echo "Restarted $SERVICE_NAME"
