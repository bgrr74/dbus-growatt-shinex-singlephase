#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="$(basename "$SCRIPT_DIR")"
SERVICE_LINK="/service/$SERVICE_NAME"
RC_LOCAL="/data/rc.local"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this uninstaller as root."
  exit 1
fi

if [ -L "$SERVICE_LINK" ]; then
  command -v svc >/dev/null 2>&1 && svc -d "$SERVICE_LINK" || true
  rm -f "$SERVICE_LINK"
fi

if [ -f "$RC_LOCAL" ]; then
  INSTALL_LINE="/bin/bash $SCRIPT_DIR/install.sh"
  TEMP_FILE="$(mktemp)"
  grep -Fvx "$INSTALL_LINE" "$RC_LOCAL" > "$TEMP_FILE" || true
  chmod --reference="$RC_LOCAL" "$TEMP_FILE" 2>/dev/null || chmod 0755 "$TEMP_FILE"
  mv "$TEMP_FILE" "$RC_LOCAL"
fi

echo "Uninstalled $SERVICE_NAME; configuration and logs were retained."
