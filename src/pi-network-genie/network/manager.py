import json
import os
import subprocess
from pathlib import Path


# Handles network-related behaviour for the host Raspberry Pi project.
# It stores the desired network mode, checks the current mode, and uses nmcli
# to switch between saved Wi-Fi networks and the device hotspot.


class NetworkManager:
    def __init__(
        self,
        settings_dir=None,
        hotspot_connection_name=None,
    ):
        if settings_dir is None:
            configured_settings_dir = os.environ.get("PI_NETWORK_GENIE_SETTINGS_DIR")
            settings_dir = (
                Path(configured_settings_dir)
                if configured_settings_dir
                else Path.home() / ".config" / "pi-network-genie"
            )

        if hotspot_connection_name is None:
            hotspot_connection_name = os.environ.get(
                "PI_NETWORK_GENIE_HOTSPOT_CONNECTION",
                "project-hotspot",
            )

        self.settings_dir = Path(settings_dir)
        self.settings_dir.mkdir(parents=True, exist_ok=True)

        self.network_mode_file = self.settings_dir / "network_mode.json"
        self.hotspot_connection_name = hotspot_connection_name

        self.network_modes = {
            "auto": "WiFi with hotspot fallback",
            "hotspot": "Hotspot only",
        }

    # Return selectable network options for the front end (webapp).
    def get_network_options(self):
        return {
            "modes": self.network_modes,
        }

    # Save the user's preferred network mode.
    # This does not itself switch network mode; it only updates the stored target.
    def update_network_settings(self, data):
        network_mode = {
            "mode": data.get("mode", "hotspot"),
        }

        with self.network_mode_file.open("w", encoding="utf-8") as file:
            json.dump(network_mode, file, indent=2)

        return network_mode

    # Load the saved network mode.
    # If nothing has been saved yet, default to hotspot mode so the device
    # remains directly accessible.
    def get_network_mode(self):
        if not self.network_mode_file.exists():
            return {"mode": "hotspot"}

        try:
            with self.network_mode_file.open("r", encoding="utf-8") as file:
                network_mode = json.load(file)
        except (OSError, json.JSONDecodeError):
            return {"mode": "hotspot"}

        return network_mode or {"mode": "hotspot"}

    # Check what network mode appears to be active right now.
    # This reads active NetworkManager connections via nmcli and makes a simple
    # judgement based on the active connection names.
    def get_current_network_mode(self):
        try:
            result = subprocess.run(
                ["nmcli", "-t", "-f", "NAME", "connection", "show", "--active"],
                capture_output=True,
                text=True,
            )

            # The configured hotspot connection means the device hotspot is active.
            # A wlan/wifi connection suggests the Pi is connected to normal Wi-Fi.
            for name in result.stdout.splitlines():
                if self.hotspot_connection_name.lower() in name.lower():
                    return "hotspot"

                if "wlan" in name.lower() or "wifi" in name.lower():
                    return "auto"

            return "unknown"

        except FileNotFoundError:
            return "unknown"

    # Switch the device into hotspot mode.
    # The connection is brought down first to clear any stale state, then brought up.
    def enable_hotspot(self):
        try:
            subprocess.run(
                ["nmcli", "connection", "down", self.hotspot_connection_name],
                capture_output=True,
                text=True,
            )

            result = subprocess.run(
                ["nmcli", "connection", "up", self.hotspot_connection_name],
                capture_output=True,
                text=True,
            )

            return result.returncode == 0

        except FileNotFoundError:
            return False

    # Connect to a saved Wi-Fi connection by connection name.
    # The hotspot is stopped first so wlan0 can be used for client Wi-Fi.
    def connect_to_wifi(self, ssid):
        try:
            subprocess.run(
                ["nmcli", "connection", "down", self.hotspot_connection_name],
                capture_output=True,
                text=True,
            )

            result = subprocess.run(
                ["nmcli", "connection", "up", ssid],
                capture_output=True,
                text=True,
            )

            return result.returncode == 0

        except FileNotFoundError:
            return False

    # Apply the saved target mode.
    # In hotspot mode, always enable the hotspot.
    # In auto mode, try saved Wi-Fi networks one by one and fall back to hotspot
    # if none of them connect successfully.
    def apply_target_mode(self):
        network_mode = self.get_network_mode()
        target_mode = network_mode.get("mode", "hotspot")

        if target_mode == "hotspot":
            return self.enable_hotspot()

        if target_mode == "auto":
            saved_networks = self.get_saved_wifi_networks()

            # Saved networks are tried in the order nmcli returns them.
            # The first successful connection wins.
            for network in saved_networks:
                connection_name = network.get("connection_name")
                if connection_name and self.connect_to_wifi(connection_name):
                    return True

            return self.enable_hotspot()

        return self.enable_hotspot()

    # Given an nmcli connection name, retrieve the human-readable Wi-Fi SSID.
    # If nmcli does not expose the SSID cleanly, fall back to deriving it from
    # the netplan-style connection name.
    def get_wifi_ssid(self, connection_name):
        try:
            result = subprocess.run(
                ["nmcli", "connection", "show", connection_name],
                capture_output=True,
                text=True,
            )

            for line in result.stdout.splitlines():
                if line.startswith("802-11-wireless.ssid:"):
                    return line.split(":", 1)[1].strip()

            return connection_name.replace("netplan-wlan0-", "")

        except FileNotFoundError:
            return connection_name

    # Return Wi-Fi connections saved on the Pi.
    # Currently this only includes netplan-created wlan connections and ignores
    # other NetworkManager profiles such as the hotspot.
    def get_saved_wifi_networks(self):
        try:
            result = subprocess.run(
                ["nmcli", "-t", "-f", "NAME", "connection", "show"],
                capture_output=True,
                text=True,
            )

            networks = []

            for connection_name in result.stdout.splitlines():
                # Ignore non-Wi-Fi profiles and the hotspot connection.
                if not connection_name.startswith("netplan-wlan"):
                    continue

                ssid = self.get_wifi_ssid(connection_name)

                networks.append(
                    {
                        "ssid": ssid,
                        "connection_name": connection_name,
                    }
                )

            return networks

        except FileNotFoundError:
            return [{"ssid": "(nmcli not available)", "connection_name": ""}]

    # Remove a saved Wi-Fi connection from NetworkManager.
    # This is the backend action for "forget network" in the admin UI.
    def forget_wifi_network(self, connection_name):
        try:
            result = subprocess.run(
                ["nmcli", "connection", "delete", connection_name],
                capture_output=True,
                text=True,
            )

            return result.returncode == 0

        except FileNotFoundError:
            return False

    # Add and immediately connect to a new Wi-Fi network.
    # nmcli stores the successful connection so it can be reused later.
    def add_wifi_network(self, ssid, password):
        try:
            result = subprocess.run(
                ["nmcli", "device", "wifi", "connect", ssid, "password", password],
                capture_output=True,
                text=True,
            )

            return result.returncode == 0

        except FileNotFoundError:
            return False
