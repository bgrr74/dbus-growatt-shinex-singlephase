# dbus-growatt-shinex-singlephase

A focused Venus OS driver that publishes one **single-phase Growatt inverter**
with an OpenInverterGateway/ShineX Wi-Fi dongle as a Victron PV inverter on
D-Bus.

This edition intentionally does not support three-phase inverters. Run one
independent installation per inverter. A communication problem with one
ShineX dongle therefore does not block the other inverter services.

## Highlights

- Publishes only the global AC and L1 D-Bus paths.
- Keeps communication state separate from inverter running state: a reachable
  inverter remains connected at night.
- Performs HTTP polling in a background thread, so request timeouts never block
  the GLib/D-Bus event loop.
- Uses one persistent HTTP session and one request per polling cycle.
- Marks stale data offline and resets live power, current and voltage to zero.
- Retains the last cumulative energy value during a communication outage.
- Does not automatically restart the ShineX dongle.
- Loads and validates configuration once at startup.
- Publishes measurement paths as read-only values.

## Requirements

- Victron GX device or Venus OS with Python 3.
- Root access to the GX device.
- `requests`, `dbus`, GLib and Victron `velib_python`, as included on current
  Venus OS systems.
- A ShineX-compatible dongle running
  [OpenInverterGateway](https://github.com/OpenInverterGateway/OpenInverterGateway)
  and reachable through its local `/status` endpoint.

## Install one inverter

Download the repository into a uniquely named directory below `/data`. The
directory name becomes the service name.

```sh
cd /data
wget -O growatt-singlephase.zip \
  https://github.com/bgrr74/dbus-growatt-shinex-singlephase/archive/refs/heads/main.zip
unzip growatt-singlephase.zip
mv dbus-growatt-shinex-singlephase-main growatt-solar-1
rm growatt-singlephase.zip

cd /data/growatt-solar-1
cp config.example.ini config.ini
vi config.ini
chmod +x install.sh
./install.sh
```

Use `Position = 0` when the inverter is connected on the AC-input side of the
Victron system.

## Configuration

```ini
[DEFAULT]
AccessType = OnPremise
DeviceInstance = 41
CustomName = Growatt Solar 1
Position = 0
PollInterval = 2
RequestTimeout = 3
OfflineAfter = 10
SignOfLifeLog = 5
LogLevel = INFO

[ONPREMISE]
Host = 192.168.1.100
Username =
Password =
```

| Setting | Meaning |
|---|---|
| `DeviceInstance` | Unique Victron D-Bus device instance. Each inverter needs its own number. |
| `CustomName` | Name displayed on the GX device and VRM. |
| `Position` | Victron PV position; normally `0` for AC input. |
| `PollInterval` | Seconds between request starts; minimum `0.5`. |
| `RequestTimeout` | HTTP timeout in seconds. |
| `OfflineAfter` | Maximum age of the last valid response before `/Connected` becomes `0`. |
| `SignOfLifeLog` | Periodic status log interval in minutes; `0` disables it. |
| `LogLevel` | Python log level, normally `INFO` or `WARNING`. |
| `Host` | ShineX IP address, hostname, or complete HTTP(S) base URL. |

Restart the service after changing `config.ini`:

```sh
/data/growatt-solar-1/restart.sh
```

Logs are stored in `/var/log/growatt-solar-1/current`.

## Three separate Growatt inverters

Create three directory copies and configure a different host, name and device
instance in each `config.ini`, for example:

| Directory | Device instance | Suggested name |
|---|---:|---|
| `/data/growatt-solar-1` | 41 | Growatt West |
| `/data/growatt-solar-2` | 42 | Growatt East |
| `/data/growatt-solar-3` | 43 | Growatt Flat |

Run `install.sh` once from every directory. Each copy gets its own supervised
service and log directory.

## Published D-Bus paths

- `/Ac/Power`
- `/Ac/Energy/Forward`
- `/Ac/L1/Voltage`
- `/Ac/L1/Current`
- `/Ac/L1/Power`
- `/Ac/L1/Energy/Forward`
- `/Connected`, `/StatusCode`, `/ErrorCode`, `/Latency` and management paths

No L2 or L3 paths are created.

## Uninstall

```sh
/data/growatt-solar-1/uninstall.sh
```

The configuration directory and logs are deliberately retained.

## Origin and license

This project is based on
[christoph5180/dbus-growatt-shinex](https://github.com/christoph5180/dbus-growatt-shinex),
which in turn is a fork of
[Kotty666/dbus-growatt-shinex](https://github.com/Kotty666/dbus-growatt-shinex).
The original copyright notice and MIT license are retained.
