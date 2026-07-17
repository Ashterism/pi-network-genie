from flask import Flask, redirect, render_template, request, url_for

from network.manager import NetworkManager


app = Flask(__name__)
network_manager = NetworkManager()


@app.get("/")
def admin():
    network_mode = network_manager.get_network_mode()
    current_mode = network_manager.get_current_network_mode()
    networks = network_manager.get_saved_wifi_networks()

    return render_template(
        "admin.html",
        network_options=network_manager.get_network_options(),
        selected_mode=network_mode.get("mode", "hotspot"),
        current_mode=current_mode,
        networks=networks,
    )


@app.post("/network-mode")
def update_network_mode():
    network_manager.update_network_settings(request.form)
    return redirect(url_for("admin"))


@app.post("/forget-network")
def forget_network():
    network_manager.forget_wifi_network(
        request.form.get("connection_name", "")
    )
    return redirect(url_for("admin"))


@app.post("/add-network")
def add_network():
    network_manager.add_wifi_network(
        request.form.get("ssid", ""),
        request.form.get("password", ""),
    )
    return redirect(url_for("admin"))