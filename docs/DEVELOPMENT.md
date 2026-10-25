# Beast Mode Developer Guide and Contributing Context

## 1. Prerequisites and Development Environment

### 1.1 Required System Dependencies
The Beast Mode project requires a standard Ubuntu 26.04+ desktop installation with GNOME. Ensure the following system libraries and runtime components are installed:

```bash
sudo apt update
sudo apt install -y \
    python3 \
    python3-gi \
    gir1.2-gtk-4.0 \
    gir1.2-adw-1 \
    gir1.2-gtk-3.0 \
    libayatana-appindicator3-1 \
    power-profiles-daemon \
    network-manager \
    libnotify-bin
```

### 1.2 Python Runtime
- Beast Mode uses standard Python 3 with PyGObject (GObject Introspection).
- It relies entirely on standard Linux system libraries (`os`, `sys`, `json`, `subprocess`, `ctypes`, `socket`, `pathlib`) and does not require third-party PyPI packages.

---

## 2. Codebase Organization

```
/home/explorer01/hobby/beast-mode/
├── bin/
│   └── beast_engine.py          # Core engine, snapshot manager, CLI interface
├── app/
│   ├── beast_app.py             # Libadwaita / GTK4 Settings application
│   └── beast_indicator.py       # Standalone indicator implementation
├── daemon/
│   ├── beast_service.py         # Native Ayatana AppIndicator and AC listener daemon
│   ├── beast_root_helper.py     # Privileged kernel/sysfs/zram helper
│   ├── beast-mode-daemon.service # Systemd root service definition
│   └── install-root-helper.sh   # Root helper automated installer
├── extension/
│   ├── metadata.json            # GNOME Shell extension metadata
│   └── extension.js             # GNOME Shell ESM extension entrypoint
├── assets/
│   ├── beast-mode.svg           # Scalable application icon
│   └── beast-mode.desktop       # XDG desktop entry specification
├── docs/
│   ├── ARCHITECTURE.md          # In-depth system architecture & hardware analysis
│   └── DEVELOPMENT.md           # Developer guide and extension instructions
├── install.sh                   # User-space single-command installer
└── README.md                    # Primary repository overview
```

---

## 3. How to Add a New Granular Optimization Toggle

To introduce a new subsystem optimization (for example, `opt_fan_boost` or `opt_cpu_boost_limit`), follow these four steps:

### Step 1: Update Default Configuration in `bin/beast_engine.py`
Add the new key and its default boolean state to `DEFAULT_CONFIG`:

```python
DEFAULT_CONFIG = {
    ...
    "opt_new_feature": True,
}
```

### Step 2: Implement Dynamic Apply and Revert Logic in `bin/beast_engine.py`
Inside `set_granular_option()` and `enable()`, add handling for the feature:

```python
# In set_granular_option():
elif key == "opt_new_feature":
    if value:
        # Apply the optimization
        run_cmd("command_to_enable")
    else:
        # Revert to the snapshot value
        orig = snapshot.get("new_feature_baseline", default_val)
        run_cmd(f"command_to_restore {orig}")
```

Ensure any necessary baseline metrics are captured in `enable()` when writing `snapshot.json`.

### Step 3: Add the UI Switch Row in `app/beast_app.py`
Add a tuple entry to `granular_items` in `BeastModeWindow.__init__()`:

```python
(
    "opt_new_feature",
    "New Feature Display Name",
    "Clear, professional description of what this setting optimizes",
    "symbolic-icon-name"
),
```

The application will automatically bind the switch row, persist the configuration, and display dynamic toast feedback when toggled.

### Step 4 (Optional): Add Kernel / Sysfs Handlers in `daemon/beast_root_helper.py`
If the feature requires root privileges (e.g. sysctl or sysfs modification):
1. In `RootOptimizer.enable()`, check `config.get("opt_new_feature", True)`.
2. Save the original parameter value into `snapshot` before mutating.
3. In `RootOptimizer.disable()`, restore the original parameter value from `snapshot`.

---

## 4. Testing and Verification Procedures

### 4.1 End-to-End State Reversibility Test
Run the following test to verify clean activation and reversion:

```bash
# 1. Verify baseline state
beast-mode status

# 2. Activate Beast Mode
beast-mode on
powerprofilesctl get          # Expected: performance
gsettings get org.gnome.desktop.interface enable-animations # Expected: false

# 3. Deactivate Beast Mode
beast-mode off
powerprofilesctl get          # Expected: balanced
gsettings get org.gnome.desktop.interface enable-animations # Expected: true
ls ~/.config/beast-mode/snapshot.json # Expected: No such file (cleanly removed)
```

### 4.2 Dynamic Granular Toggle Test
Verify that changing a granular setting on-the-fly modifies only that subsystem without disturbing others:

```bash
beast-mode on
beast-mode config opt_disable_animations false
gsettings get org.gnome.desktop.interface enable-animations # Expected: true (restored on-the-fly)

beast-mode config opt_disable_animations true
gsettings get org.gnome.desktop.interface enable-animations # Expected: false (re-disabled)

beast-mode off
```

### 4.3 AppIndicator Menu Verification
Verify that the top panel indicator correctly exports its DBusMenu layout:

```bash
BUS_NAME=$(gdbus call --session --dest org.kde.StatusNotifierWatcher \
  --object-path /StatusNotifierWatcher \
  --method org.freedesktop.DBus.Properties.Get org.kde.StatusNotifierWatcher RegisteredStatusNotifierItems \
  | grep -o "':1.[0-9]*@/org/ayatana/NotificationItem/beast_mode_panel'" | tr -d "'" | cut -d'@' -f1)

gdbus call --session --dest "$BUS_NAME" \
  --object-path /org/ayatana/NotificationItem/beast_mode_panel/Menu \
  --method com.canonical.dbusmenu.GetLayout 0 2 "[]"
```

### 4.4 Monitoring Logs
Inspect the background monitor service logs in real time:

```bash
journalctl --user -u beast-mode-monitor.service -f
```

---

## 5. UI Guidelines and Design Standards

- **Typography & Formatting**: All labels, titles, and notifications must strictly adhere to professional system software standards. **Do not use emojis** in UI labels, badges, or notification text.
- **Pango Markup Caution**: In GTK4 / Libadwaita, labels parse Pango markup. Never use raw `&` characters in subtitles or titles without escaping them as `&amp;`, or use the word `and` instead.
- **Theme Consistency**: Use standard GNOME symbolic icons (`-symbolic`) to ensure seamless visual integration with Adwaita and Yaru icon themes across light and dark modes.

---

## 6. Future Development Roadmap

1. **AMD APU Power Limit Configuration (`ryzenadj`)**:
   - Implement support for dynamic Sustained Power Limit (STAPM), Fast Package Power Tracking (PPT), and Slow PPT adjustment on AC power.
   - On AC power with adequate cooling, the Ryzen 5 5500U can be elevated from 15W to 25W sustained TDP.
2. **Dynamic Fan Curve Enforcement via HP-WMI**:
   - Investigate `/sys/devices/platform/hp-wmi/hwmon` interfaces to allow proactive fan ramp-up prior to heavy agent executions, avoiding thermal throttling.
3. **cgroups v2 Task Prioritization (`beast-exec`)**:
   - Provide a CLI wrapper `beast-exec <command>` that launches user agent tasks inside a high-priority systemd scope with elevated CPU and I/O weights (`CPUWeight=200`, `IOWeight=200`).
4. **Battery Charge Threshold Control**:
   - Provide a toggle to limit battery charging to 80% when permanently connected to the AC adapter, extending battery lifespan during long developer desktop sessions.
