import importlib.util
import os
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock


def load_service_module():
    requests_module = types.ModuleType("requests")
    requests_module.RequestException = type("RequestException", (Exception,), {})
    requests_module.get = mock.Mock()

    dbus_module = types.ModuleType("dbus")
    dbus_mainloop_module = types.ModuleType("dbus.mainloop")
    dbus_glib_module = types.ModuleType("dbus.mainloop.glib")
    dbus_glib_module.DBusGMainLoop = mock.Mock()

    gi_module = types.ModuleType("gi")
    gi_repository_module = types.ModuleType("gi.repository")
    gi_repository_module.GLib = types.SimpleNamespace(timeout_add=mock.Mock())

    vedbus_module = types.ModuleType("vedbus")
    vedbus_module.VeDbusService = mock.Mock()

    module_stubs = {
        "requests": requests_module,
        "dbus": dbus_module,
        "dbus.mainloop": dbus_mainloop_module,
        "dbus.mainloop.glib": dbus_glib_module,
        "gi": gi_module,
        "gi.repository": gi_repository_module,
        "vedbus": vedbus_module,
    }

    script_path = Path(__file__).resolve().parents[1] / "dbus-growatt-shinex.py"
    spec = importlib.util.spec_from_file_location("growatt_dbus_service", script_path)
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, module_stubs):
        spec.loader.exec_module(module)
    return module


SERVICE = load_service_module()


