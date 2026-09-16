# dbus-growatt-shinex-singlephase

[![Test](https://github.com/bgrr74/dbus-growatt-shinex-singlephase/actions/workflows/test.yml/badge.svg)](https://github.com/bgrr74/dbus-growatt-shinex-singlephase/actions/workflows/test.yml)

A focused Venus OS driver that publishes one **single-phase Growatt inverter**
with an OpenInverterGateway/ShineX Wi-Fi dongle as a Victron PV inverter on
D-Bus.

**Current driver version: 1.2.0**

This driver intentionally does not support three-phase inverters. It publishes
one global AC measurement and exactly one configured house phase: L1, L2 or
L3. Run one independent installation per inverter so a communication problem
with one ShineX dongle cannot block the others.

## Highlights

- Selects the physical house phase with `Phase = L1`, `L2` or `L3`.
- Keeps communication state separate from inverter running state, so a
  reachable inverter remains connected with 0 W at night.
- Performs HTTP polling in a background thread; timeouts never block the
  GLib/D-Bus event loop.
- Uses one short-lived HTTP connection per poll because ShineX firmware does
  not reliably support connection reuse.
- Marks stale communication offline and resets live power, current and voltage
  to zero while retaining the cumulative energy counter.
- Loads and validates configuration once at startup.
- Publishes measurement paths as read-only D-Bus values.
- Rate-limits repeated transient HTTP errors.
- Provides checked install, restart and uninstall scripts for runit.
- Supports an optional inverter model in the GX product name.

## Compatibility and test status

- Live-tested on Venus OS 3.79 with Python 3.12 and a Growatt MIC 1500TL-X.
- Parser tests include real response shapes from Growatt MIC and MIN
  single-phase inverters.
- GitHub Actions compiles the driver and runs all unit tests on Python 3.9 and
  Python 3.12.
- Version 1.2.0 has been verified live with only the configured L1 D-Bus paths
  present. L2 and L3 publication are covered by automated service tests.

This is a community driver and is not an official Victron or Growatt product.

## Requirements

- Victron GX device or Venus OS with Python 3.
- Root access to the GX device.
- `requests`, `dbus`, GLib and Victron `velib_python`, as included on current
  Venus OS systems.
- A ShineX-compatible dongle running
  [OpenInverterGateway](https://github.com/OpenInverterGateway/OpenInverterGateway)
  and reachable through its local `/status` endpoint.

Before installing, verify that the endpoint returns a JSON object:

```sh
wget -qO- http://192.0.2.10/status
```

Replace `192.0.2.10` with the actual local IP address or hostname. Do not expose
an unauthenticated ShineX endpoint directly to the internet.

## Fresh installation

Download the repository into a uniquely named directory below `/data`. The
directory name becomes the runit service name and the log directory name.

```sh
cd /data
wget -O /tmp/growatt-singlephase.zip \
  https://github.com/bgrr74/dbus-growatt-shinex-singlephase/archive/refs/heads/main.zip
unzip /tmp/growatt-singlephase.zip -d /data
mv /data/dbus-growatt-shinex-singlephase-main /data/growatt-solar-1
rm /tmp/growatt-singlephase.zip

cd /data/growatt-solar-1
cp config.example.ini config.ini
vi config.ini
chmod +x install.sh
./install.sh
```

Use a different directory and `DeviceInstance` for every inverter.

## Configuration

```ini
[DEFAULT]
AccessType = OnPremise
DeviceInstance = 41
CustomName = Growatt Solar 1
Model = MIN 2500TL-XE
Phase = L1
Position = 0
PollInterval = 2
RequestTimeout = 3
OfflineAfter = 10
SignOfLifeLog = 5
LogLevel = INFO

[ONPREMISE]
Host = 192.0.2.10
Username =
Password =
```

| Setting | Required | Meaning |
|---|---:|---|
| `AccessType` | No | Only `OnPremise` is supported; this is also the default. |
| `DeviceInstance` | Yes | Unique Victron D-Bus instance from `0` through `255`. |
| `CustomName` | No | Name shown on the GX device and in VRM. |
| `Model` | No | Inverter model shown as product name. `MIN 2500TL-XE` and `Growatt MIN 2500TL-XE` are both accepted. |
| `Phase` | No | Physical house phase: `L1`, `L2` or `L3`. Defaults to `L1`. |
| `Position` | No | Victron AC position: `0` = AC input 1, `1` = AC output, `2` = AC input 2. Defaults to `0`. |
| `PollInterval` | No | Seconds between request starts; minimum `0.5`, default `2`. |
| `RequestTimeout` | No | HTTP timeout in seconds; minimum `0.5`, default `3`. |
| `OfflineAfter` | No | Maximum age of valid data before `/Connected` becomes `0`; must be at least `RequestTimeout`, default `10`. |
| `SignOfLifeLog` | No | Status log interval in minutes; `0` disables it, default `5`. |
| `LogLevel` | No | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL`. |
| `Host` | Yes | ShineX IP address, hostname or complete HTTP(S) base URL. Do not append `/status`. |
| `Username` | No | HTTP Basic Authentication username, when enabled on the endpoint. |
| `Password` | No | HTTP Basic Authentication password. |

AC input 1 and AC input 2 are mapped to grid or genset according to the GX
system setup. For a grid-connected PV inverter on AC input 1, normally use
`Position = 0`. This follows Victron's
[PV inverter system mapping](https://github.com/victronenergy/dbus-systemcalc-py/blob/master/delegates/pvinverter.py).

### Product name

With `Model = MIC 1500TL-X`, the GX product name becomes
`Growatt MIC 1500TL-X`. Supplying the `Growatt` prefix is also accepted and
does not duplicate it. If `Model` is empty or absent, the product name remains
`Growatt ShineX single-phase`.

### Phase mapping

`Phase` selects the Victron D-Bus phase on which this single-phase inverter is
published:

| Configuration | Published phase paths |
|---|---|
| `Phase = L1` | `/Ac/L1/...` |
| `Phase = L2` | `/Ac/L2/...` |
| `Phase = L3` | `/Ac/L3/...` |

Only the selected phase is created. The ShineX JSON fields still start with
`L1ThreePhaseGrid`; those names describe the inverter's own single AC output
and remain the correct source when the house connection places that output on
L2 or L3.

Restart after changing `config.ini`:

```sh
/data/growatt-solar-1/restart.sh
```

## Multiple inverters

Create one complete installation per inverter. Each copy needs a unique
directory name, `DeviceInstance`, `CustomName` and `Host`. Configure `Phase` to
match the physical connection.

Example for three single-phase inverters distributed across a three-phase
house:

| Directory | DeviceInstance | CustomName | Model | Phase | Example host |
|---|---:|---|---|:---:|---|
| `/data/growatt-solar-1` | 41 | Growatt West | MIN 2500TL-XE | L1 | `192.0.2.11` |
| `/data/growatt-solar-2` | 42 | Growatt East | MIC 1500TL-X | L2 | `192.0.2.12` |
| `/data/growatt-solar-3` | 43 | Growatt Flat | MIN 5000TL-X | L3 | `192.0.2.13` |

All inverters may use the same phase when that matches the actual installation.

## Upgrade an existing installation

An in-place upgrade must retain `config.ini`. Do not replace the complete
installation directory with a freshly extracted directory.

The following example upgrades `/data/growatt-solar-1`:

```sh
GROWATT_UPDATE_DIR="$(mktemp -d)"
wget -O "$GROWATT_UPDATE_DIR/release.zip" \
  https://github.com/bgrr74/dbus-growatt-shinex-singlephase/archive/refs/heads/main.zip
unzip "$GROWATT_UPDATE_DIR/release.zip" -d "$GROWATT_UPDATE_DIR"

GROWATT_BACKUP_DIR="/data/growatt-solar-1-backup-$(date +%Y%m%d-%H%M%S)"
cp -a /data/growatt-solar-1 "$GROWATT_BACKUP_DIR"

svc -d /service/growatt-solar-1/log
svc -d /service/growatt-solar-1
sleep 2

cd /data/growatt-solar-1
GROWATT_SOURCE_DIR="$GROWATT_UPDATE_DIR/dbus-growatt-shinex-singlephase-main"
cp "$GROWATT_SOURCE_DIR/dbus-growatt-shinex.py" .
cp "$GROWATT_SOURCE_DIR/growatt_shinex.py" .
cp "$GROWATT_SOURCE_DIR/install.sh" .
cp "$GROWATT_SOURCE_DIR/restart.sh" .
cp "$GROWATT_SOURCE_DIR/uninstall.sh" .
cp "$GROWATT_SOURCE_DIR/service/run" service/run
cp "$GROWATT_SOURCE_DIR/service/log/run" service/log/run

chmod +x install.sh restart.sh uninstall.sh dbus-growatt-shinex.py \
  service/run service/log/run
```

Review `config.ini` before starting the upgraded service.

### Upgrade from 1.1.x to 1.2.0

Add the physical house phase:

```ini
Phase = L1
```

Use L2 or L3 when appropriate. If `Phase` is absent, version 1.2.0 defaults to
L1 for backwards compatibility.

Start the upgraded service after reviewing the configuration:

```sh
cd /data/growatt-solar-1
./install.sh
```

## Migration from another driver or directory

Do not replace a `/service/<name>` symlink while its old runit supervisor is
active. Stop both the old main service and its logger first, or run the old
installation's uninstaller:

```sh
svc -d /service/growatt-solar-1/log
svc -d /service/growatt-solar-1
sleep 2
```

The installer refuses to overwrite a service link that points to another
directory. This prevents orphaned Python and `multilog` processes.

## Verification

Check the service and process:

```sh
svstat /service/growatt-solar-1 /service/growatt-solar-1/log
ps w | grep '[d]bus-growatt-shinex.py'
```

Check the installed source version:

```sh
grep -n '^VERSION' /data/growatt-solar-1/dbus-growatt-shinex.py
```

For `DeviceInstance = 41`, verify the registered D-Bus service:

```sh
dbus -y com.victronenergy.pvinverter.http_41 /FirmwareVersion GetValue
dbus -y com.victronenergy.pvinverter.http_41 /ProductName GetValue
dbus -y com.victronenergy.pvinverter.http_41 /Connected GetValue
dbus -y com.victronenergy.pvinverter.http_41 /Ac/L1/Power GetValue
```

List the registered phase paths:

```sh
dbus -y com.victronenergy.pvinverter.http_41 | grep -E '/Ac/L[123]/'
```

Only the configured phase should be present.

Logs are stored in `/var/log/<service-name>/current`. Convert the runit
timestamps with:

```sh
tail -n 30 /var/log/growatt-solar-1/current | tai64nlocal
```

## Runtime behaviour

| Situation | `/Connected` | Live AC values | Energy counter |
|---|:---:|---|---|
| Valid response, inverter producing | `1` | Actual values | Updated |
| Valid response, inverter sleeping at night | `1` | Power/current `0`; voltage retained when supplied | Updated when supplied |
| Temporary HTTP error, data still fresh | Previous state | Last valid values | Retained |
| No valid data for `OfflineAfter` seconds | `0` | Power/current/voltage `0` | Retained |

Occasional HTTP 503 or closed-connection errors from ShineX firmware are
rate-limited in the log. A successful response restores the online state
without restarting the driver or dongle.

## Troubleshooting

### Service is not visible

```sh
svstat /service/growatt-solar-1
tail -n 30 /var/log/growatt-solar-1/current | tai64nlocal
```

Configuration errors are fatal at startup and appear in the log with a clear
message.

### D-Bus name already exists

Another process is already using the same `DeviceInstance`. Check for duplicate
driver processes and ensure every inverter has a unique instance:

```sh
ps w | grep '[d]bus-growatt-shinex.py'
```

### Continuous HTTP errors

Test the endpoint directly from the GX device:

```sh
wget -qO- http://192.0.2.10/status
```

Replace the example address. Occasional 503 responses are tolerated; continuous
errors indicate a dongle, network, authentication or endpoint problem.

### Wrong phase in the GX interface

Set `Phase` to the physical house phase, restart the service, and list the
registered paths. Exactly one of L1, L2 or L3 should exist.

### Logger lock or duplicate process after migration

This usually means an old runit supervisor is still active. Stop the old main
service and logger before changing a `/service/<name>` link. Do not start a
second manual copy while the supervised service is running.

## Published D-Bus paths

- `/Ac/Power`
- `/Ac/Energy/Forward`
- `/Ac/<Phase>/Voltage`
- `/Ac/<Phase>/Current`
- `/Ac/<Phase>/Power`
- `/Ac/<Phase>/Energy/Forward`
- `/Connected`
- `/StatusCode`
- `/ErrorCode`
- `/Latency`
- Victron management, identity and update paths

Only the configured phase is created. This maps one single-phase inverter to
its physical house phase; it does not add support for a three-phase inverter.

## Development and tests

Run the complete test suite on a regular Python installation:

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile dbus-growatt-shinex.py growatt_shinex.py
bash -n install.sh restart.sh uninstall.sh
sh -n service/run service/log/run
```

Some embedded Venus OS Python builds omit the `unittest` module. In that case,
use GitHub Actions or another Python system for the unit tests and perform the
D-Bus verification above on the GX device.

See [CHANGELOG.md](CHANGELOG.md) for the version history.

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
