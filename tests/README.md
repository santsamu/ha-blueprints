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
Sonoff checks evaluate the actual blueprint's gesture conditions, including
empty gestures during restart mode and configured gestures passing the guard.
They do not replace validation in a running Home Assistant instance or testing
with real bulbs or buttons.

## Home Assistant runtime checks

The separate Sonoff suite imports the repository's blueprint into a temporary
Home Assistant configuration and sends events through the real event bus. It
checks gesture routing, other devices, unknown commands, empty actions, all four
automation modes, cancellation, queue and parallel limits, and ignored-press
warnings. Native event waits keep actions running until the test releases them;
the script engine and blueprint importer are not simulated.

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
physical gesture detection still needs checking with your button.
