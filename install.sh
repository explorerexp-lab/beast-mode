#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing Beast Mode..."

# 1. Create target user directories
mkdir -p "$HOME/.local/bin"
mkdir -p "$HOME/.local/share/applications"
mkdir -p "$HOME/.local/share/icons/hicolor/scalable/apps"
mkdir -p "$HOME/.local/share/gnome-shell/extensions/beast-mode@laptop"
mkdir -p "$HOME/.config/systemd/user"
mkdir -p "$HOME/.config/beast-mode"

# 2. Install executables
cp "$SCRIPT_DIR/bin/beast_engine.py" "$HOME/.local/bin/beast-mode"
chmod +x "$HOME/.local/bin/beast-mode"

cp "$SCRIPT_DIR/app/beast_app.py" "$HOME/.local/bin/beast-mode-app"
chmod +x "$HOME/.local/bin/beast-mode-app"

# 3. Install icon and desktop launcher
cp "$SCRIPT_DIR/assets/beast-mode.svg" "$HOME/.local/share/icons/hicolor/scalable/apps/beast-mode.svg"
cp "$SCRIPT_DIR/assets/beast-mode.desktop" "$HOME/.local/share/applications/beast-mode.desktop"
gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

# 4. Install GNOME Shell extension
cp "$SCRIPT_DIR/extension/metadata.json" "$HOME/.local/share/gnome-shell/extensions/beast-mode@laptop/"
cp "$SCRIPT_DIR/extension/extension.js" "$HOME/.local/share/gnome-shell/extensions/beast-mode@laptop/"

# 5. Install and enable background monitor service
cat > "$HOME/.config/systemd/user/beast-mode-monitor.service" << EOF
[Unit]
Description=Beast Mode Integrated AC Monitor and Top Panel Indicator
After=default.target

[Service]
Type=simple
ExecStart=$SCRIPT_DIR/daemon/beast_service.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now beast-mode-monitor.service

echo "Installation complete!"
echo "Beast Mode is now active. Launch 'beast-mode-app' or control via top panel."
