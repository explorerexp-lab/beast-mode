#!/usr/bin/env python3
"""
Beast Mode Root Helper Daemon
Runs with elevated privileges to manage kernel-level optimizations with granular controls:
- zram compressed memory swap (zstd, 8GB)
- Kernel VM swappiness & cache pressure tuning
- CPU scaling_min_freq locking on AC
- NVMe read-ahead tuning
- Wi-Fi hardware power-save toggle (iw)
- Memory compaction & cache trimming
"""

import os
import sys
import json
import socket
import logging
import subprocess
from pathlib import Path

SOCKET_PATH = "/run/beast-mode.sock"
BACKUP_FILE = "/run/beast-mode-root-snapshot.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [ROOT-DAEMON] %(message)s")


def run(cmd: str) -> str:
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False)
        return res.stdout.strip()
    except Exception as e:
        logging.error(f"Command failed '{cmd}': {e}")
        return ""


def read_sysfs(path: str) -> str:
    try:
        return Path(path).read_text().strip()
    except Exception:
        return ""


def write_sysfs(path: str, value: str):
    try:
        Path(path).write_text(str(value))
    except Exception as e:
        logging.warning(f"Could not write {value} to {path}: {e}")


class RootOptimizer:
    def __init__(self):
        self.zram_active = False

    def is_zram_enabled(self) -> bool:
        out = run("lsblk -o NAME,TYPE | grep -i zram0")
        return "zram0" in out

    def enable(self, ac_online: bool, config: dict = None) -> dict:
        config = config or {}
        logging.info(f"Enabling kernel-level optimizations (AC Online: {ac_online}, Config: {config})...")
        snapshot = {}

        # 1. Snapshot current kernel VM parameters if not already saved
        if not Path(BACKUP_FILE).exists():
            snapshot["swappiness"] = read_sysfs("/proc/sys/vm/swappiness")
            snapshot["vfs_cache_pressure"] = read_sysfs("/proc/sys/vm/vfs_cache_pressure")
            snapshot["read_ahead_kb"] = read_sysfs("/sys/block/nvme0n1/queue/read_ahead_kb")

            cpu_min_freqs = {}
            for i in range(12):
                p = f"/sys/devices/system/cpu/cpu{i}/cpufreq/scaling_min_freq"
                if Path(p).exists():
                    cpu_min_freqs[i] = read_sysfs(p)
            snapshot["cpu_min_freqs"] = cpu_min_freqs
            Path(BACKUP_FILE).write_text(json.dumps(snapshot, indent=2))

        # 2. Granular: RAM Compression (zram)
        if config.get("opt_ram_compression", True):
            if not self.is_zram_enabled():
                run("modprobe zram num_devices=1")
                run("zramctl /dev/zram0 --algorithm zstd --size 8G")
                run("mkswap -L zram0 /dev/zram0")
                run("swapon -p 100 /dev/zram0")
                logging.info("Created 8 GB zstd zram swap on /dev/zram0 (priority 100).")
            write_sysfs("/proc/sys/vm/swappiness", "100")
            write_sysfs("/proc/sys/vm/vfs_cache_pressure", "50")
            self.zram_active = True
        else:
            if self.is_zram_enabled():
                run("swapoff /dev/zram0 2>/dev/null")
                run("zramctl --reset /dev/zram0 2>/dev/null")
                self.zram_active = False

        # 3. Granular: Memory Compaction & Cache Trimming
        if config.get("opt_ram_compaction", True):
            write_sysfs("/proc/sys/vm/drop_caches", "3")
            write_sysfs("/proc/sys/vm/compact_memory", "1")

        # 4. Granular: Storage I/O
        if config.get("opt_storage_io", True):
            if Path("/sys/block/nvme0n1/queue/read_ahead_kb").exists():
                write_sysfs("/sys/block/nvme0n1/queue/read_ahead_kb", "2048")
        else:
            if Path("/sys/block/nvme0n1/queue/read_ahead_kb").exists():
                write_sysfs("/sys/block/nvme0n1/queue/read_ahead_kb", "128")

        # 5. Granular: Wi-Fi Hardware Power Saving
        if config.get("opt_wifi_low_latency", True):
            run("iw dev wlo1 set power_save off 2>/dev/null")
        else:
            run("iw dev wlo1 set power_save on 2>/dev/null")

        # 6. Granular: CPU AC Turbo
        if config.get("opt_cpu_ac_turbo", True):
            self.apply_ac_scaling(ac_online)
        else:
            self.apply_ac_scaling(False)

        return {"status": "ok", "zram_enabled": self.is_zram_enabled(), "ac_online": ac_online}

    def apply_ac_scaling(self, ac_online: bool):
        """Scale CPU clock floor based on AC connection."""
        if ac_online:
            logging.info("AC detected: Locking CPU minimum frequency at 2.1 GHz base clock.")
            write_sysfs("/sys/devices/system/cpu/cpufreq/boost", "1")
            for i in range(12):
                p = f"/sys/devices/system/cpu/cpu{i}/cpufreq/scaling_min_freq"
                if Path(p).exists():
                    write_sysfs(p, "2100000")  # 2.1 GHz base
        else:
            logging.info("Battery detected: Restoring standard idle frequency floor.")
            for i in range(12):
                p = f"/sys/devices/system/cpu/cpu{i}/cpufreq/scaling_min_freq"
                if Path(p).exists():
                    write_sysfs(p, "1113637")

    def disable(self) -> dict:
        logging.info("Restoring kernel-level settings to baseline...")

        if Path(BACKUP_FILE).exists():
            try:
                snap = json.loads(Path(BACKUP_FILE).read_text())
                if "swappiness" in snap:
                    write_sysfs("/proc/sys/vm/swappiness", snap["swappiness"])
                if "vfs_cache_pressure" in snap:
                    write_sysfs("/proc/sys/vm/vfs_cache_pressure", snap["vfs_cache_pressure"])
                if "read_ahead_kb" in snap and Path("/sys/block/nvme0n1/queue/read_ahead_kb").exists():
                    write_sysfs("/sys/block/nvme0n1/queue/read_ahead_kb", snap["read_ahead_kb"])
                if "cpu_min_freqs" in snap:
                    for i, freq in snap["cpu_min_freqs"].items():
                        write_sysfs(f"/sys/devices/system/cpu/cpu{i}/cpufreq/scaling_min_freq", str(freq))
                Path(BACKUP_FILE).unlink()
            except Exception as e:
                logging.error(f"Error restoring snapshot: {e}")
        else:
            write_sysfs("/proc/sys/vm/swappiness", "60")
            write_sysfs("/proc/sys/vm/vfs_cache_pressure", "100")
            if Path("/sys/block/nvme0n1/queue/read_ahead_kb").exists():
                write_sysfs("/sys/block/nvme0n1/queue/read_ahead_kb", "128")
            for i in range(12):
                p = f"/sys/devices/system/cpu/cpu{i}/cpufreq/scaling_min_freq"
                if Path(p).exists():
                    write_sysfs(p, "1113637")

        if self.is_zram_enabled():
            run("swapoff /dev/zram0 2>/dev/null")
            run("zramctl --reset /dev/zram0 2>/dev/null")
            self.zram_active = False
            logging.info("Dismantled zram swap device.")

        run("iw dev wlo1 set power_save on 2>/dev/null")
        return {"status": "ok", "zram_enabled": False}

    def status(self) -> dict:
        return {
            "status": "ok",
            "zram_enabled": self.is_zram_enabled(),
            "swappiness": read_sysfs("/proc/sys/vm/swappiness"),
            "vfs_cache_pressure": read_sysfs("/proc/sys/vm/vfs_cache_pressure"),
            "read_ahead_kb": read_sysfs("/sys/block/nvme0n1/queue/read_ahead_kb")
        }


