# Blueprint checks

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