class CountingService(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.write_count = 0

    def __setitem__(self, key, value):
        self.write_count += 1
        super().__setitem__(key, value)


class PathService:
    def __init__(self):
        self.paths = {}

    def add_path(self, path, value, **kwargs):
        self.paths[path] = value


class ServiceLogicTests(unittest.TestCase):
    def write_config(self, content):
        directory = tempfile.TemporaryDirectory()
        path = os.path.join(directory.name, "config.ini")
        with open(path, "w", encoding="utf-8") as config_file:
            config_file.write(content)
        return directory, path

    def valid_config(self):
        return """\
[DEFAULT]
DeviceInstance = 42
CustomName = solar2
Model = MIC 1500TL-X
Phase = L2
Position = 0
PollInterval = 2
RequestTimeout = 3
OfflineAfter = 10
SignOfLifeLog = 5
LogLevel = INFO

[ONPREMISE]
Host = 192.0.2.42
"""

    def test_valid_settings_are_typed(self):
        directory, path = self.write_config(self.valid_config())
        self.addCleanup(directory.cleanup)

        settings = SERVICE.load_settings(path)

        self.assertEqual(settings["device_instance"], 42)
        self.assertEqual(settings["position"], 0)
        self.assertEqual(settings["phase"], "L2")
        self.assertEqual(settings["product_name"], "Growatt MIC 1500TL-X")
        self.assertEqual(settings["status_url"], "http://192.0.2.42/status")

    def test_model_accepts_optional_growatt_prefix_and_has_fallback(self):
        cases = (
            ("MIN 2500TL-XE", "Growatt MIN 2500TL-XE"),
            ("Growatt MIN 5000TL-X", "Growatt MIN 5000TL-X"),
            ("  Growatt   MIC 1500TL-X  ", "Growatt MIC 1500TL-X"),
            ("", "Growatt ShineX single-phase"),
        )
        for configured, expected in cases:
            with self.subTest(configured=configured):
                self.assertEqual(SERVICE.product_name_from_model(configured), expected)

    def test_missing_model_uses_generic_product_name(self):
        content = self.valid_config().replace("Model = MIC 1500TL-X\n", "")
        directory, path = self.write_config(content)
        self.addCleanup(directory.cleanup)

        settings = SERVICE.load_settings(path)

        self.assertEqual(settings["product_name"], "Growatt ShineX single-phase")

    def test_missing_phase_defaults_to_l1(self):
        content = self.valid_config().replace("Phase = L2\n", "")
        directory, path = self.write_config(content)
        self.addCleanup(directory.cleanup)

        settings = SERVICE.load_settings(path)

        self.assertEqual(settings["phase"], "L1")

    def test_phase_is_case_insensitive(self):
        content = self.valid_config().replace("Phase = L2", "Phase = l3")
        directory, path = self.write_config(content)
        self.addCleanup(directory.cleanup)

        settings = SERVICE.load_settings(path)

        self.assertEqual(settings["phase"], "L3")

    def test_invalid_device_instance_position_and_log_level_are_rejected(self):
        cases = (
            ("DeviceInstance = 42", "DeviceInstance = 256"),
            ("Position = 0", "Position = 3"),
            ("Phase = L2", "Phase = L4"),
            ("LogLevel = INFO", "LogLevel = VERBOSE"),
        )
        for original, replacement in cases:
            with self.subTest(replacement=replacement):
                content = self.valid_config().replace(original, replacement)
                directory, path = self.write_config(content)
                try:
                    with self.assertRaises(ValueError):
                        SERVICE.load_settings(path)
                finally:
                    directory.cleanup()

    def test_measurements_start_invalid_instead_of_zero(self):
        service = SERVICE.DbusGrowattShineXService.__new__(
            SERVICE.DbusGrowattShineXService
        )
        service._settings = {
            "device_instance": 42,
            "custom_name": "solar2",
            "product_name": "Growatt MIC 1500TL-X",
            "position": 0,
            "phase": "L2",
        }
        service._dbusservice = PathService()

        service._add_paths()

        self.assertEqual(service._dbusservice.paths["/Connected"], 0)
        self.assertEqual(
            service._dbusservice.paths["/ProductName"], "Growatt MIC 1500TL-X"
        )
        self.assertIsNone(service._dbusservice.paths["/Ac/Power"])
        self.assertIsNone(service._dbusservice.paths["/Ac/Energy/Forward"])
        self.assertIsNone(service._dbusservice.paths["/Ac/L2/Power"])
        self.assertNotIn("/Ac/L1/Power", service._dbusservice.paths)
        self.assertNotIn("/Ac/L3/Power", service._dbusservice.paths)

    def test_measurement_is_published_only_on_configured_phase(self):
        service = SERVICE.DbusGrowattShineXService.__new__(
            SERVICE.DbusGrowattShineXService
        )
        service._settings = {"phase": "L3"}
        service._dbusservice = CountingService({"/UpdateIndex": 0})
        service._last_success = None
        service._connected = False
        measurement = types.SimpleNamespace(
            inverter_running=True,
            error_code=0,
            power=1234.5,
            current=5.2,
            voltage=237.4,
            energy=4567.8,
            serial="AABBCCDDEEFF",
        )

        with mock.patch.object(SERVICE.logging, "info"):
            service._apply_measurement(measurement, 0.123)

        self.assertEqual(service._dbusservice["/Ac/Power"], 1234.5)
        self.assertEqual(service._dbusservice["/Ac/L3/Power"], 1234.5)
        self.assertEqual(service._dbusservice["/Ac/L3/Current"], 5.2)
        self.assertEqual(service._dbusservice["/Ac/L3/Voltage"], 237.4)
        self.assertEqual(service._dbusservice["/Ac/L3/Energy/Forward"], 4567.8)
        self.assertNotIn("/Ac/L1/Power", service._dbusservice)
        self.assertNotIn("/Ac/L2/Power", service._dbusservice)

    def test_offline_transition_writes_only_once(self):
        service = SERVICE.DbusGrowattShineXService.__new__(
            SERVICE.DbusGrowattShineXService
        )
        service._dbusservice = CountingService()
        service._settings = {"phase": "L2"}
        service._connected = False

        service._set_offline()
        self.assertEqual(service._dbusservice.write_count, 0)

        service._connected = True
        with mock.patch.object(SERVICE.logging, "warning"):
            service._set_offline()
        writes_after_transition = service._dbusservice.write_count
        service._set_offline()

        self.assertGreater(writes_after_transition, 0)
        self.assertEqual(service._dbusservice.write_count, writes_after_transition)
        self.assertEqual(service._dbusservice["/Connected"], 0)
        self.assertEqual(service._dbusservice["/Ac/L2/Power"], 0.0)
        self.assertNotIn("/Ac/L1/Power", service._dbusservice)

    def test_repeated_identical_errors_are_rate_limited(self):
        service = SERVICE.DbusGrowattShineXService.__new__(
            SERVICE.DbusGrowattShineXService
        )
        service._last_logged_error = None
        service._last_error_log_time = None

        with mock.patch.object(SERVICE.time, "monotonic", side_effect=(100, 120, 161)):
            with mock.patch.object(SERVICE.logging, "warning") as warning:
                service._handle_error("503 Service Unavailable")
                service._handle_error("503 Service Unavailable")
                service._handle_error("503 Service Unavailable")

        self.assertEqual(warning.call_count, 2)

    def test_unexpected_worker_error_does_not_escape(self):
        service = SERVICE.DbusGrowattShineXService.__new__(
            SERVICE.DbusGrowattShineXService
        )
        service._settings = {"poll_interval": 2, "request_timeout": 3}
        service._stop_event = threading.Event()
        service._updates = SERVICE.queue.Queue(maxsize=1)

        class BrokenClient:
            def __init__(self, settings):
                pass

            def get_status(self):
                service._stop_event.set()
                raise OverflowError("bad numeric value")

        with mock.patch.object(SERVICE, "ShineXClient", BrokenClient):
            service._poll_worker()

        update = service._updates.get_nowait()
        self.assertEqual(update[0], "error")
        self.assertIn("OverflowError", update[1])


if __name__ == "__main__":
    unittest.main()
