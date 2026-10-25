#!/usr/bin/env python3
"""
Beast Mode StatusNotifierItem (Tray / Top Bar Indicator)
Registers on org.kde.StatusNotifierWatcher so a toggle icon appears
directly in Ubuntu GNOME's top bar.
"""

import sys
import json
import subprocess
from pathlib import Path

from gi.repository import Gio, GLib

ENGINE_BIN = Path("/home/explorer01/.local/bin/beast-mode")
STATE_FILE = Path.home() / ".config" / "beast-mode" / "state.json"

INTROSPECTION_XML = """
<!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
"http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
<node>
  <interface name="org.kde.StatusNotifierItem">
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="WindowId" type="i" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconThemePath" type="s" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
    
    <method name="ContextMenu">
      <arg type="i" name="x" direction="in"/>
      <arg type="i" name="y" direction="in"/>
    </method>
    <method name="Activate">
      <arg type="i" name="x" direction="in"/>
      <arg type="i" name="y" direction="in"/>
    </method>
    <method name="SecondaryActivate">
      <arg type="i" name="x" direction="in"/>
      <arg type="i" name="y" direction="in"/>
    </method>
    <method name="Scroll">
      <arg type="i" name="delta" direction="in"/>
      <arg type="s" name="orientation" direction="in"/>
    </method>

    <signal name="NewTitle"/>
    <signal name="NewIcon"/>
    <signal name="NewAttentionIcon"/>
    <signal name="NewOverlayIcon"/>
    <signal name="NewToolTip"/>
    <signal name="NewStatus">
      <arg type="s" name="status"/>
    </signal>
  </interface>
</node>
"""


class BeastTrayIndicator:
    def __init__(self):
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.node_info = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION_XML)
        self.iface_info = self.node_info.interfaces[0]

        self.object_path = "/StatusNotifierItem"
        self.reg_id = self.bus.register_object(
            self.object_path,
            self.iface_info,
            self.handle_method_call,
            self.handle_get_property,
            None
        )

        # Register with StatusNotifierWatcher
        try:
            self.bus.call_sync(
                "org.kde.StatusNotifierWatcher",
                "/StatusNotifierWatcher",
                "org.kde.StatusNotifierWatcher",
                "RegisterStatusNotifierItem",
                GLib.Variant("(s)", (self.object_path,)),
                None,
                Gio.DBusCallFlags.NONE,
                -1,
                None
            )
            print("[Tray] Registered successfully with StatusNotifierWatcher!")
        except Exception as e:
            print(f"[Tray] Registration failed: {e}")

        # Watch state file for changes
        self.setup_file_monitor()

    def get_state(self):
        if STATE_FILE.exists():
            try:
                return json.loads(STATE_FILE.read_text())
            except Exception:
                pass
        return {"enabled": False, "mode": "off", "ac_online": False}

    def setup_file_monitor(self):
        try:
            file = Gio.File.new_for_path(str(STATE_FILE))
            parent = file.get_parent()
            if parent and not parent.query_exists(None):
                parent.make_directory_with_parents(None)
            self.monitor = file.monitor_file(Gio.FileMonitorFlags.NONE, None)
            self.monitor.connect("changed", self.on_state_file_changed)
        except Exception as e:
            print(f"[Tray] Monitor setup failed: {e}")

    def on_state_file_changed(self, monitor, file, other_file, event_type):
        self.emit_property_changes()

    def emit_property_changes(self):
        try:
            self.bus.emit_signal(
                None,
                self.object_path,
                "org.kde.StatusNotifierItem",
                "NewIcon",
                None
            )
            self.bus.emit_signal(
                None,
                self.object_path,
                "org.kde.StatusNotifierItem",
                "NewTitle",
                None
            )
            self.bus.emit_signal(
                None,
                self.object_path,
                "org.kde.StatusNotifierItem",
                "NewToolTip",
                None
            )
        except Exception as e:
            print(f"[Tray] Signal emit error: {e}")

    def handle_get_property(self, connection, sender, object_path, interface_name, property_name):
        state = self.get_state()
        enabled = state.get("enabled", False)
        ac_online = state.get("ac_online", False)

        if property_name == "Category":
            return GLib.Variant("s", "Hardware")
        elif property_name == "Id":
            return GLib.Variant("s", "beast-mode")
        elif property_name == "Title":
            if not enabled:
                return GLib.Variant("s", "Beast Mode: Off")
            elif ac_online:
                return GLib.Variant("s", "Beast Mode: 100% Speed (AC)")
            else:
                return GLib.Variant("s", "Beast Mode: Battery")
        elif property_name == "Status":
            return GLib.Variant("s", "Active")
        elif property_name == "WindowId":
            return GLib.Variant("i", 0)
        elif property_name == "IconName":
            if not enabled:
                return GLib.Variant("s", "preferences-system-symbolic")
            elif ac_online:
                return GLib.Variant("s", "weather-storm-symbolic")
            else:
                return GLib.Variant("s", "battery-charging-symbolic")
        elif property_name == "IconThemePath":
            return GLib.Variant("s", str(Path.home() / ".local/share/icons"))
        elif property_name == "Menu":
            return GLib.Variant("o", "/NO_DBUSMENU")
        elif property_name == "ItemIsMenu":
            return GLib.Variant("b", False)
        elif property_name == "ToolTip":
            sub = "All 12 cores 100% Speed" if ac_online else ("High performance" if enabled else "Balanced")
            return GLib.Variant("(sa(iiay)ss)", ("beast-mode", [], "Beast Mode", sub))

        return None

    def handle_method_call(self, connection, sender, object_path, interface_name, method_name, parameters, invocation):
        if method_name in ("Activate", "SecondaryActivate", "ContextMenu"):
            # Clicking the icon toggles Beast Mode!
            print(f"[Tray] {method_name} called: Toggling Beast Mode...")
            subprocess.run([str(ENGINE_BIN), "toggle"], check=False)
            self.emit_property_changes()
            invocation.return_value(None)
        elif method_name == "Scroll":
            invocation.return_value(None)
        else:
            invocation.return_value(None)


def main():
    print("Starting Beast Mode Top Bar Tray Indicator...")
    indicator = BeastTrayIndicator()
    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
