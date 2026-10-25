#!/usr/bin/env python3
"""
Beast Mode Settings Application
Modern Libadwaita / GTK4 settings interface matching GNOME Settings.
Provides granular toggle controls for every subsystem optimization
and an optional lightweight real-time system resources monitor.
"""

import os
import sys
import json
import time
import subprocess
from pathlib import Path

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio

ENGINE_PATH = Path("/home/explorer01/.local/bin/beast-mode")
CONFIG_PATH = Path.home() / ".config" / "beast-mode" / "config.json"


def run_engine_cmd(args: list) -> dict:
    try:
        res = subprocess.run([str(ENGINE_PATH)] + args, capture_output=True, text=True, check=False)
        out = res.stdout.strip()
        if out.startswith("{"):
            return json.loads(out)
    except Exception as e:
        print(f"Engine call failed {args}: {e}")
    return {}


class CPUTracker:
    def __init__(self):
        self.last_idle = 0
        self.last_total = 0

    def get_cpu_percent(self) -> float:
        try:
            with open("/proc/stat") as f:
                fields = [int(x) for x in f.readline().split()[1:]]
                idle = fields[3] + fields[4]
                total = sum(fields)
                if self.last_total == 0:
                    self.last_idle = idle
                    self.last_total = total
                    return 0.0
                diff_idle = idle - self.last_idle
                diff_total = total - self.last_total
                self.last_idle = idle
                self.last_total = total
                if diff_total > 0:
                    usage = (1.0 - (diff_idle / diff_total)) * 100.0
                    return max(0.0, min(100.0, round(usage, 1)))
        except Exception:
            pass
        return 0.0


class NetTracker:
    def __init__(self, iface="wlo1"):
        self.iface = iface
        self.last_rx = 0
        self.last_tx = 0
        self.last_time = time.time()

    def get_rates(self) -> tuple:
        rx_rate = 0.0
        tx_rate = 0.0
        now = time.time()
        try:
            with open("/proc/net/dev") as f:
                for line in f:
                    if self.iface in line:
                        stats = line.split(":")[1].split()
                        rx = int(stats[0])
                        tx = int(stats[8])
                        if self.last_rx > 0:
                            dt = max(0.2, now - self.last_time)
                            rx_rate = (rx - self.last_rx) / (1024.0 * dt)
                            tx_rate = (tx - self.last_tx) / (1024.0 * dt)
                        self.last_rx = rx
                        self.last_tx = tx
                        self.last_time = now
                        break
        except Exception:
            pass
        return (round(rx_rate, 1), round(tx_rate, 1))


def get_disk_usage() -> tuple:
    try:
        st = os.statvfs("/")
        total_gb = (st.f_blocks * st.f_frsize) / (1024**3)
        free_gb = (st.f_bavail * st.f_frsize) / (1024**3)
        used_gb = total_gb - free_gb
        pct = (used_gb / total_gb) * 100.0 if total_gb > 0 else 0
        return (round(used_gb, 1), round(total_gb, 1), round(pct, 1))
    except Exception:
        return (0.0, 0.0, 0.0)


