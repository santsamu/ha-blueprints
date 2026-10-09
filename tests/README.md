# Blueprint checks

Install the test dependencies, then run from the repository root:

```text
python -m pip install -r tests/requirements.txt
python -m unittest discover -s tests -v
```

The tests parse the actual blueprint and evaluate its Jinja templates and action
steps with simulated lights, timestamps, helper storage, and state updates. They
cover restart recovery, cancellation, completion, and startup waits. They do not
replace validation in a running Home Assistant instance or testing with real bulbs.
