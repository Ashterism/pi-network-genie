#!/usr/bin/env bash
set -euo pipefail

CONFIG_FILE="${1:-./pi-network-genie.yaml}"
GENIE_SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GENIE_INSTALL_DIR="/opt/pi-network-genie"

if [[ $EUID -ne 0 ]]; then
  echo "Run this installer with sudo."
  exit 1
fi

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Config file not found: $CONFIG_FILE"
  exit 1
fi

read_config() {
  local key="$1"
  awk -F ':' -v wanted="$key" '
    $1 ~ "^[[:space:]]*" wanted "[[:space:]]*$" {
      sub(/^[^:]*:[[:space:]]*/, "", $0)
      sub(/[[:space:]]+#.*$/, "", $0)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", $0)
      gsub(/^"|"$/, "", $0)
      gsub(/^\047|\047$/, "", $0)
      print $0
      exit
    }
  ' "$CONFIG_FILE"
}

PROJECT_NAME="$(read_config project_name)"
PROJECT_USER="$(read_config user)"
INSTALL_PATH="$(read_config install_path)"
SERVICE_COMMAND="$(read_config service_command)"
HOTSPOT_CONNECTION_NAME="$(read_config hotspot_connection_name)"
HOTSPOT_SSID="$(read_config hotspot_ssid)"
NETWORK_MODE="$(read_config network_mode)"

for value_name in PROJECT_NAME PROJECT_USER INSTALL_PATH SERVICE_COMMAND HOTSPOT_CONNECTION_NAME HOTSPOT_SSID NETWORK_MODE; do
  if [[ -z "${!value_name}" ]]; then
    echo "Missing required config value: $value_name"
    exit 1
  fi
done

if [[ "$NETWORK_MODE" != "auto" && "$NETWORK_MODE" != "hotspot" ]]; then
  echo "network_mode must be 'auto' or 'hotspot'."
  exit 1
fi

if ! id "$PROJECT_USER" >/dev/null 2>&1; then
  echo "Linux user does not exist: $PROJECT_USER"
  exit 1
fi

USER_HOME="$(getent passwd "$PROJECT_USER" | cut -d: -f6)"
SETTINGS_DIR="$USER_HOME/.config/pi-network-genie"
NETWORK_SERVICE_NAME="pi-network-genie-${PROJECT_NAME}.service"
PROJECT_SERVICE_NAME="${PROJECT_NAME}.service"

printf '\nPi Network Genie installer\n'
printf 'Project: %s\n' "$PROJECT_NAME"
printf 'User: %s\n' "$PROJECT_USER"
printf 'Project path: %s\n' "$INSTALL_PATH"
printf 'Network mode: %s\n\n' "$NETWORK_MODE"

apt-get update
apt-get install -y network-manager python3

mkdir -p "$GENIE_INSTALL_DIR"
rm -rf "$GENIE_INSTALL_DIR/src" "$GENIE_INSTALL_DIR/scripts"
cp -R "$GENIE_SOURCE_DIR/src" "$GENIE_INSTALL_DIR/src"
cp -R "$GENIE_SOURCE_DIR/scripts" "$GENIE_INSTALL_DIR/scripts"

mkdir -p "$SETTINGS_DIR"
cat > "$SETTINGS_DIR/network_mode.json" <<EOF
{
  "mode": "$NETWORK_MODE"
}
EOF
chown -R "$PROJECT_USER:$PROJECT_USER" "$SETTINGS_DIR"

printf '\nConfigure hotspot password (stored only on this Pi).\n'
read -r -s -p "Hotspot password (8+ characters): " HOTSPOT_PASSWORD
echo
if [[ ${#HOTSPOT_PASSWORD} -lt 8 ]]; then
  echo "Hotspot password must be at least 8 characters."
  exit 1
fi

if nmcli connection show "$HOTSPOT_CONNECTION_NAME" >/dev/null 2>&1; then
  nmcli connection modify "$HOTSPOT_CONNECTION_NAME" \
    connection.interface-name wlan0 \
    802-11-wireless.ssid "$HOTSPOT_SSID" \
    802-11-wireless.mode ap \
    802-11-wireless.band bg \
    ipv4.method shared \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "$HOTSPOT_PASSWORD" \
    connection.autoconnect no
else
  nmcli connection add \
    type wifi \
    ifname wlan0 \
    con-name "$HOTSPOT_CONNECTION_NAME" \
    ssid "$HOTSPOT_SSID"

  nmcli connection modify "$HOTSPOT_CONNECTION_NAME" \
    802-11-wireless.mode ap \
    802-11-wireless.band bg \
    ipv4.method shared \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "$HOTSPOT_PASSWORD" \
    connection.autoconnect no
fi

while true; do
  read -r -p "Add a Wi-Fi network now? [y/N]: " ADD_WIFI
  case "${ADD_WIFI:-n}" in
    y|Y|yes|YES)
      read -r -p "Wi-Fi SSID: " WIFI_SSID
      read -r -s -p "Wi-Fi password: " WIFI_PASSWORD
      echo
      CONNECTION_NAME="netplan-wlan0-${WIFI_SSID}"

      nmcli connection delete "$CONNECTION_NAME" >/dev/null 2>&1 || true
      if nmcli device wifi connect "$WIFI_SSID" password "$WIFI_PASSWORD" name "$CONNECTION_NAME"; then
        nmcli connection modify "$CONNECTION_NAME" connection.autoconnect no
        echo "Saved Wi-Fi network: $WIFI_SSID"
      else
        echo "Could not connect to $WIFI_SSID; it was not saved by Genie."
      fi
      ;;
    *)
      break
      ;;
  esac
done

render_template() {
  local source="$1"
  local destination="$2"

  sed \
    -e "s|{{PROJECT_NAME}}|$PROJECT_NAME|g" \
    -e "s|{{USER}}|$PROJECT_USER|g" \
    -e "s|{{USER_HOME}}|$USER_HOME|g" \
    -e "s|{{INSTALL_PATH}}|$INSTALL_PATH|g" \
    -e "s|{{SERVICE_COMMAND}}|$SERVICE_COMMAND|g" \
    -e "s|{{GENIE_PATH}}|$GENIE_INSTALL_DIR|g" \
    -e "s|{{SETTINGS_DIR}}|$SETTINGS_DIR|g" \
    -e "s|{{HOTSPOT_CONNECTION_NAME}}|$HOTSPOT_CONNECTION_NAME|g" \
    "$source" > "$destination"
}

render_template \
  "$GENIE_INSTALL_DIR/scripts/network.service" \
  "/etc/systemd/system/$NETWORK_SERVICE_NAME"

render_template \
  "$GENIE_INSTALL_DIR/scripts/keep-running.service" \
  "/etc/systemd/system/$PROJECT_SERVICE_NAME"

systemctl daemon-reload
systemctl enable "$NETWORK_SERVICE_NAME"
systemctl enable "$PROJECT_SERVICE_NAME"

echo
echo "Installed:"
echo "  $NETWORK_SERVICE_NAME"
echo "  $PROJECT_SERVICE_NAME"
echo
echo "Reboot to test the full boot-time behaviour:"
echo "  sudo reboot"