class BeastModeWindow(Adw.ApplicationWindow):
    def __init__(self, show_monitor_initial=False, **kwargs):
        super().__init__(**kwargs)
        self.set_title("Beast Mode Settings")
        self.set_default_size(740, 840)

        self._updating = False
        self.switches = {}
        self.cpu_tracker = CPUTracker()
        self.net_tracker = NetTracker("wlo1")

        # Main layout
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(self.main_box)

        # Header bar
        header = Adw.HeaderBar()
        self.main_box.append(header)

        # Toast overlay for notifications
        self.toast_overlay = Adw.ToastOverlay()
        self.main_box.append(self.toast_overlay)

        # Scrolled content window
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        self.toast_overlay.set_child(scrolled)

        # Clamp for Adwaita centered layout
        clamp = Adw.Clamp()
        clamp.set_maximum_size(700)
        clamp.set_margin_top(18)
        clamp.set_margin_bottom(24)
        clamp.set_margin_start(16)
        clamp.set_margin_end(16)
        scrolled.set_child(clamp)

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        clamp.set_child(content_box)

        # 1. HERO STATUS BANNER
        self.hero_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.hero_card.set_margin_bottom(8)
        self.hero_card.add_css_class("card")
        self.hero_card.set_size_request(-1, 140)

        hero_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        hero_inner.set_margin_top(16)
        hero_inner.set_margin_bottom(16)
        hero_inner.set_margin_start(20)
        hero_inner.set_margin_end(20)

        self.hero_icon = Gtk.Image()
        self.hero_icon.set_pixel_size(54)
        hero_inner.append(self.hero_icon)

        hero_text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        hero_text_box.set_valign(Gtk.Align.CENTER)
        hero_inner.append(hero_text_box)

        self.hero_title = Gtk.Label()
        self.hero_title.set_halign(Gtk.Align.START)
        self.hero_title.add_css_class("title-2")
        hero_text_box.append(self.hero_title)

        self.hero_subtitle = Gtk.Label()
        self.hero_subtitle.set_halign(Gtk.Align.START)
        self.hero_subtitle.set_wrap(True)
        self.hero_subtitle.add_css_class("body")
        self.hero_subtitle.add_css_class("dim-label")
        hero_text_box.append(self.hero_subtitle)

        self.hero_card.append(hero_inner)
        content_box.append(self.hero_card)

        # 2. MASTER TOGGLE GROUP
        master_group = Adw.PreferencesGroup()
        master_group.set_title("Master Control")
        master_group.set_description("Instantly prepare your laptop for heavy agentic tasks, compiling, and AI workloads.")

        self.master_switch_row = Adw.SwitchRow()
        self.master_switch_row.set_title("Beast Mode")
        self.master_switch_row.set_subtitle("Applies all enabled optimizations below and eliminates desktop latency")
        self.master_switch_row.set_icon_name("weather-storm-symbolic")
        self.master_switch_row.connect("notify::active", self.on_master_toggle)
        master_group.add(self.master_switch_row)
        content_box.append(master_group)

        # 3. LIVE SYSTEM RESOURCES MONITOR (VIEW / HIDE TOGGLE)
        monitor_control_group = Adw.PreferencesGroup()
        monitor_control_group.set_title("System Monitor Controls")

        self.monitor_toggle_row = Adw.SwitchRow()
        self.monitor_toggle_row.set_title("System Resources Monitor")
        self.monitor_toggle_row.set_subtitle("Show live CPU utilization, clock frequencies, RAM, NVMe I/O, and Wi-Fi throughput")
        self.monitor_toggle_row.set_icon_name("utilities-system-monitor-symbolic")
        self.monitor_toggle_row.connect("notify::active", self.on_monitor_toggle)
        monitor_control_group.add(self.monitor_toggle_row)
        content_box.append(monitor_control_group)

        # THE MONITOR CARD (Collapsible)
        self.monitor_group = Adw.PreferencesGroup()
        self.monitor_group.set_title("Live System Resources")
        self.monitor_group.set_description("Real-time telemetry updated every 1.5 seconds.")

        # Monitor: CPU Row
        self.mon_cpu_row = Adw.ActionRow()
        self.mon_cpu_row.set_title("CPU Utilization (AMD Ryzen 5 5500U)")
        self.mon_cpu_row.set_icon_name("cpu-symbolic")
        cpu_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        cpu_box.set_valign(Gtk.Align.CENTER)
        self.cpu_progress = Gtk.ProgressBar()
        self.cpu_progress.set_size_request(160, -1)
        self.cpu_pct_label = Gtk.Label(label="0.0%")
        self.cpu_pct_label.set_halign(Gtk.Align.END)
        self.cpu_pct_label.add_css_class("caption")
        cpu_box.append(self.cpu_progress)
        cpu_box.append(self.cpu_pct_label)
        self.mon_cpu_row.add_suffix(cpu_box)
        self.monitor_group.add(self.mon_cpu_row)

        # Monitor: CPU Clock Frequencies Detail
        self.mon_freq_row = Adw.ActionRow()
        self.mon_freq_row.set_title("Ryzen Core Clocks (12 Threads)")
        self.mon_freq_row.set_subtitle("Fetching clock speeds...")
        self.mon_freq_row.set_icon_name("speedometer-symbolic")
        self.mon_boost_badge = Gtk.Label(label="Boost Active")
        self.mon_boost_badge.add_css_class("pill")
        self.mon_freq_row.add_suffix(self.mon_boost_badge)
        self.monitor_group.add(self.mon_freq_row)

        # Monitor: Memory (RAM) Row
        self.mon_mem_row = Adw.ActionRow()
        self.mon_mem_row.set_title("Physical RAM Utilization")
        self.mon_mem_row.set_icon_name("drive-multidisk-symbolic")
        mem_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        mem_box.set_valign(Gtk.Align.CENTER)
        self.mem_progress = Gtk.ProgressBar()
        self.mem_progress.set_size_request(160, -1)
        self.mem_pct_label = Gtk.Label(label="0.0 / 0.0 GB")
        self.mem_pct_label.set_halign(Gtk.Align.END)
        self.mem_pct_label.add_css_class("caption")
        mem_box.append(self.mem_progress)
        mem_box.append(self.mem_pct_label)
        self.mon_mem_row.add_suffix(mem_box)
        self.monitor_group.add(self.mon_mem_row)

        # Monitor: Swap and Compression Row
        self.mon_swap_row = Adw.ActionRow()
        self.mon_swap_row.set_title("Swap and Compression (zram)")
        self.mon_swap_row.set_icon_name("media-flash-symbolic")
        self.mon_swap_badge = Gtk.Label(label="zram active")
        self.mon_swap_badge.add_css_class("pill")
        self.mon_swap_row.add_suffix(self.mon_swap_badge)
        self.monitor_group.add(self.mon_swap_row)

        # Monitor: Storage NVMe I/O Row
        self.mon_disk_row = Adw.ActionRow()
        self.mon_disk_row.set_title("NVMe SSD Storage (KIOXIA 256GB)")
        self.mon_disk_row.set_icon_name("drive-harddisk-symbolic")
        disk_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        disk_box.set_valign(Gtk.Align.CENTER)
        self.disk_progress = Gtk.ProgressBar()
        self.disk_progress.set_size_request(160, -1)
        self.disk_pct_label = Gtk.Label(label="0 GB Used")
        self.disk_pct_label.set_halign(Gtk.Align.END)
        self.disk_pct_label.add_css_class("caption")
        disk_box.append(self.disk_progress)
        disk_box.append(self.disk_pct_label)
        self.mon_disk_row.add_suffix(disk_box)
        self.monitor_group.add(self.mon_disk_row)

        # Monitor: Wi-Fi Throughput Row
        self.mon_net_row = Adw.ActionRow()
        self.mon_net_row.set_title("Wi-Fi Throughput (RTL8822CE)")
        self.mon_net_row.set_icon_name("network-wireless-symbolic")
        self.mon_net_badge = Gtk.Label(label="RX: 0 KB/s | TX: 0 KB/s")
        self.mon_net_badge.add_css_class("pill")
        self.mon_net_row.add_suffix(self.mon_net_badge)
        self.monitor_group.add(self.mon_net_row)

        content_box.append(self.monitor_group)

        # 4. GRANULAR OPTIMIZATION CONTROLS GROUP
        granular_group = Adw.PreferencesGroup()
        granular_group.set_title("Granular Optimization Controls")
        granular_group.set_description("Fine-tune exactly which hardware and system components Beast Mode optimizes.")

        granular_items = [
            (
                "opt_cpu_governor",
                "CPU Performance Governor",
                "Force AMD Ryzen 5 cores to 'performance' scaling governor and high-power EPP",
                "cpu-symbolic"
            ),
            (
                "opt_cpu_ac_turbo",
                "100% Speed Turbo on AC",
                "Lock maximum 4.05 GHz clock capacity without idle downclocking when charger is connected",
                "weather-storm-symbolic"
            ),
            (
                "opt_ram_compression",
                "RAM Compression (8 GB zram)",
                "Allocate fast zstd in-RAM compressed swap to expand memory and prevent disk thrashing",
                "drive-multidisk-symbolic"
            ),
            (
                "opt_ram_compaction",
                "Memory Compaction and Cache Trimming",
                "Defragment memory pages and purge inactive buffers before heavy tasks",
                "view-refresh-symbolic"
            ),
            (
                "opt_wifi_low_latency",
                "Low-Latency Wi-Fi Mode",
                "Disable 802.11 power saving on Realtek RTL8822CE to eliminate latency jitter",
                "network-wireless-symbolic"
            ),
            (
                "opt_disable_animations",
                "Disable Desktop Animations",
                "Turn off GNOME Shell and window animations for zero-latency response",
                "video-display-symbolic"
            ),
            (
                "opt_pause_indexers",
                "Pause File Indexer (Tracker / LocalSearch)",
                "Suspend background disk indexing during heavy compilation and agent runs",
                "system-search-symbolic"
            ),
            (
                "opt_pause_remote_desktop",
                "Pause Remote Desktop Service",
                "Suspend unused gnome-remote-desktop to reclaim ~120 MB RAM",
                "network-server-symbolic"
            ),
            (
                "opt_storage_io",
                "NVMe Storage I/O Tuning",
                "Boost read-ahead buffer to 2048 KB and tune kernel dirty page ratios",
                "drive-harddisk-symbolic"
            ),
        ]

        for key, title, subtitle, icon in granular_items:
            row = Adw.SwitchRow()
            row.set_title(title)
            row.set_subtitle(subtitle)
            row.set_icon_name(icon)
            row.connect("notify::active", self.create_granular_callback(key, title))
            granular_group.add(row)
            self.switches[key] = row

        content_box.append(granular_group)

        # 5. MAINTENANCE AND RECOVERY GROUP
        action_group = Adw.PreferencesGroup()
        action_group.set_title("Maintenance and Recovery")

        revert_row = Adw.ActionRow()
        revert_row.set_title("Reset to Baseline Defaults")
        revert_row.set_subtitle("Safely disable Beast Mode and restore original system settings")
        revert_btn = Gtk.Button(label="Reset Defaults")
        revert_btn.set_valign(Gtk.Align.CENTER)
        revert_btn.add_css_class("destructive-action")
        revert_btn.connect("clicked", self.on_revert_clicked)
        revert_row.add_suffix(revert_btn)
        action_group.add(revert_row)

        content_box.append(action_group)

        # Load persisted monitor visibility preference
        monitor_visible = show_monitor_initial
        if CONFIG_PATH.exists():
            try:
                cfg = json.loads(CONFIG_PATH.read_text())
                if "show_resource_monitor" in cfg:
                    monitor_visible = bool(cfg["show_resource_monitor"])
            except Exception:
                pass

        self._updating = True
        self.monitor_toggle_row.set_active(monitor_visible)
        self.monitor_group.set_visible(monitor_visible)
        self._updating = False

        # Initial refresh
        self.refresh_ui()

        # Update live metrics every 1.5 seconds
        GLib.timeout_add_seconds(1, self.refresh_ui)

    def on_monitor_toggle(self, switch_row, param):
        if self._updating:
            return
        is_active = switch_row.get_active()
        self.monitor_group.set_visible(is_active)
        # Persist preference
        try:
            cfg = {}
            if CONFIG_PATH.exists():
                cfg = json.loads(CONFIG_PATH.read_text())
            cfg["show_resource_monitor"] = is_active
            CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
        except Exception as e:
            print(f"Error saving monitor preference: {e}")

        toast_text = "System Monitor Displayed" if is_active else "System Monitor Hidden"
        self.toast_overlay.add_toast(Adw.Toast.new(toast_text))

    def create_granular_callback(self, key: str, title: str):
        def callback(switch_row, param):
            if self._updating:
                return
            is_active = switch_row.get_active()
            val_str = "true" if is_active else "false"
            run_engine_cmd(["config", key, val_str])
            status_text = "Enabled" if is_active else "Disabled"
            toast = Adw.Toast.new(f"{title}: {status_text}")
            self.toast_overlay.add_toast(toast)
            self.refresh_ui()
        return callback

    def refresh_ui(self) -> bool:
        """Fetch current hardware status and update widgets."""
        status = run_engine_cmd(["status"])
        if not status:
            return True

        enabled = status.get("enabled", False)
        mode = status.get("mode", "off")
        ac_online = status.get("ac_online", False)
        profile = status.get("power_profile", "balanced")
        freqs = status.get("cpu_freqs_mhz", [])
        mem = status.get("memory", {})
        zram_active = status.get("zram_active", False)
        cfg = status.get("config", {})

        # Prevent recursion during switch notify
        self._updating = True
        self.master_switch_row.set_active(enabled)

        # Update granular switches from config
        for key, switch in self.switches.items():
            if key in cfg:
                switch.set_active(bool(cfg[key]))

        self._updating = False

        # Update Hero Banner
        if not enabled:
            self.hero_icon.set_from_icon_name("preferences-system-symbolic")
            self.hero_title.set_text("Beast Mode: Disabled")
            self.hero_subtitle.set_text("Laptop running under standard balanced profile with desktop animations enabled.")
            self.hero_card.remove_css_class("accent")
            self.hero_card.remove_css_class("warning")
            self.hero_card.remove_css_class("error")
        elif ac_online and cfg.get("opt_cpu_ac_turbo", True):
            self.hero_icon.set_from_icon_name("power-profile-performance-symbolic")
            self.hero_title.set_text("Beast Mode: 100% Speed (AC Connected)")
            self.hero_subtitle.set_text("Charger connected. All 12 Ryzen CPU threads running at maximum clock capacity without thermal throttling.")
            self.hero_card.remove_css_class("accent")
            self.hero_card.remove_css_class("warning")
            self.hero_card.add_css_class("error")
        else:
            self.hero_icon.set_from_icon_name("battery-charging-symbolic")
            self.hero_title.set_text("Beast Mode: Active (Battery)")
            self.hero_subtitle.set_text("High performance active. Connect charger to unlock 100% turbo clock speeds.")
            self.hero_card.remove_css_class("error")
            self.hero_card.remove_css_class("accent")
            self.hero_card.add_css_class("warning")

        # ------------------- UPDATE MONITOR TELEMETRY -------------------
        if self.monitor_group.get_visible():
            # CPU Usage
            cpu_pct = self.cpu_tracker.get_cpu_percent()
            self.cpu_progress.set_fraction(cpu_pct / 100.0)
            self.cpu_pct_label.set_text(f"{cpu_pct}% Usage")
            self.mon_cpu_row.set_subtitle(f"Overall CPU Load: {cpu_pct}% | Governor: {profile.capitalize()}")

            # Core Frequencies Detail
            if freqs:
                avg_freq = round(sum(freqs) / len(freqs), 0)
                max_freq = max(freqs)
                min_freq = min(freqs)
                self.mon_freq_row.set_subtitle(
                    f"Peak: {max_freq} MHz | Avg: {avg_freq} MHz | Floor: {min_freq} MHz"
                )
                if enabled and ac_online and cfg.get("opt_cpu_ac_turbo", True):
                    self.mon_boost_badge.set_text("100% Turbo")
                elif enabled:
                    self.mon_boost_badge.set_text("Performance")
                else:
                    self.mon_boost_badge.set_text("Balanced")

            # RAM Usage
            tot_mb = mem.get("total_mb", 1)
            used_mb = mem.get("used_mb", 0)
            ram_pct = (used_mb / tot_mb) * 100.0 if tot_mb > 0 else 0
            self.mem_progress.set_fraction(min(1.0, ram_pct / 100.0))
            self.mem_pct_label.set_text(f"{round(used_mb/1024, 1)} / {round(tot_mb/1024, 1)} GB ({round(ram_pct, 1)}%)")
            self.mon_mem_row.set_subtitle(f"Used: {round(used_mb/1024, 1)} GB of {round(tot_mb/1024, 1)} GB Total RAM")

            # Swap and Compression
            swap_tot = mem.get("swap_total_mb", 0)
            swap_used = mem.get("swap_used_mb", 0)
            z_status = "zram 8GB Active" if zram_active else "NVMe Disk Swap"
            self.mon_swap_row.set_subtitle(f"Swap Used: {swap_used} MB of {swap_tot} MB | Compression: {z_status}")
            self.mon_swap_badge.set_text(f"{swap_used} MB / {swap_tot} MB")

            # NVMe Storage
            used_disk, tot_disk, disk_pct = get_disk_usage()
            self.disk_progress.set_fraction(disk_pct / 100.0)
            self.disk_pct_label.set_text(f"{used_disk} / {tot_disk} GB ({disk_pct}%)")
            ra_kb = "2048 KB (Optimized)" if (enabled and cfg.get("opt_storage_io", True)) else "128 KB"
            self.mon_disk_row.set_subtitle(f"Root Partition: {disk_pct}% Used | Read-Ahead Buffer: {ra_kb}")

            # Wi-Fi Throughput
            rx_rate, tx_rate = self.net_tracker.get_rates()
            wf_mode = "Low-Latency (Power Save Off)" if (enabled and cfg.get("opt_wifi_low_latency", True)) else "Power Save On"
            self.mon_net_row.set_subtitle(f"Network: wlo1 | Mode: {wf_mode}")
            self.mon_net_badge.set_text(f"RX: {rx_rate} KB/s | TX: {tx_rate} KB/s")

        return True

    def on_master_toggle(self, switch_row, param):
        if self._updating:
            return
        is_active = switch_row.get_active()
        cmd = "on" if is_active else "off"
        run_engine_cmd([cmd])
        
        toast = Adw.Toast.new(f"Beast Mode {'Enabled' if is_active else 'Disabled'}")
        self.toast_overlay.add_toast(toast)
        self.refresh_ui()

    def on_revert_clicked(self, button):
        run_engine_cmd(["off"])
        toast = Adw.Toast.new("System successfully restored to baseline defaults!")
        self.toast_overlay.add_toast(toast)
        self.refresh_ui()


class BeastModeApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="org.laptop.beastmode", flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.show_monitor_arg = False

    def do_command_line(self, command_line):
        args = command_line.get_arguments()
        self.show_monitor_arg = "--monitor" in args or "-m" in args
        self.activate()
        return 0

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = BeastModeWindow(show_monitor_initial=self.show_monitor_arg, application=self)
        win.present()


def main():
    app = BeastModeApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
