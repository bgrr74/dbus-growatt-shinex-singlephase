# Changelog

All notable changes to this project are documented here.

## 1.2.0 - 2026-09-16

- Added `Phase = L1`, `L2` or `L3` for the physical house phase.
- Kept L1 as the backwards-compatible default when `Phase` is absent.
- Publish voltage, current, power and energy only on the configured phase.
- Added configuration, path-registration, live-update and offline phase tests.
- Live-verified L1 publication on Venus OS 3.79.

## 1.1.1 - 2026-09-16

- Added the optional `Model` setting for the GX product name.
- Prevented a duplicated `Growatt` prefix when a full model name is supplied.
- Kept `Growatt ShineX single-phase` as the backwards-compatible fallback.

## 1.1.0 - 2026-09-15

- Added stricter configuration validation.
- Delayed measurement values until the first valid response.
- Improved service install, restart and uninstall lifecycle handling.
- Added protection against orphaned runit services and logger processes.
- Rate-limited repeated identical HTTP errors.
- Improved worker exception handling and parser safety.
- Expanded automated service tests.

## 1.0.0 - 2026-09-15

- Created the focused single-phase Growatt ShineX driver.
- Moved HTTP polling out of the GLib/D-Bus event loop.
- Separated communication state from inverter running state.
- Added stale-data handling while retaining cumulative energy.
- Added safe low-current calculation and read-only telemetry paths.
- Added parser tests for three real single-phase Growatt response shapes.
