# Pi Network Genie

Pi Network Genie is a small helper package for Raspberry Pi projects.

Its purpose is simple: get a Pi into a state where you can reliably connect to it over either Wi-Fi or its own hotspot, and ensure that connection is restored correctly after every reboot.

It can be used in two ways:

- By manually copying the networking files into an existing project.
- Via the installer (coming soon).

---

# Manual installation

If you already have a project and just want the networking functionality, copy the following files:

- `apply.py`
- `manager.py`
- `network_mode.json`

In `manager.py`, update the hotspot connection name to match your project.

You can then call `apply.py` however you like to switch between Wi-Fi and hotspot modes.

If you would like a simple web interface for managing networking, you can also copy the contents of the `web` folder. This provides a lightweight interface for:

- changing the boot network mode
- adding Wi-Fi networks
- forgetting saved Wi-Fi networks

> **Note**
>
> Changing the network mode requires a reboot.
>
> This package is intentionally designed this way for reliability. The selected mode is stored in `network_mode.json`, and the network configuration is applied during boot rather than while the application is running.

If you want the selected network mode to be applied automatically on every boot, also copy and install the included `network.service` systemd service.

---

# Installer

Coming soon.

The installer will configure Pi Network Genie automatically using the values in `project.yml`.