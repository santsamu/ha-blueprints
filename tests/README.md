# Blueprint checks

## Simulation checks

Install the test dependencies, then run from the repository root:

```text
python -m pip install -r tests/requirements.txt
python -m unittest discover -s tests -v
```

The tests parse the actual blueprint and evaluate its Jinja templates and action
steps with simulated lights, timestamps, helper storage, and state updates. They
cover restart recovery, cancellation, completion, startup waits, and mixed light
capabilities, including fading, stepping, and color-temperature limits. Timing
checks simulate slow light commands, missed update deadlines, and cancellation.
Time-helper checks cover daily scheduling, local time, midnight and weekday
boundaries, invalid helpers, changes before and during a run, and recovery.
The helper-only sunrise checks also cover the on/off helper, cancellation during
startup and final commands, disabled recovery, and wake-up actions.
Color checks cover editable palette checkpoints, interpolation and normalization,
capability fallbacks, checkpoint deadlines, late commands, and recovery.
Sonoff checks evaluate the actual blueprint's gesture conditions, including
empty gestures during restart mode and configured gestures passing the guard.
Scene-cycle checks cover scene-count wraparound, invalid positions and helpers,
missing scenes, failed scene calls, resets, and independent gesture actions.
Dropdown checks cover option ordering, current selection, dynamic lists, invalid
helpers, and failed activation without changing the selection.
Motion-light template checks cover duration conversion, daylight source gating,
profile selection, supported command parameters, color normalization, temperature
limits, startup confirmation, rounding tolerances, and override comparisons for
all native light color modes.
Legacy color-mode enum reports are normalized before native template values are
stored, so older Home Assistant light reports remain usable.
They do not replace validation in a running Home Assistant instance or testing
with real bulbs or buttons.

## Home Assistant runtime checks

The separate runtime suite imports the repository's blueprints into temporary
Home Assistant configurations. Sonoff tests send events through the real event bus and
check gesture routing, other devices, unknown commands, empty actions, all four
automation modes, cancellation, queue and parallel limits, and ignored-press
warnings. Native event waits keep actions running until the test releases them;
the script engine and blueprint importer are not simulated.
Scene-cycle tests use native scenes, recording lights, and a Number helper to
verify ordered activation, queued presses, overflow, errors, and helper restoration
after a Home Assistant restart.
Both Number and Dropdown modes run through the native scene and helper services;
queued dropdown presses also verify that changed options are read at execution.

Sunrise tests use the native light service and recording light entities in place
of hardware. They verify blueprint import, RGB conversion to each supported color
format, temperature and brightness fallbacks, the default white style, and
rejection of black palettes before commands.
They also verify scheduling from a native time-only Input Datetime helper.
The helper-only blueprint is imported separately to verify white and colorful
styles, toggle gating, native wait cancellation, and cancelled recovery records.

Motion-light tests import the blueprint and use native motion state triggers and
recording light entities. They cover fixed and resettable timers, independent
off-only checks, day/night profiles, all native color conversions, command failures,
unconfirmed startup, changes during other lights' startup, reverted overrides,
power changes, unavailability, rounding, repeated motion, fresh sessions, and
reload/disable cancellation. The session remains locked until its deadline even
if all lights have been released. These scenarios require Home Assistant 2025.4
variable scoping and are explicitly skipped on 2024.10; a native blueprint
minimum-version validation test runs on every release.

Run on Linux with Python 3.12 for the minimum supported Home Assistant release:

```text
python -m pip install -r tests/runtime/requirements-2024.10.0.txt
python -m unittest discover -s tests/runtime -v
```

Use a separate environment with Python 3.14.2 or newer and install
`tests/runtime/requirements-2026.10.0.txt` to test the other CI matrix entry.
For the motion-light blueprint's minimum release, use Python 3.13 and
`tests/runtime/requirements-2025.4.0.txt`. Its pinned dependencies may need C and C++
compilers and Python development headers on Linux; GitHub's Ubuntu runners
already provide them.
The version-specific requirements pin Home Assistant and keep the older release's
ACME dependency compatible. The runtime suite fails if Home Assistant is missing;
it does not silently skip tests.

[GitHub Actions](../.github/workflows/blueprint-tests.yml) runs the simulation
checks and all three pinned runtime versions on pushes and pull requests. Run the
two discovery commands above to include both suites locally.

No Zigbee coordinator, paired button, helpers, or live Home Assistant installation
is needed. These tests verify automation behavior after a ZHA event arrives;
physical gesture detection and the appearance of colors and fades still need
checking with your hardware.

## Run with Docker

Start Docker Desktop with **Linux containers** enabled, then open **PowerShell**
in the repository root. No local Python installation is required. Docker needs
internet access to download the Python images and test dependencies.

Run the simulation checks and all runtime tests on Home Assistant **2024.10.0**:

```powershell
$repoPath = (Get-Location).Path

docker run --rm `
  --mount "type=bind,source=$repoPath,target=/workspace,readonly" `
  --workdir /workspace `
  --env PYTHONDONTWRITEBYTECODE=1 `
  python:3.12-slim sh -c 'python -m pip install -q -r tests/requirements.txt -r tests/runtime/requirements-2024.10.0.txt && python -m unittest discover -s tests -v && python -m unittest discover -s tests/runtime -v'
```

In the same PowerShell session, also run all runtime tests on
Home Assistant **2026.10.0**:

```powershell
docker run --rm `
  --mount "type=bind,source=$repoPath,target=/workspace,readonly" `
  --workdir /workspace `
  --env PYTHONDONTWRITEBYTECODE=1 `
  python:3.14-slim sh -c 'python -m pip install -q -r tests/runtime/requirements-2026.10.0.txt && python -m unittest discover -s tests/runtime -v'
```

Also verify the motion-light blueprint's minimum, **2025.4.0**. Its older pinned
dependencies need a compiler in the slim Python image:

```powershell
docker run --rm `
  --mount "type=bind,source=$repoPath,target=/workspace,readonly" `
  --workdir /workspace `
  --env PYTHONDONTWRITEBYTECODE=1 `
  --env DEBIAN_FRONTEND=noninteractive `
  python:3.13-slim sh -c 'apt-get update -qq && apt-get install -y -qq --no-install-recommends gcc g++ libc6-dev && python -m pip install -q -r tests/runtime/requirements-2025.4.0.txt && python -m unittest discover -s tests/runtime -v'
```

Successful suites finish with `OK`: currently **123 simulation checks** and
**63 runtime tests** on Home Assistant 2025.4 and 2026.10. On 2024.10, **37 runtime
tests execute and 26 motion-light scenarios are skipped** because the blueprint
declares a newer minimum; its minimum-version guard is still tested. If installation or a test suite
fails, the command exits with a nonzero code; check `$LASTEXITCODE` immediately
after the Docker command.

The repository is mounted read-only, and `PYTHONDONTWRITEBYTECODE=1` prevents
Python from attempting to write bytecode there. Home Assistant uses a temporary
configuration inside the container. No ports or Zigbee hardware need to be
exposed. Docker removes each container after it exits because of `--rm`.
Images remain cached, but Python dependencies install again for each run.
