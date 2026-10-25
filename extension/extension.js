/*
 * Beast Mode GNOME Shell Quick Settings Extension
 * For GNOME Shell 50+
 */

import GObject from 'gi://GObject';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as QuickSettings from 'resource:///org/gnome/shell/ui/quickSettings.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const STATE_FILE_PATH = GLib.build_filenamev([GLib.get_home_dir(), '.config', 'beast-mode', 'state.json']);
const ENGINE_BIN = GLib.build_filenamev([GLib.get_home_dir(), '.local', 'bin', 'beast-mode']);

const BeastQuickToggle = GObject.registerClass(
class BeastQuickToggle extends QuickSettings.QuickToggle {
    _init() {
        super._init({
            title: 'Beast Mode',
            subtitle: 'Off',
            iconName: 'weather-storm-symbolic',
            toggleMode: true,
        });

        this.connect('clicked', () => this._onClicked());
        this._initMonitor();
        this._syncState();
    }

    _onClicked() {
        try {
            // Asynchronously toggle beast-mode
            const proc = Gio.Subprocess.new(
                [ENGINE_BIN, 'toggle'],
                Gio.SubprocessFlags.NONE
            );
            proc.wait_async(null, () => {
                this._syncState();
            });
        } catch (e) {
            console.error(`[BeastMode] Failed to execute toggle: ${e}`);
        }
    }

    _initMonitor() {
        try {
            const file = Gio.File.new_for_path(STATE_FILE_PATH);
            const parent = file.get_parent();
            if (parent && !parent.query_exists(null)) {
                parent.make_directory_with_parents(null);
            }
            this._monitor = file.monitor_file(Gio.FileMonitorFlags.NONE, null);
            this._monitorId = this._monitor.connect('changed', () => {
                this._syncState();
            });
        } catch (e) {
            console.error(`[BeastMode] Failed to setup file monitor: ${e}`);
        }
    }

    _syncState() {
        try {
            const file = Gio.File.new_for_path(STATE_FILE_PATH);
            if (!file.query_exists(null)) {
                this.checked = false;
                this.subtitle = 'Off';
                this.iconName = 'preferences-system-symbolic';
                return;
            }

            file.load_contents_async(null, (source, res) => {
                try {
                    const [ok, contents] = source.load_contents_finish(res);
                    if (!ok) return;

                    const text = new TextDecoder().decode(contents);
                    const state = JSON.parse(text);

                    const enabled = Boolean(state.enabled);
                    const mode = state.mode || (enabled ? 'battery' : 'off');
                    const acOnline = Boolean(state.ac_online);

                    this.checked = enabled;

                    if (!enabled) {
                        this.subtitle = 'Off';
                        this.iconName = 'preferences-system-symbolic';
                    } else if (acOnline || mode === 'ac_turbo') {
                        this.subtitle = '100% Speed (AC)';
                        this.iconName = 'weather-storm-symbolic';
                    } else {
                        this.subtitle = 'Active (Battery)';
                        this.iconName = 'battery-charging-symbolic';
                    }
                } catch (err) {
                    console.error(`[BeastMode] Error parsing state file: ${err}`);
                }
            });
        } catch (e) {
            console.error(`[BeastMode] Error syncing state: ${e}`);
        }
    }

    destroy() {
        if (this._monitor && this._monitorId) {
            this._monitor.disconnect(this._monitorId);
            this._monitor.cancel();
            this._monitor = null;
        }
        super.destroy();
    }
});

export default class BeastModeExtension extends Extension {
    enable() {
        this._toggle = new BeastQuickToggle();
        // Add to QuickSettingsMenu grid (colSpan = 1 to fit standard dual-column tile grid)
        Main.panel.statusArea.quickSettings.menu.addItem(this._toggle, 1);
        
        // Also run a 5-second periodic refresh to catch any external power transitions
        this._timeoutId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 5, () => {
            if (this._toggle) {
                this._toggle._syncState();
            }
            return GLib.SOURCE_CONTINUE;
        });
    }

    disable() {
        if (this._timeoutId) {
            GLib.Source.remove(this._timeoutId);
            this._timeoutId = null;
        }
        if (this._toggle) {
            this._toggle.destroy();
            this._toggle = null;
        }
    }
}
