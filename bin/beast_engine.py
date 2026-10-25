#!/usr/bin/env python3
"""
Beast Mode Engine
High-performance system optimizer for HP Laptop (AMD Ryzen 5 5500U, Ubuntu 26.04)
Optimizes CPU, Wi-Fi, Storage, RAM, and desktop animations for heavy agentic workloads.
Supports granular toggle controls for every optimization subsystem.
"""

import os
import sys
import json
import time
import socket
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

CONFIG_DIR = Path.home() / ".config" / "beast-mode"
STATE_FILE = CONFIG_DIR / "state.json"
CONFIG_FILE = CONFIG_DIR / "config.json"
SNAPSHOT_FILE = CONFIG_DIR / "snapshot.json"
SOCKET_FILE = Path("/run/beast-mode.sock")

DEFAULT_CONFIG = {
    "opt_cpu_governor": True,          # Force performance scaling governor & EPP
    "opt_cpu_ac_turbo": True,          # 100% max clock boost on AC charger
    "opt_ram_compression": True,       # 8 GB zstd zram compressed RAM swap
    "opt_ram_compaction": True,        # Compact memory & drop stale caches
    "opt_wifi_low_latency": True,      # Disable 802.11 power saving
    "opt_disable_animations": True,    # Turn off GNOME desktop animations
    "opt_pause_indexers": True,        # Pause LocalSearch / Tracker file indexing
    "opt_pause_remote_desktop": True,  # Pause unused gnome-remote-desktop
    "opt_storage_io": True             # NVMe 2048KB read-ahead & dirty ratio tuning
}


def run_cmd(cmd: str) -> str:
    """Run a shell command and return stdout stripped."""
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False)
        return res.stdout.strip()
    except Exception as e:
        logging.error(f"Error running command '{cmd}': {e}")
        return ""