def handle_client(conn, optimizer: RootOptimizer):
    try:
        data = conn.recv(4096)
        if not data:
            return
        req = json.loads(data.decode("utf-8"))
        action = req.get("action", "")

        if action == "enable":
            ac_online = req.get("ac_online", False)
            config = req.get("config", {})
            resp = optimizer.enable(ac_online, config)
        elif action == "disable":
            resp = optimizer.disable()
        elif action == "update_config":
            ac_online = req.get("ac_online", False)
            config = req.get("config", {})
            resp = optimizer.enable(ac_online, config)
        elif action == "update_ac":
            ac_online = req.get("ac_online", False)
            optimizer.apply_ac_scaling(ac_online)
            resp = {"status": "ok", "ac_online": ac_online}
        elif action == "status":
            resp = optimizer.status()
        else:
            resp = {"status": "error", "message": f"Unknown action {action}"}

        conn.sendall(json.dumps(resp).encode("utf-8"))
    except Exception as e:
        logging.error(f"Error handling client request: {e}")
    finally:
        conn.close()


def main():
    if os.geteuid() != 0:
        print("Error: beast_root_helper must run as root.")
        sys.exit(1)

    if os.path.exists(SOCKET_PATH):
        try:
            os.unlink(SOCKET_PATH)
        except OSError:
            pass

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET_PATH)
    os.chmod(SOCKET_PATH, 0o666)
    server.listen(5)
    logging.info(f"Root helper listening on {SOCKET_PATH}")

    optimizer = RootOptimizer()

    try:
        while True:
            conn, _ = server.accept()
            handle_client(conn, optimizer)
    except KeyboardInterrupt:
        pass
    finally:
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)


if __name__ == "__main__":
    main()
