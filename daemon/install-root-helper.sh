#!/bin/bash
set -e

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root: sudo ./install-root-helper.sh"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing Beast Mode Root Helper..."
cp "$SCRIPT_DIR/beast_root_helper.py" /usr/local/bin/beast-mode-root-helper
chmod +x /usr/local/bin/beast-mode-root-helper

cp "$SCRIPT_DIR/beast-mode-daemon.service" /etc/systemd/system/beast-mode-daemon.service
systemctl daemon-reload
systemctl enable --now beast-mode-daemon.service

echo "Beast Mode root daemon installed and running successfully!"
