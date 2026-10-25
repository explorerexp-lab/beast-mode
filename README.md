# Beast Mode for Linux (AMD Ryzen 5 and Ubuntu GNOME)

Beast Mode is a high-performance system configuration manager engineered for this laptop (AMD Ryzen 5 5500U, 10 GiB RAM, NVMe SSD, Ubuntu 26.04 GNOME Wayland). It optimizes kernel, CPU, memory, storage, and networking parameters for compute-intensive workloads and agentic workflows, while ensuring complete reversibility to baseline settings upon deactivation.

---

## Core Capabilities

1. **Automatic 100% Speed Scaling on AC**:
   - Monitors the power supply in real time via UPower D-Bus.
   - When connected to AC power, locks AMD Core Performance Boost on and eliminates idle downclock latency, maintaining maximum clock throughput across all 12 threads (up to 4.05 GHz).
   - On battery, maintains a high-performance profile while balancing power consumption.
2. **Memory and Cache Management**:
   - Trims stale caches and runs memory compaction to reduce allocation latency.
   - Automatically pauses background indexing services (`localsearch-3`) and unused desktop daemons (`gnome-remote-desktop`) to preserve memory and I/O bandwidth.
   - Supports 8 GB `zram` compressed in-RAM swap (`zstd` algorithm) via the optional root helper daemon.
3. **Low-Latency Wi-Fi Optimization**:
   - Disables 802.11 power saving on the Realtek RTL8822CE wireless interface (`wlo1`).
   - Prevents radio sleep states to eliminate latency spikes during concurrent API requests, repository operations, and network transfers.
4. **Desktop Compositor Optimization**:
   - Disables GNOME Shell and window animations (`enable-animations false`).
   - Removes compositor render delays for instantaneous window and interface response.
5. **Reversibility Guarantee**:
   - Captures a state snapshot (`~/.config/beast-mode/snapshot.json`) prior to applying any modifications.
   - Disabling Beast Mode restores original power profiles, animation preferences, network configurations, and background services.

---

## Interfaces and Controls

### 1. Top Panel Indicator
The top panel menu item provides quick access to core controls:
- **Beast Mode [Checkbox]**: Toggle Beast Mode on or off.
- **Status Indicator**: Displays current operating mode (e.g. `Status: 100% Speed Turbo (AC)` or `Status: Balanced`).
- **Beast Mode Settings**: Launches the configuration application.
- **System Resources Monitor**: Opens the application focused on the resource monitor.
- **Reset to Baseline Defaults**: Reverts all settings to their original state.

### 2. Settings Application
Launchable from the application menu or terminal (`beast-mode-app`):
- **Master Switch**: Global toggle for Beast Mode.
- **Live System Resources Monitor**: Real-time telemetry displaying CPU load, 12-thread clock frequencies, physical RAM utilization, swap/zram metrics, NVMe storage usage, and network throughput. Includes a toggle to show or hide the monitor.
- **Granular Optimization Controls**: 9 independent switches to enable or disable specific optimizations:
  - CPU Performance Governor
  - 100% Speed Turbo on AC
  - RAM Compression (8 GB zram)
  - Memory Compaction and Cache Trimming
  - Low-Latency Wi-Fi Mode
  - Disable Desktop Animations
  - Pause File Indexer (Tracker / LocalSearch)
  - Pause Remote Desktop Service
  - NVMe Storage I/O Tuning
- **Maintenance**: Reset system configuration to baseline defaults.

### 3. Command Line Interface
```bash
# Toggle Beast Mode
beast-mode toggle

# Explicitly enable or disable
beast-mode on
beast-mode off

# View current configuration
beast-mode config

# Modify a granular setting
beast-mode config opt_disable_animations false
beast-mode config opt_ram_compression true

# View real-time hardware status
beast-mode status
```

---

## Optional: Root Supercharge Helper
All standard optimizations operate without root privileges. To enable kernel-level 8 GB `zram` swap and NVMe read-ahead tuning, run the installer:
```bash
sudo /home/explorer01/hobby/beast-mode/daemon/install-root-helper.sh
```

---

## Documentation and Technical Context

Detailed technical specifications and developer guidelines are maintained in the `docs/` directory:
- **[System Architecture and Hardware Context](docs/ARCHITECTURE.md)**: Deep dive into the AMD Ryzen 5 5500U, `amd-pstate-epp` driver, zram memory compression, Realtek RTL8822CE power saving, D-Bus protocols, and the Snapshot Reversibility protocol.
- **[Developer Guide and Extending Beast Mode](docs/DEVELOPMENT.md)**: Step-by-step instructions for adding new granular toggles, verification workflows, debugging logs, and future roadmap items.

---

## Directory Structure
```
/home/explorer01/hobby/beast-mode/
├── bin/
│   └── beast_engine.py          # State engine and CLI controller
├── app/
│   ├── beast_app.py             # Libadwaita / GTK4 settings interface
│   └── beast_indicator.py       # Indicator backend
├── daemon/
│   ├── beast_service.py         # Top panel indicator and AC monitor service
│   ├── beast_root_helper.py     # Kernel zram and sysfs helper
│   ├── beast-mode-daemon.service # Systemd root unit
│   └── install-root-helper.sh   # Root helper installer
├── extension/
│   ├── metadata.json            # GNOME Shell extension metadata
│   └── extension.js             # GNOME Shell extension entrypoint
├── docs/
│   ├── ARCHITECTURE.md          # In-depth architectural analysis
│   └── DEVELOPMENT.md           # Developer guide and contributing context
├── install.sh                   # User-space single-command installer
└── assets/
    ├── beast-mode.svg           # Application icon
    └── beast-mode.desktop       # Desktop entry file
```
