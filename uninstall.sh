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
  if command -v svc >/dev/null 2>&1; then
    if [ -d "$SERVICE_LINK/log" ]; then
      svc -d "$SERVICE_LINK/log" || true
    fi
    svc -d "$SERVICE_LINK" || true

    if command -v svstat >/dev/null 2>&1; then
      all_down=0
      for attempt in 1 2 3 4 5; do
        main_down=0
        log_down=1
        svstat "$SERVICE_LINK" 2>/dev/null | grep -q ': down' && main_down=1
        if [ -d "$SERVICE_LINK/log" ]; then
          svstat "$SERVICE_LINK/log" 2>/dev/null | grep -q ': down' || log_down=0
        fi
        if [ "$main_down" -eq 1 ] && [ "$log_down" -eq 1 ]; then
          all_down=1
          break
        fi
        sleep 1
      done
      if [ "$all_down" -ne 1 ]; then
        echo "Refusing to remove $SERVICE_LINK because its services did not stop cleanly."
        exit 1
      fi
    else
      sleep 1
    fi
  fi
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
