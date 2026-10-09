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
Color checks cover editable palette checkpoints, interpolation and normalization,
capability fallbacks, checkpoint deadlines, late commands, and recovery.
Sonoff checks evaluate the actual blueprint's gesture conditions, including
empty gestures during restart mode and configured gestures passing the guard.
They do not replace validation in a running Home Assistant instance or testing
with real bulbs or buttons.

## Home Assistant runtime checks

The separate runtime suite imports the repository's blueprints into temporary
Home Assistant configurations. Sonoff tests send events through the real event bus and
check gesture routing, other devices, unknown commands, empty actions, all four
automation modes, cancellation, queue and parallel limits, and ignored-press
warnings. Native event waits keep actions running until the test releases them;
the script engine and blueprint importer are not simulated.

Sunrise tests use the native light service and recording light entities in place
of hardware. They verify blueprint import, RGB conversion to each supported color
format, temperature and brightness fallbacks, the default white style, and
rejection of black palettes before commands.

Run on Linux with Python 3.12 for the minimum supported Home Assistant release:

```text
python -m pip install -r tests/runtime/requirements-2024.10.0.txt
python -m unittest discover -s tests/runtime -v
```

Use a separate environment with Python 3.14.2 or newer and install
`tests/runtime/requirements-2026.10.0.txt` to test the other CI matrix entry.
The version-specific requirements pin Home Assistant and keep the older release's
ACME dependency compatible. The runtime suite fails if Home Assistant is missing;
it does not silently skip tests.

[GitHub Actions](../.github/workflows/blueprint-tests.yml) runs the simulation
checks and both pinned runtime versions on pushes and pull requests. Run the
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

Successful suites finish with `OK`: currently **62 simulation checks** and
**15 runtime tests per Home Assistant version**. If installation or a test suite
fails, the command exits with a nonzero code; check `$LASTEXITCODE` immediately
after the Docker command.

The repository is mounted read-only, and `PYTHONDONTWRITEBYTECODE=1` prevents
Python from attempting to write bytecode there. Home Assistant uses a temporary
configuration inside the container. No ports or Zigbee hardware need to be
exposed. Docker removes each container after it exits because of `--rm`.
Images remain cached, but Python dependencies install again for each run.