def send_notification(title: str, message: str, urgency: str = "normal", icon: str = "beast-mode"):
    """Send desktop notification via notify-send."""
    try:
        subprocess.run(
            ["notify-send", "-a", "Beast Mode", "-u", urgency, "-i", icon, title, message],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        logging.warning(f"Failed to send notification: {e}")


def is_ac_online() -> bool:
    """Check if AC power supply is connected."""
    acad_online = Path("/sys/class/power_supply/ACAD/online")
    if acad_online.exists():
        try:
            return acad_online.read_text().strip() == "1"
        except Exception:
            pass

    upower_out = run_cmd("upower -d | grep 'on-battery'")
    if "yes" in upower_out:
        return False
    elif "no" in upower_out:
        return True

    return False


def get_active_wifi_connections():
    """Get active Wi-Fi connections and their current powersave settings."""
    connections = []
    out = run_cmd("nmcli -t -f UUID,NAME,TYPE connection show --active")
    for line in out.splitlines():
        if not line:
            continue
        parts = line.split(":")
        if len(parts) >= 3 and parts[2] == "802-11-wireless":
            uuid, name = parts[0], parts[1]
            ps_val = run_cmd(f"nmcli -t -f 802-11-wireless.powersave connection show {uuid}")
            try:
                ps_int = int(ps_val.split(":")[1]) if ":" in ps_val else 0
            except Exception:
                ps_int = 0
            connections.append({"uuid": uuid, "name": name, "powersave": ps_int})
    return connections


def call_root_helper(command: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Communicate with root daemon over unix socket if available."""
    if not SOCKET_FILE.exists():
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(3.0)
            client.connect(str(SOCKET_FILE))
            client.sendall(json.dumps(command).encode("utf-8"))
            data = client.recv(4096)
            if data:
                return json.loads(data.decode("utf-8"))
    except Exception as e:
        logging.debug(f"Root helper not reachable: {e}")
    return None


class BeastEngine:
    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    def get_config(self) -> Dict[str, bool]:
        cfg = dict(DEFAULT_CONFIG)
        if CONFIG_FILE.exists():
            try:
                user_cfg = json.loads(CONFIG_FILE.read_text())
                cfg.update(user_cfg)
            except Exception as e:
                logging.error(f"Error reading config: {e}")
        return cfg

    def save_config(self, cfg: Dict[str, bool]):
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

    def set_granular_option(self, key: str, value: bool) -> bool:
        """Update a single granular option and apply/revert immediately if active."""
        cfg = self.get_config()
        if key not in DEFAULT_CONFIG:
            logging.warning(f"Unknown config key: {key}")
            return False

        cfg[key] = value
        self.save_config(cfg)
        logging.info(f"Granular setting '{key}' set to {value}")

        # If Beast Mode is currently running, apply or revert the individual feature on-the-fly
        if self.is_enabled():
            ac_online = is_ac_online()
            snapshot = self._load_snapshot()

            if key == "opt_cpu_governor":
                if value:
                    run_cmd("powerprofilesctl set performance")
                else:
                    orig = snapshot.get("power_profile", "balanced")
                    run_cmd(f"powerprofilesctl set {orig}")

            elif key == "opt_disable_animations":
                if value:
                    run_cmd("gsettings set org.gnome.desktop.interface enable-animations false")
                else:
                    orig = snapshot.get("enable_animations", True)
                    run_cmd(f"gsettings set org.gnome.desktop.interface enable-animations {'true' if orig else 'false'}")

            elif key == "opt_wifi_low_latency":
                for conn in get_active_wifi_connections():
                    ps = 2 if value else snapshot.get("wifi_connections", [{}])[0].get("powersave", 0)
                    run_cmd(f"nmcli connection modify {conn['uuid']} 802-11-wireless.powersave {ps}")

            elif key == "opt_pause_indexers":
                if value:
                    run_cmd("systemctl --user stop localsearch-3.service 2>/dev/null")
                else:
                    run_cmd("systemctl --user start localsearch-3.service 2>/dev/null")

            elif key == "opt_pause_remote_desktop":
                if value:
                    run_cmd("systemctl --user stop gnome-remote-desktop.service 2>/dev/null")
                else:
                    run_cmd("systemctl --user start gnome-remote-desktop.service 2>/dev/null")

            # Forward to root helper for kernel features (zram, compaction, I/O, AC turbo)
            call_root_helper({"action": "update_config", "config": cfg, "ac_online": ac_online})

        return True

    def is_enabled(self) -> bool:
        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text())
                return bool(data.get("enabled", False))
            except Exception:
                pass
        return False

    def get_state(self) -> Dict[str, Any]:
        if STATE_FILE.exists():
            try:
                return json.loads(STATE_FILE.read_text())
            except Exception:
                pass
        return {"enabled": False, "mode": "off", "ac_online": is_ac_online()}

    def _save_state(self, state: Dict[str, Any]):
        STATE_FILE.write_text(json.dumps(state, indent=2))

    def _load_snapshot(self) -> Dict[str, Any]:
        if SNAPSHOT_FILE.exists():
            try:
                return json.loads(SNAPSHOT_FILE.read_text())
            except Exception as e:
                logging.error(f"Failed to read snapshot: {e}")
        return {}

    def enable(self) -> bool:
        ac_online = is_ac_online()
        cfg = self.get_config()
        logging.info(f"Enabling Beast Mode (AC: {ac_online}, Config: {cfg})...")

        # 1. Capture snapshot of all subsystems if not already saved
        if not SNAPSHOT_FILE.exists():
            current_profile = run_cmd("powerprofilesctl get") or "balanced"
            current_animations = run_cmd("gsettings get org.gnome.desktop.interface enable-animations")
            anim_bool = True if current_animations.strip() == "true" else False
            wifi_conns = get_active_wifi_connections()

            paused_services = []
            if run_cmd("systemctl --user is-active localsearch-3.service") == "active":
                paused_services.append("localsearch-3.service")
            if run_cmd("systemctl --user is-active gnome-remote-desktop.service") == "active":
                paused_services.append("gnome-remote-desktop.service")

            snapshot = {
                "timestamp": time.time(),
                "power_profile": current_profile,
                "enable_animations": anim_bool,
                "wifi_connections": wifi_conns,
                "paused_services": paused_services
            }
            SNAPSHOT_FILE.write_text(json.dumps(snapshot, indent=2))
            logging.info("Saved baseline settings snapshot.")

        # 2. Granular: CPU performance profile
        if cfg.get("opt_cpu_governor", True):
            run_cmd("powerprofilesctl set performance")

        # 3. Granular: Disable GNOME animations
        if cfg.get("opt_disable_animations", True):
            run_cmd("gsettings set org.gnome.desktop.interface enable-animations false")

        # 4. Granular: Optimize active Wi-Fi connections
        if cfg.get("opt_wifi_low_latency", True):
            for conn in get_active_wifi_connections():
                run_cmd(f"nmcli connection modify {conn['uuid']} 802-11-wireless.powersave 2")
                logging.info(f"Disabled Wi-Fi power saving on {conn['name']}")

        # 5. Granular: Pause background daemons
        if cfg.get("opt_pause_indexers", True):
            run_cmd("systemctl --user stop localsearch-3.service 2>/dev/null")
        if cfg.get("opt_pause_remote_desktop", True):
            run_cmd("systemctl --user stop gnome-remote-desktop.service 2>/dev/null")

        # 6. Contact root helper with config for zram, compaction, storage I/O, and AC turbo
        root_resp = call_root_helper({"action": "enable", "ac_online": ac_online, "config": cfg})
        if root_resp and root_resp.get("status") == "ok":
            logging.info("Root helper applied kernel-level optimizations.")

        # 7. Update state
        mode = "ac_turbo" if (ac_online and cfg.get("opt_cpu_ac_turbo", True)) else "battery"
        state = {
            "enabled": True,
            "mode": mode,
            "ac_online": ac_online,
            "activated_at": time.time()
        }
        self._save_state(state)

        # 8. Notify user
        if ac_online and cfg.get("opt_cpu_ac_turbo", True):
            send_notification(
                "Beast Mode: 100% Speed Unlocked",
                "Charger connected. CPU at maximum clock speed, boost locked, RAM and Wi-Fi optimized.",
                urgency="normal"
            )
        else:
            send_notification(
                "Beast Mode: Active",
                "High performance active. Connect charger to unlock 100% turbo clock boost.",
                urgency="normal"
            )

        logging.info(f"Beast Mode enabled in {mode} mode.")
        return True

    def disable(self) -> bool:
        logging.info("Disabling Beast Mode and restoring original settings...")
        snapshot = self._load_snapshot()

        # 1. Restore power profile
        orig_profile = snapshot.get("power_profile", "balanced")
        run_cmd(f"powerprofilesctl set {orig_profile}")

        # 2. Restore GNOME animations
        orig_animations = snapshot.get("enable_animations", True)
        run_cmd(f"gsettings set org.gnome.desktop.interface enable-animations {'true' if orig_animations else 'false'}")

        # 3. Restore Wi-Fi power saving settings
        orig_conns = snapshot.get("wifi_connections", [])
        if orig_conns:
            for conn in orig_conns:
                run_cmd(f"nmcli connection modify {conn['uuid']} 802-11-wireless.powersave {conn.get('powersave', 0)}")
        else:
            for conn in get_active_wifi_connections():
                run_cmd(f"nmcli connection modify {conn['uuid']} 802-11-wireless.powersave 0")

        # 4. Restart paused background services
        paused_services = snapshot.get("paused_services", ["localsearch-3.service", "gnome-remote-desktop.service"])
        for srv in paused_services:
            run_cmd(f"systemctl --user start {srv} 2>/dev/null")

        # 5. Notify root helper to dismantle zram and restore sysctl
        call_root_helper({"action": "disable"})

        # 6. Clean up snapshot and update state
        if SNAPSHOT_FILE.exists():
            SNAPSHOT_FILE.unlink()

        state = {
            "enabled": False,
            "mode": "off",
            "ac_online": is_ac_online(),
            "deactivated_at": time.time()
        }
        self._save_state(state)

        # 7. Notify user
        send_notification(
            "Beast Mode: Disabled",
            "All hardware, Wi-Fi, animations, and background services restored to baseline state.",
            urgency="low"
        )

        logging.info("Beast Mode disabled and original state restored.")
        return True

    def toggle(self) -> bool:
        if self.is_enabled():
            return self.disable()
        else:
            return self.enable()

    def sync_ac_status(self):
        """Called when AC adapter plug/unplug event occurs."""
        if not self.is_enabled():
            return

        ac_online = is_ac_online()
        state = self.get_state()
        prev_ac = state.get("ac_online", False)
        cfg = self.get_config()

        if ac_online != prev_ac:
            logging.info(f"AC status changed: online={ac_online}")
            mode = "ac_turbo" if (ac_online and cfg.get("opt_cpu_ac_turbo", True)) else "battery"
            state["mode"] = mode
            state["ac_online"] = ac_online
            self._save_state(state)

            call_root_helper({"action": "update_ac", "ac_online": ac_online})

            if ac_online:
                send_notification(
                    "Charger Connected: 100% Speed Unlocked",
                    "Beast Mode detected AC power. All Ryzen cores operating at 100% capacity.",
                    urgency="normal"
                )
            else:
                send_notification(
                    "Charger Disconnected: Switched to Battery Mode",
                    "Running high-performance battery profile with active power balancing.",
                    urgency="low"
                )

    def get_hardware_status(self) -> Dict[str, Any]:
        """Fetch real-time hardware status metrics."""
        ac_online = is_ac_online()
        profile = run_cmd("powerprofilesctl get") or "balanced"
        animations = run_cmd("gsettings get org.gnome.desktop.interface enable-animations") == "true"
        cfg = self.get_config()

        # CPU Frequencies across all cores
        cpu_freqs = []
        try:
            for i in range(12):
                f_path = Path(f"/sys/devices/system/cpu/cpu{i}/cpufreq/scaling_cur_freq")
                if f_path.exists():
                    khz = int(f_path.read_text().strip())
                    cpu_freqs.append(round(khz / 1000.0, 1))
        except Exception:
            pass

        # Memory usage
        mem_info = {}
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        k = parts[0].strip()
                        v = parts[1].strip().split()[0]
                        mem_info[k] = int(v)
            total_mb = mem_info.get("MemTotal", 0) // 1024
            avail_mb = mem_info.get("MemAvailable", 0) // 1024
            used_mb = total_mb - avail_mb
            swap_total_mb = mem_info.get("SwapTotal", 0) // 1024
            swap_free_mb = mem_info.get("SwapFree", 0) // 1024
            swap_used_mb = swap_total_mb - swap_free_mb
        except Exception:
            total_mb = used_mb = swap_total_mb = swap_used_mb = 0

        wifi_ps = run_cmd("iw dev wlo1 get power_save 2>/dev/null")
        root_status = call_root_helper({"action": "status"})

        return {
            "enabled": self.is_enabled(),
            "mode": "ac_turbo" if (self.is_enabled() and ac_online and cfg.get("opt_cpu_ac_turbo", True)) else ("battery" if self.is_enabled() else "off"),
            "ac_online": ac_online,
            "power_profile": profile,
            "animations": animations,
            "cpu_freqs_mhz": cpu_freqs,
            "memory": {
                "total_mb": total_mb,
                "used_mb": used_mb,
                "swap_total_mb": swap_total_mb,
                "swap_used_mb": swap_used_mb
            },
            "wifi_power_save": wifi_ps,
            "root_helper_active": bool(root_status and root_status.get("status") == "ok"),
            "zram_active": bool(root_status and root_status.get("zram_enabled", False)),
            "config": cfg
        }


def monitor_daemon():
    """Background listener for AC power changes and state synchronization."""
    logging.info("Starting Beast Mode AC Monitor Daemon...")
    engine = BeastEngine()
    prev_ac = is_ac_online()

    while True:
        try:
            curr_ac = is_ac_online()
            if curr_ac != prev_ac:
                logging.info(f"AC event detected: was {prev_ac}, now {curr_ac}")
                engine.sync_ac_status()
                prev_ac = curr_ac
            time.sleep(1.5)
        except KeyboardInterrupt:
            break
        except Exception as e:
            logging.error(f"Error in monitor loop: {e}")
            time.sleep(3.0)


def main():
    if len(sys.argv) < 2:
        print("Usage: beast-mode [on|off|toggle|sync|status|config|monitor]")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    engine = BeastEngine()

    if cmd in ("on", "enable"):
        engine.enable()
    elif cmd in ("off", "disable"):
        engine.disable()
    elif cmd in ("toggle", "switch"):
        engine.toggle()
    elif cmd in ("sync", "update"):
        engine.sync_ac_status()
    elif cmd == "status":
        status = engine.get_hardware_status()
        print(json.dumps(status, indent=2))
    elif cmd == "config":
        if len(sys.argv) == 2:
            print(json.dumps(engine.get_config(), indent=2))
        elif len(sys.argv) == 4:
            key = sys.argv[2]
            val = sys.argv[3].lower() in ("true", "1", "yes", "on")
            engine.set_granular_option(key, val)
            print(json.dumps({key: val}, indent=2))
        else:
            print("Usage: beast-mode config [key] [true|false]")
    elif cmd == "monitor":
        monitor_daemon()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
