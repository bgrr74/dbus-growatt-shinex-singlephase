#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="$(basename "$SCRIPT_DIR")"
SERVICE_LINK="/service/$SERVICE_NAME"
RC_LOCAL="/data/rc.local"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this installer as root."
  exit 1
fi

case "$SERVICE_NAME" in
  ''|*[!A-Za-z0-9._-]*)
    echo "Directory name '$SERVICE_NAME' is not a safe runit service name."
    exit 1
    ;;
esac

if [ ! -f "$SCRIPT_DIR/config.ini" ]; then
  cp "$SCRIPT_DIR/config.example.ini" "$SCRIPT_DIR/config.ini"
  echo "Created $SCRIPT_DIR/config.ini"
  echo "Edit the configuration and run install.sh again."
  exit 1
fi

chmod 0755 \
  "$SCRIPT_DIR/install.sh" \
  "$SCRIPT_DIR/restart.sh" \
  "$SCRIPT_DIR/uninstall.sh" \
  "$SCRIPT_DIR/dbus-growatt-shinex.py" \
  "$SCRIPT_DIR/service/run" \
  "$SCRIPT_DIR/service/log/run"

mkdir -p /service "/var/log/$SERVICE_NAME"

if [ -e "$SERVICE_LINK" ] || [ -L "$SERVICE_LINK" ]; then
  CURRENT_TARGET="$(readlink -f "$SERVICE_LINK" 2>/dev/null || true)"
  EXPECTED_TARGET="$(readlink -f "$SCRIPT_DIR/service")"
  if [ "$CURRENT_TARGET" != "$EXPECTED_TARGET" ]; then
    echo "Refusing to replace active service link $SERVICE_LINK."
    echo "Current target: ${CURRENT_TARGET:-unknown}"
    echo "Expected target: $EXPECTED_TARGET"
    echo "Uninstall or stop the old installation before migrating."
    exit 1
  fi
fi

ln -sfn "$SCRIPT_DIR/service" "$SERVICE_LINK"

if [ ! -f "$RC_LOCAL" ]; then
  printf '%s\n' '#!/bin/bash' > "$RC_LOCAL"
fi
chmod 0755 "$RC_LOCAL"

INSTALL_LINE="/bin/bash $SCRIPT_DIR/install.sh"
if ! grep -Fqx "$INSTALL_LINE" "$RC_LOCAL"; then
  printf '%s\n' "$INSTALL_LINE" >> "$RC_LOCAL"
fi

if command -v svc >/dev/null 2>&1 && command -v svstat >/dev/null 2>&1; then
  service_found=0
  for attempt in 1 2 3 4 5; do
    if svstat "$SERVICE_LINK" >/dev/null 2>&1; then
      service_found=1
      break
    fi
    sleep 1
  done

  if [ "$service_found" -eq 1 ]; then
    if [ -d "$SERVICE_LINK/log" ]; then
      svc -u "$SERVICE_LINK/log"
    fi
    svc -u "$SERVICE_LINK"
  else
    echo "Warning: runit has not discovered $SERVICE_LINK yet; it should start automatically."
  fi
fi

echo "Installed $SERVICE_NAME"
