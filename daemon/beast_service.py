#!/usr/bin/env python3
"""
Beast Mode Native AppIndicator & AC Monitor Service
Uses libayatana-appindicator3 to provide a native, fully functional top bar
indicator menu and automatic AC power monitor.
"""

import os
import sys
import json
import time
import ctypes
import logging
import subprocess
from pathlib import Path

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

logging.basicConfig(level=logging.INFO, format="%(asctime)s [INDICATOR] %(message)s")

ENGINE_BIN = Path("/home/explorer01/.local/bin/beast-mode")
APP_BIN = Path("/home/explorer01/.local/bin/beast-mode-app")
STATE_FILE = Path.home() / ".config" / "beast-mode" / "state.json"

# Setup ctypes bindings for libayatana-appindicator3
ctypes.pythonapi.PyCapsule_GetPointer.restype = ctypes.c_void_p
ctypes.pythonapi.PyCapsule_GetPointer.argtypes = [ctypes.py_object, ctypes.c_char_p]

try:
    libappindicator = ctypes.CDLL("libayatana-appindicator3.so.1")
    libappindicator.app_indicator_new.restype = ctypes.c_void_p
    libappindicator.app_indicator_new.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    libappindicator.app_indicator_set_status.argtypes = [ctypes.c_void_p, ctypes.c_int]
    libappindicator.app_indicator_set_menu.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    libappindicator.app_indicator_set_icon_full.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
except Exception as e:
    logging.error(f"Failed to load libayatana-appindicator3: {e}")
    sys.exit(1)


def is_ac_online() -> bool:
    acad = Path("/sys/class/power_supply/ACAD/online")
    if acad.exists():
        try:
            return acad.read_text().strip() == "1"
        except Exception:
            pass
    return False


def get_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"enabled": False, "mode": "off", "ac_online": is_ac_online()}


class BeastModeIndicator:
    def __init__(self):
        self.last_ac_online = is_ac_online()
        self._updating = False

        # Create AppIndicator (category 0 = APP_INDICATOR_CATEGORY_APPLICATION_STATUS)
        self.ind = libappindicator.app_indicator_new(
            b"beast-mode-panel",
            b"weather-storm-symbolic",
            0
        )
        # Status 1 = APP_INDICATOR_STATUS_ACTIVE
        libappindicator.app_indicator_set_status(self.ind, 1)

        # Build GTK Menu
        self.menu = Gtk.Menu()

        # 1. Beast Mode Toggle Checkbox
        self.toggle_item = Gtk.CheckMenuItem(label="Beast Mode")
        self.toggle_item.connect("toggled", self.on_toggle_clicked)
        self.menu.append(self.toggle_item)

        # 2. Dynamic Status Subtitle Item (display-only)
        self.status_item = Gtk.MenuItem(label="Status: Balanced (Off)")
        self.status_item.set_sensitive(False)
        self.menu.append(self.status_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        # 3. Open Beast Mode Settings
        settings_item = Gtk.MenuItem(label="Beast Mode Settings...")
        settings_item.connect("activate", self.on_open_settings)
        self.menu.append(settings_item)

        # 4. Open Resources Monitor
        monitor_item = Gtk.MenuItem(label="System Resources Monitor...")
        monitor_item.connect("activate", self.on_open_monitor)
        self.menu.append(monitor_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        # 5. Reset Defaults
        reset_item = Gtk.MenuItem(label="Reset to Baseline Defaults")
        reset_item.connect("activate", self.on_reset_defaults)
        self.menu.append(reset_item)

        self.menu.show_all()

        # Pass C pointer of GtkMenu to libayatana-appindicator
        c_menu_ptr = ctypes.pythonapi.PyCapsule_GetPointer(self.menu.__gpointer__, None)
        libappindicator.app_indicator_set_menu(self.ind, c_menu_ptr)

        # Initial UI refresh
        self.sync_ui()

        # Poll for AC changes and state file changes every 1.5 seconds
        GLib.timeout_add_seconds(2, self.check_updates)

    def sync_ui(self):
        state = get_state()
        enabled = state.get("enabled", False)
        ac_online = is_ac_online()

        self._updating = True
        self.toggle_item.set_active(enabled)
        self._updating = False

        if not enabled:
            icon_name = b"preferences-system-symbolic"
            self.status_item.set_label("Status: Balanced (Off)")
        elif ac_online:
            icon_name = b"power-profile-performance-symbolic"
            self.status_item.set_label("Status: 100% Speed Turbo (AC)")
        else:
            icon_name = b"battery-charging-symbolic"
            self.status_item.set_label("Status: High Performance (Battery)")

        libappindicator.app_indicator_set_icon_full(self.ind, icon_name, b"Beast Mode Status")

    def check_updates(self) -> bool:
        curr_ac = is_ac_online()
        if curr_ac != self.last_ac_online:
            logging.info(f"AC status change: was {self.last_ac_online}, now {curr_ac}")
            self.last_ac_online = curr_ac
            state = get_state()
            if state.get("enabled", False):
                subprocess.run([str(ENGINE_BIN), "sync"], check=False)

        self.sync_ui()
        return True

    def on_toggle_clicked(self, widget):
        if self._updating:
            return
        is_active = widget.get_active()
        cmd = "on" if is_active else "off"
        logging.info(f"User toggled menu item to: {cmd}")
        subprocess.run([str(ENGINE_BIN), cmd], check=False)
        self.sync_ui()

    def on_open_settings(self, widget):
        logging.info("Opening Beast Mode Settings...")
        subprocess.Popen([str(APP_BIN)])

    def on_open_monitor(self, widget):
        logging.info("Opening Beast Mode with Monitor...")
        subprocess.Popen([str(APP_BIN), "--monitor"])

    def on_reset_defaults(self, widget):
        logging.info("Resetting defaults...")
        subprocess.run([str(ENGINE_BIN), "off"], check=False)
        self.sync_ui()


def main():
    logging.info("Starting Beast Mode Native Top Bar Indicator Service...")
    app = BeastModeIndicator()
    Gtk.main()


if __name__ == "__main__":
    main()
