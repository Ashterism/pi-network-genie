import subprocess
from .storage import Storage



# Handles network-related behaviour for the timelapse device.
# This sits in the "system controls" layer rather than the core timelapse logic.
# It stores the desired network mode, checks the current mode, and uses nmcli
# to switch between saved Wi-Fi networks and the device hotspot.


class NetworkManager:
    def __init__(self):
        # Use the shared Storage helper so network settings are saved via json in
        # the same metadata area as the rest of the device configuration.
        self.storage = Storage()
        self.network_settings = self.storage.meta_dir / "network_settings.json"

        # These are the network modes exposed to the front end.
        # "auto" tries saved Wi-Fi first, then falls back to hotspot.
        # "hotspot" forces the device into hotspot-only mode.
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
        settings = {
            "target_mode": data.get("mode", "hotspot"),
        }

        self.storage.write_json(self.network_settings, settings)
        return settings

    # Load the saved network settings.
    # If nothing has been saved yet, default to hotspot mode so the device
    # remains directly accessible.
    def get_network_settings(self):
        saved = self.storage.read_json(self.network_settings)
        return saved or {"target_mode": "hotspot"}

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

            # A potshot connection means the device hotspot is active.
            # A wlan/wifi connection suggests the Pi is connected to normal Wi-Fi.
            for name in result.stdout.splitlines():
                if "potshot" in name.lower():
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
                ["nmcli", "connection", "down", "potshot-hotspot"],
                capture_output=True,
                text=True,
            )

            result = subprocess.run(
                ["nmcli", "connection", "up", "potshot-hotspot"],
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
                ["nmcli", "connection", "down", "potshot-hotspot"],
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
        settings = self.get_network_settings()
        target_mode = settings.get("target_mode", "hotspot")

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
            # running on non-Pi (e.g. Mac)
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