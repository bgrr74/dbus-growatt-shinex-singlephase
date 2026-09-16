#!/usr/bin/env python3
"""Publish one single-phase Growatt inverter on the Victron Venus OS D-Bus."""

import configparser
import logging
import os
import platform
import queue
import sys
import threading
import time
from urllib.parse import urlparse

import requests
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

sys.path.insert(1, "/opt/victronenergy/dbus-systemcalc-py/ext/velib_python")
from vedbus import VeDbusService  # noqa: E402

from growatt_shinex import parse_measurement


VERSION = "1.2.0"
CONFIG_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "config.ini")
ERROR_LOG_INTERVAL = 60.0


def product_name_from_model(model):
    """Build a consistent Victron product name from an optional model value."""
    model = " ".join(model.split())
    if not model:
        return "Growatt ShineX single-phase"

    if model.casefold() == "growatt":
        return "Growatt"
    if model.casefold().startswith("growatt "):
        return "Growatt {}".format(model[8:].strip())
    return "Growatt {}".format(model)


def load_settings(path):
    parser = configparser.ConfigParser()
    if not parser.read(path):
        raise RuntimeError("Configuration file not found: {}".format(path))

    defaults = parser["DEFAULT"]
    if defaults.get("AccessType", "OnPremise").strip().lower() != "onpremise":
        raise ValueError("Only AccessType=OnPremise is supported")
    if "ONPREMISE" not in parser:
        raise ValueError("Missing [ONPREMISE] section")

    on_premise = parser["ONPREMISE"]
    host = on_premise.get("Host", "").strip()
    if not host:
        raise ValueError("ONPREMISE Host must be configured")

    base_url = host if "://" in host else "http://{}".format(host)
    parsed_url = urlparse(base_url)
    if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
        raise ValueError("Invalid ONPREMISE Host: {}".format(host))

    poll_interval = defaults.getfloat("PollInterval", fallback=2.0)
    request_timeout = defaults.getfloat("RequestTimeout", fallback=3.0)
    offline_after = defaults.getfloat("OfflineAfter", fallback=10.0)
    sign_of_life = defaults.getint("SignOfLifeLog", fallback=5)
    device_instance = defaults.getint("DeviceInstance")
    position = defaults.getint("Position", fallback=0)
    phase = defaults.get("Phase", "L1").strip().upper()
    log_level = defaults.get("LogLevel", "INFO").strip().upper()

    if not 0 <= device_instance <= 255:
        raise ValueError("DeviceInstance must be between 0 and 255")
    if position not in (0, 1, 2):
        raise ValueError("Position must be 0, 1 or 2")
    if phase not in {"L1", "L2", "L3"}:
        raise ValueError("Phase must be L1, L2 or L3")
    if poll_interval < 0.5:
        raise ValueError("PollInterval must be at least 0.5 seconds")
    if request_timeout < 0.5:
        raise ValueError("RequestTimeout must be at least 0.5 seconds")
    if offline_after < request_timeout:
        raise ValueError("OfflineAfter must be greater than or equal to RequestTimeout")
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("LogLevel must be DEBUG, INFO, WARNING, ERROR or CRITICAL")

    return {
        "device_instance": device_instance,
        "custom_name": defaults.get("CustomName", "Growatt ShineX").strip(),
        "product_name": product_name_from_model(defaults.get("Model", "")),
        "position": position,
        "phase": phase,
        "poll_interval": poll_interval,
        "request_timeout": request_timeout,
        "offline_after": offline_after,
        "sign_of_life": max(sign_of_life, 0),
        "log_level": log_level,
        "status_url": "{}/status".format(base_url.rstrip("/")),
        "username": on_premise.get("Username", "").strip(),
        "password": on_premise.get("Password", ""),
    }


