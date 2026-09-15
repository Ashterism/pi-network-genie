# Pi Network Genie

Pi Network Genie exists for one reason: **after a Raspberry Pi boots, it should be contactable.**

It does two jobs:

1. Get the Pi onto a known Wi-Fi network, or fall back to its own hotspot if none work.
2. Keep the host project's main service running so there is actually something to connect to.

The networking behaviour is deliberately simple and conservative because it was developed through real Pi use. Avoid casually rewriting the Wi-Fi/hotspot switching logic.

## Future Ash: setting up a new Pi

### 1. Create the project repo first

In the new project's GitHub repo, add a file called `pi-network-genie.yaml`:

```yaml
project_name: my-project
device_name: my-pi
user: ash
install_path: /home/ash/my-project
service_command: /home/ash/my-project/.venv/bin/python3 -m my_project
network_mode: auto
```

`project_name` identifies the software/service. `device_name` identifies the physical Pi. Several Pis can therefore run the same project without all advertising the same hotspot.

By default Genie derives:

```text
hotspot SSID: <device_name>
NetworkManager connection: <device_name>-hotspot
```

You can override `hotspot_ssid` or `hotspot_connection_name` in the YAML if needed, but normally you should not.

Do **not** put Wi-Fi passwords or the hotspot password in GitHub. The installer asks for them locally on the Pi.

### 2. On the new Pi, clone the project

```bash
cd ~
git clone https://github.com/Ashterism/my-project.git
cd my-project
```

### 3. Run Pi Network Genie

The simplest standalone install is:

```bash
git clone https://github.com/Ashterism/pi-network-genie.git /tmp/pi-network-genie
sudo bash /tmp/pi-network-genie/install.sh ./pi-network-genie.yaml
```

A project's own `install.sh` can wrap those two commands so new-machine setup becomes a single command.

The installer will:

- check/install the required system packages;
- create the Pi hotspot;
- ask for the hotspot password locally;
- optionally add saved Wi-Fi networks;
- store the selected network mode outside the project repo;
- install a boot-time Pi Network Genie systemd service;
- install a `keep-running` systemd service for the host project;
- enable both services.

### 4. Reboot

```bash
sudo reboot
```

After boot, in `auto` mode:

- Genie tries the saved Wi-Fi connections;
- if one connects, the Pi uses it;
- if none connect, Genie enables the Pi's hotspot;
- the host project's service is started and kept running.

In `hotspot` mode, the Pi always starts its hotspot.

## Configuration

| Setting | Meaning |
| --- | --- |
| `project_name` | Software/project identity and project systemd service name |
| `device_name` | Physical Pi identity; normally becomes the hotspot SSID |
| `user` | Linux user that runs the project |
| `install_path` | Project working directory |
| `service_command` | Exact command systemd should use to run the project |
| `network_mode` | `auto` or `hotspot` |
| `hotspot_connection_name` | Optional override for NetworkManager's local profile name |
| `hotspot_ssid` | Optional override for the Wi-Fi name broadcast by the Pi |

Secrets are intentionally not supported in this file.

## How it works

Pi Network Genie uses NetworkManager through `nmcli`.

The core manager supports:

- `auto`: try saved Wi-Fi connections and fall back to the hotspot;
- `hotspot`: force the hotspot;
- listing saved networks;
- adding and forgetting Wi-Fi networks;
- a small optional web administration interface.

Network mode is applied at boot rather than live-switched while the application is running. This is intentional: changing the network underneath the web request controlling it is fragile and can strand the Pi.

Runtime state is stored under the configured user's:

```text
~/.config/pi-network-genie/
```

not inside the host project's Git repository.

## Development rule

The existing `NetworkManager` switching sequence is the known-good part of this project. Changes around installation, configuration and UI are fine; changes to the actual Wi-Fi/hotspot switching behaviour should be tested on a real Pi before being trusted.