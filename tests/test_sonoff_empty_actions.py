"""Check the Sonoff guard before handing a gesture to the action script.

These checks evaluate actual YAML and Jinja, not Home Assistant's script engine.
Home Assistant evaluates automation conditions before applying the script mode.
"""

from copy import deepcopy
from itertools import product
from pathlib import Path
import unittest

from jinja2 import Environment, StrictUndefined
import yaml


class Input(str):
    pass


class Loader(yaml.SafeLoader):
    pass


Loader.add_constructor("!input", lambda loader, node: Input(loader.construct_scalar(node)))
BLUEPRINT = yaml.load(
    (Path(__file__).resolve().parents[1] / "sonoff_zigbee_button/sonoff_zigbee_button.yaml")
    .read_text(encoding="utf-8"), Loader=Loader,
)
ENV = Environment(undefined=StrictUndefined)
GESTURES = {"press": "press_action", "double_press": "double_press_action", "hold": "hold_action"}


def substitute(value, inputs):
    if isinstance(value, Input):
        return deepcopy(inputs[value])
    if isinstance(value, dict):
        return {key: substitute(item, inputs) for key, item in value.items()}
    if isinstance(value, list):
        return [substitute(item, inputs) for item in value]
    return value


def configuration(**overrides):
    inputs = {name: details.get("default") for name, details in BLUEPRINT["blueprint"]["input"].items()}
    inputs.update(button_id="test-button", **overrides)
    return substitute(BLUEPRINT, inputs)


def passes_guard(config, gesture=None):
    context = {}
    if gesture is not None:
        trigger = next(item for item in config["triggers"] if item["id"] == gesture)
        context.update(trigger["variables"])
    return all(ENV.from_string(condition["value_template"]).render(context).strip() == "True"
               for condition in config["conditions"])


class SonoffEmptyActionTests(unittest.TestCase):
    def test_each_gesture_is_allowed_only_when_its_own_sequence_is_configured(self):
        for configured in product((False, True), repeat=3):
            inputs = {name: [{"action": "test." + gesture}] if enabled else []
                      for (gesture, name), enabled in zip(GESTURES.items(), configured)}
            for mode in ("single", "restart", "queued", "parallel"):
                config = configuration(mode=mode, **inputs)
                for gesture, enabled in zip(GESTURES, configured):
                    with self.subTest(configured=configured, mode=mode, gesture=gesture):
                        self.assertEqual(passes_guard(config, gesture), enabled)

    def test_empty_gesture_does_not_reach_restart_script(self):
        config = configuration(mode="restart", press_action=[{"delay": 60}])
        running_sequence = object()
        script_starts = []
        for gesture in ("hold", "double_press"):
            # Model the automation boundary: rejection happens before async_run,
            # so the script never receives a request to restart its active run.
            if passes_guard(config, gesture):
                running_sequence = None
                script_starts.append(gesture)
        self.assertIsNotNone(running_sequence)
        self.assertEqual(script_starts, [])

    def test_configured_gesture_still_reaches_restart_script(self):
        config = configuration(mode="restart", hold_action=[{"action": "test.hold"}])
        self.assertTrue(passes_guard(config, "hold"))
        self.assertEqual(config["mode"], "restart")
        choices = config["actions"][0]["choose"]
        branch = next(item for item in choices if item["conditions"][0]["id"] == "hold")
        self.assertEqual(branch["sequence"], [{"action": "test.hold"}])

    def test_non_service_sequences_are_also_configured_actions(self):
        for sequence in ([{"delay": 5}], [{"variables": {"level": 20}}],
                         [{"condition": "state", "entity_id": "light.test", "state": "on"}]):
            with self.subTest(sequence=sequence):
                self.assertTrue(passes_guard(configuration(press_action=sequence), "press"))

    def test_missing_gesture_variables_fail_closed(self):
        self.assertFalse(passes_guard(configuration()))

    def test_guard_is_an_automation_condition_before_action_dispatch(self):
        self.assertIn("conditions", BLUEPRINT)
        self.assertEqual(BLUEPRINT["conditions"][0]["condition"], "template")
        # Inputs stay directly attached to their action branches for execution.
        choices = BLUEPRINT["actions"][0]["choose"]
        for branch in choices:
            gesture = branch["conditions"][0]["id"]
            self.assertEqual(branch["sequence"], Input(GESTURES[gesture]))


if __name__ == "__main__":
    unittest.main()