class ShineXClient:
    def __init__(self, settings):
        self._url = settings["status_url"]
        self._timeout = settings["request_timeout"]
        self._auth = None
        if settings["username"]:
            self._auth = (settings["username"], settings["password"])
        self._headers = {
            "Accept": "application/json",
            "Connection": "close",
        }

    def get_status(self):
        # OpenInverterGateway/ShineX firmware can close keep-alive sockets
        # without warning. Use a fresh connection for every polling cycle.
        response = requests.get(
            self._url,
            auth=self._auth,
            headers=self._headers,
            timeout=self._timeout,
        )
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" in content_type or response.text.lstrip().lower().startswith("<html"):
            raise ValueError("ShineX returned HTML instead of JSON")

        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("ShineX returned JSON that is not an object")
        return payload

class DbusGrowattShineXService:
    def __init__(self, settings):
        self._settings = settings
        self._updates = queue.Queue(maxsize=1)
        self._stop_event = threading.Event()
        self._last_success = None
        self._last_logged_error = None
        self._last_error_log_time = None
        self._connected = False

        instance = settings["device_instance"]
        service_name = "com.victronenergy.pvinverter.http_{:02d}".format(instance)
        self._dbusservice = VeDbusService(service_name, register=False)
        self._add_paths()
        self._dbusservice.register()

        self._worker = threading.Thread(
            target=self._poll_worker,
            name="shinex-http-{}".format(instance),
            daemon=True,
        )
        self._worker.start()

        GLib.timeout_add(250, self._update)
        if settings["sign_of_life"] > 0:
            GLib.timeout_add(settings["sign_of_life"] * 60 * 1000, self._sign_of_life)

        logging.info(
            "Started %s as device instance %d on %s",
            settings["custom_name"],
            instance,
            settings["phase"],
        )

    def _phase_path(self, item):
        return "/Ac/{}/{}".format(self._settings["phase"], item)

    def _add_paths(self):
        service = self._dbusservice
        settings = self._settings

        service.add_path("/Mgmt/ProcessName", __file__)
        service.add_path(
            "/Mgmt/ProcessVersion",
            "{} (Python {})".format(VERSION, platform.python_version()),
        )
        service.add_path("/Mgmt/Connection", "Growatt ShineX local HTTP JSON")
        service.add_path("/DeviceInstance", settings["device_instance"])
        service.add_path("/ProductId", 0xFFFF)
        service.add_path("/ProductName", settings["product_name"])
        service.add_path("/CustomName", settings["custom_name"])
        service.add_path("/Latency", None, gettextcallback=self._format_seconds)
        service.add_path("/FirmwareVersion", VERSION)
        service.add_path("/HardwareVersion", 0)
        service.add_path("/Connected", 0)
        service.add_path("/Role", "pvinverter")
        service.add_path("/Position", settings["position"])
        service.add_path("/Serial", "UNKNOWN")
        service.add_path("/UpdateIndex", 0)
        service.add_path("/StatusCode", 0)
        service.add_path("/ErrorCode", 0)

        # Keep measurements invalid until the first valid response. In particular,
        # a cumulative energy counter must never briefly look like it reset to zero.
        service.add_path("/Ac/Energy/Forward", None, gettextcallback=self._format_kwh)
        service.add_path("/Ac/Power", None, gettextcallback=self._format_watts)
        service.add_path(
            self._phase_path("Current"), None, gettextcallback=self._format_amps
        )
        service.add_path(
            self._phase_path("Power"), None, gettextcallback=self._format_watts
        )
        service.add_path(
            self._phase_path("Voltage"), None, gettextcallback=self._format_volts
        )
        service.add_path(
            self._phase_path("Energy/Forward"),
            None,
            gettextcallback=self._format_kwh,
        )

    @staticmethod
    def _format_value(value, decimals, unit):
        if value is None:
            return "---"
        return "{:.{precision}f} {}".format(value, unit, precision=decimals)

    def _format_seconds(self, path, value):
        return self._format_value(value, 3, "s")

    def _format_kwh(self, path, value):
        return self._format_value(value, 2, "kWh")

    def _format_amps(self, path, value):
        return self._format_value(value, 2, "A")

    def _format_watts(self, path, value):
        return self._format_value(value, 1, "W")

    def _format_volts(self, path, value):
        return self._format_value(value, 1, "V")

    def _queue_latest(self, item):
        try:
            self._updates.put_nowait(item)
        except queue.Full:
            try:
                self._updates.get_nowait()
            except queue.Empty:
                pass
            self._updates.put_nowait(item)

    def _poll_worker(self):
        client = ShineXClient(self._settings)
        while not self._stop_event.is_set():
            started = time.monotonic()
            try:
                payload = client.get_status()
                measurement = parse_measurement(payload)
                latency = time.monotonic() - started
                self._queue_latest(("success", measurement, latency))
            except (requests.RequestException, ValueError) as error:
                self._queue_latest(("error", str(error), None))
            except Exception as error:  # Keep the worker alive on malformed edge cases.
                message = "{}: {}".format(type(error).__name__, error)
                self._queue_latest(("error", message, None))

            elapsed = time.monotonic() - started
            wait_time = max(0.0, self._settings["poll_interval"] - elapsed)
            self._stop_event.wait(wait_time)

    def _update(self):
        latest = None
        while True:
            try:
                latest = self._updates.get_nowait()
            except queue.Empty:
                break

        if latest is not None:
            if latest[0] == "success":
                self._apply_measurement(latest[1], latest[2])
            else:
                self._handle_error(latest[1])

        if self._last_success is None:
            self._set_offline()
        elif time.monotonic() - self._last_success >= self._settings["offline_after"]:
            self._set_offline()

        return True

    def _apply_measurement(self, measurement, latency):
        service = self._dbusservice
        was_connected = self._connected

        self._last_success = time.monotonic()
        self._connected = True

        service["/Connected"] = 1
        service["/Latency"] = latency
        service["/StatusCode"] = 7 if measurement.inverter_running else 0
        service["/ErrorCode"] = measurement.error_code
        service["/Ac/Power"] = measurement.power
        service[self._phase_path("Power")] = measurement.power
        service[self._phase_path("Current")] = measurement.current
        service[self._phase_path("Voltage")] = measurement.voltage

        if measurement.energy is not None:
            service["/Ac/Energy/Forward"] = measurement.energy
            service[self._phase_path("Energy/Forward")] = measurement.energy
        if measurement.serial:
            service["/Serial"] = measurement.serial

        service["/UpdateIndex"] = (service["/UpdateIndex"] + 1) % 256
        if not was_connected:
            logging.info("ShineX communication online")

    def _handle_error(self, message):
        now = time.monotonic()
        if (
            message != self._last_logged_error
            or self._last_error_log_time is None
            or now - self._last_error_log_time >= ERROR_LOG_INTERVAL
        ):
            logging.warning("ShineX request failed: %s", message)
            self._last_logged_error = message
            self._last_error_log_time = now

    def _set_offline(self):
        if not self._connected:
            return

        service = self._dbusservice
        logging.warning("ShineX data is stale; marking inverter disconnected")
        self._connected = False
        service["/Connected"] = 0
        service["/StatusCode"] = 0
        service["/Latency"] = None
        service["/Ac/Power"] = 0.0
        service[self._phase_path("Power")] = 0.0
        service[self._phase_path("Current")] = 0.0
        service[self._phase_path("Voltage")] = 0.0
        # Deliberately retain the cumulative energy counter while offline.

    def _sign_of_life(self):
        age = None
        if self._last_success is not None:
            age = time.monotonic() - self._last_success
        logging.info(
            "Connected=%s Power=%sW Energy=%skWh LastSuccessAge=%ss",
            self._dbusservice["/Connected"],
            self._dbusservice["/Ac/Power"],
            self._dbusservice["/Ac/Energy/Forward"],
            "never" if age is None else round(age, 1),
        )
        return True

    def stop(self):
        self._stop_event.set()
        self._worker.join(timeout=self._settings["request_timeout"] + 1.0)


def main():
    settings = load_settings(CONFIG_FILE)
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(message)s",
        level=getattr(logging, settings["log_level"], logging.INFO),
    )

    DBusGMainLoop(set_as_default=True)
    service = DbusGrowattShineXService(settings)
    main_loop = GLib.MainLoop()
    try:
        main_loop.run()
    except KeyboardInterrupt:
        logging.info("Stopping")
    finally:
        service.stop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s")
        logging.exception("Fatal error")
        sys.exit(1)
