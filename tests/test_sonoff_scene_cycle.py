"""Evaluate the actual scene-cycle blueprint's templates and action branches."""

import ast
import math
from pathlib import Path
from types import SimpleNamespace
import unittest

from jinja2 import Environment, StrictUndefined
import yaml

from test_sonoff_empty_actions import Loader, substitute


BLUEPRINT = yaml.load(
    (Path(__file__).resolve().parents[1] / "sonoff_zigbee_scene_cycle/sonoff_zigbee_scene_cycle.yaml")
    .read_text(encoding="utf-8"), Loader=Loader,
)
HELPER = "input_number.scene_position"
DROPDOWN = "input_select.scenes"
SCENES = ["scene.reading", "scene.relax", "scene.bright"]


def is_number(value):
    try:
        return math.isfinite(float(value))
    except (ValueError, TypeError):
        return False


class Stopped(Exception):
    pass


class CycleSimulation:
    def __init__(self, position=0, maximum=3, **inputs):
        defaults = {name: details.get("default")
                    for name, details in BLUEPRINT["blueprint"]["input"].items()}
        defaults.update(button_id="button", state_helper=HELPER, scenes=SCENES)
        defaults.update(inputs)
        self.config = substitute(BLUEPRINT, defaults)
        self.states = {HELPER: str(position), **{scene: "unknown" for scene in SCENES}}
        self.attrs = {HELPER: {"min": 0, "max": maximum, "step": 1}}
        self.calls = []
        self.reason = None
        self.fail_scene = False
        self.env = Environment(undefined=StrictUndefined)
        self.env.globals.update(
            states=lambda entity: self.states.get(entity, "unknown"),
            state_attr=lambda entity, attr: self.attrs.get(entity, {}).get(attr),
            is_state=lambda entity, state: self.states.get(entity) == state,
            is_number=is_number,
            expand=lambda entity: [SimpleNamespace(entity_id=entity, state=self.states[entity])]
                if entity in self.states else [],
        )

    def render(self, value):
        if isinstance(value, dict):
            return {key: self.render(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.render(item) for item in value]
        if not isinstance(value, str) or not ("{{" in value or "{%" in value):
            return value
        result = self.env.from_string(value).render(self.context).strip()
        try:
            return ast.literal_eval(result)
        except (ValueError, SyntaxError):
            return result

    def matches(self, conditions):
        return all(self.gesture == item["id"] if item["condition"] == "trigger"
                   else bool(self.render(item["value_template"])) for item in conditions)

    def execute(self, steps):
        for step in steps:
            if "variables" in step:
                for name, value in step["variables"].items():
                    self.context[name] = self.render(value)
            elif "choose" in step:
                for branch in step["choose"]:
                    if self.matches(branch["conditions"]):
                        self.execute(branch["sequence"])
                        break
                else:
                    self.execute(step.get("default", []))
            elif "if" in step:
                if self.matches(step["if"]):
                    self.execute(step["then"])
            elif "stop" in step:
                raise Stopped(step["stop"])
            elif "action" in step:
                payload = self.render(step)
                self.calls.append(payload)
                if payload["action"] == "scene.turn_on" and self.fail_scene:
                    raise Stopped("Scene service failed")
                if payload["action"] == "input_number.set_value":
                    self.states[payload["target"]["entity_id"]] = str(payload["data"]["value"])
                elif payload["action"] == "input_select.select_option":
                    self.states[payload["target"]["entity_id"]] = payload["data"]["option"]
            else:
                raise AssertionError(step)

    def run(self, gesture="double_press"):
        self.gesture = gesture
        self.context = dict(self.config["variables"])
        if gesture is not None:
            self.context["trigger"] = SimpleNamespace(id=gesture)
            item = next(item for item in self.config["triggers"] if item["id"] == gesture)
            self.context.update(item.get("variables", {}))
        if not self.matches(self.config["conditions"]):
            return False
        try:
            self.execute(self.config["actions"])
        except Stopped as error:
            self.reason = str(error)
        return True


class SonoffSceneCycleTests(unittest.TestCase):
    def dropdown_sim(self, option=None, options=None, **inputs):
        sim = CycleSimulation(scene_source="dropdown", scene_dropdown=DROPDOWN,
                              state_helper="", scenes=[], **inputs)
        sim.states[DROPDOWN] = SCENES[-1] if option is None else option
        sim.attrs[DROPDOWN] = {"options": SCENES.copy() if options is None else options}
        return sim

    def test_three_scene_wraparound_uses_scene_count_with_maximum_three_or_four(self):
        for maximum in (3, 4):
            with self.subTest(maximum=maximum):
                sim = CycleSimulation(maximum=maximum)
                for expected in (1, 2, 3, 1, 2):
                    self.assertTrue(sim.run())
                    self.assertEqual(sim.states[HELPER], str(expected))
                    self.assertEqual(sim.calls[-2]["target"]["entity_id"], SCENES[expected - 1])

    def test_out_of_range_and_fractional_positions_restart_at_scene_one(self):
        for position in (4, -1, 1.5, 99):
            with self.subTest(position=position):
                sim = CycleSimulation(position, maximum=100)
                self.assertTrue(sim.run())
                self.assertEqual(sim.states[HELPER], "1")
                self.assertEqual(sim.calls[0]["target"]["entity_id"], SCENES[0])

    def test_single_scene_repeats_and_preserves_unknown_scene_state_as_valid(self):
        sim = CycleSimulation(scenes=[SCENES[0]])
        for _ in range(3):
            self.assertTrue(sim.run())
            self.assertEqual(sim.states[HELPER], "1")
            self.assertEqual(sim.calls[-2]["target"]["entity_id"], SCENES[0])

    def test_invalid_or_unavailable_helper_does_not_activate_a_scene(self):
        for position in ("unknown", "unavailable", "invalid", "nan", "inf"):
            with self.subTest(position=position):
                sim = CycleSimulation(position)
                self.assertTrue(sim.run())
                self.assertEqual(sim.calls, [])
                self.assertIn("Number helper", sim.reason)

    def test_incompatible_helper_configuration_stops_before_scene_activation(self):
        for attrs in ({"min": 0, "max": 2, "step": 1},
                      {"min": 1, "max": 3, "step": 1},
                      {"min": 0, "max": 3, "step": 0.5}, {}):
            with self.subTest(attributes=attrs):
                sim = CycleSimulation()
                sim.attrs[HELPER] = attrs
                self.assertTrue(sim.run())
                self.assertEqual(sim.calls, [])
                self.assertEqual(sim.states[HELPER], "0")

    def test_missing_or_unavailable_scene_leaves_position_unchanged_for_retry(self):
        for missing in (True, False):
            with self.subTest(missing=missing):
                sim = CycleSimulation(position=1)
                if missing:
                    del sim.states[SCENES[1]]
                else:
                    sim.states[SCENES[1]] = "unavailable"
                self.assertTrue(sim.run())
                self.assertEqual(sim.calls, [])
                self.assertEqual(sim.states[HELPER], "1")
                sim.states[SCENES[1]] = "unknown"
                self.assertTrue(sim.run())
                self.assertEqual(sim.states[HELPER], "2")

    def test_failed_scene_service_does_not_advance_helper(self):
        sim = CycleSimulation(position=1)
        sim.fail_scene = True
        self.assertTrue(sim.run())
        self.assertEqual(sim.states[HELPER], "1")
        self.assertEqual(len(sim.calls), 1)
        sim.fail_scene = False
        sim.run()
        self.assertEqual(sim.states[HELPER], "2")

    def test_press_and_hold_work_with_invalid_cycle_helper_without_advancing_it(self):
        sim = CycleSimulation("unavailable", press_action=[{"action": "test.press"}],
                              hold_action=[{"action": "test.hold"}])
        self.assertTrue(sim.run("press"))
        self.assertTrue(sim.run("hold"))
        self.assertEqual([call["action"] for call in sim.calls], ["test.press", "test.hold"])
        self.assertEqual(sim.states[HELPER], "unavailable")

    def test_empty_scenes_and_empty_actions_are_rejected_before_dispatch(self):
        sim = CycleSimulation(scenes=[])
        for gesture in ("press", "double_press", "hold"):
            self.assertFalse(sim.run(gesture))
        self.assertEqual(sim.calls, [])

    def test_reset_and_scene_list_changes_are_read_on_the_next_press(self):
        sim = CycleSimulation(position=2)
        sim.run()
        self.assertEqual(sim.states[HELPER], "3")
        sim.states[HELPER] = "0"
        sim.run()
        self.assertEqual(sim.states[HELPER], "1")
        sim.config["variables"]["cycle_scenes"] = list(reversed(SCENES))
        sim.states[HELPER] = "0"
        sim.run()
        self.assertEqual(sim.calls[-2]["target"]["entity_id"], SCENES[-1])

    def test_no_gesture_trigger_does_not_select_a_branch(self):
        sim = CycleSimulation()
        self.assertFalse(sim.run(None))
        self.assertEqual(sim.calls, [])

    def test_dropdown_cycles_its_options_without_a_number_helper(self):
        sim = self.dropdown_sim()
        del sim.states[HELPER]
        for scene in (*SCENES, SCENES[0]):
            self.assertTrue(sim.run())
            self.assertEqual(sim.calls[-2]["target"]["entity_id"], scene)
            self.assertEqual(sim.states[DROPDOWN], scene)

    def test_dropdown_current_selection_determines_the_next_scene(self):
        sim = self.dropdown_sim(option=SCENES[0])
        sim.run()
        self.assertEqual(sim.states[DROPDOWN], SCENES[1])
        self.assertEqual(sim.calls[-2]["target"]["entity_id"], SCENES[1])

    def test_dropdown_options_are_read_again_for_each_press(self):
        sim = self.dropdown_sim()
        sim.run()
        sim.attrs[DROPDOWN]["options"] = [SCENES[0], SCENES[2]]
        sim.run()
        self.assertEqual(sim.states[DROPDOWN], SCENES[2])
        self.assertEqual(sim.calls[-2]["target"]["entity_id"], SCENES[2])
        sim.states[DROPDOWN] = "removed-option"
        sim.run()
        self.assertEqual(sim.states[DROPDOWN], SCENES[0])

    def test_invalid_dropdown_helpers_stop_without_using_the_number_mode(self):
        for option in ("unknown", "unavailable"):
            with self.subTest(option=option):
                sim = self.dropdown_sim(option=option)
                self.assertTrue(sim.run())
                self.assertEqual(sim.calls, [])
                self.assertIn("Dropdown helper", sim.reason)
        sim = self.dropdown_sim(options=[])
        self.assertTrue(sim.run())
        self.assertEqual(sim.calls, [])
        sim.config["variables"]["dropdown_helper"] = ""
        self.assertFalse(sim.run())

    def test_friendly_names_and_missing_dropdown_scenes_do_not_advance_selection(self):
        for option in ("Reading", "scene.deleted"):
            with self.subTest(option=option):
                sim = self.dropdown_sim(option=SCENES[0], options=[SCENES[0], option])
                self.assertTrue(sim.run())
                self.assertEqual(sim.states[DROPDOWN], SCENES[0])
                self.assertEqual(sim.calls, [])

    def test_failed_dropdown_scene_activation_leaves_selection_unchanged(self):
        sim = self.dropdown_sim(option=SCENES[0])
        sim.fail_scene = True
        sim.run()
        self.assertEqual(sim.states[DROPDOWN], SCENES[0])
        self.assertEqual(len(sim.calls), 1)

    def test_press_and_hold_do_not_need_an_available_dropdown(self):
        sim = self.dropdown_sim(option="unavailable", press_action=[{"action": "test.press"}],
                                hold_action=[{"action": "test.hold"}])
        sim.run("press")
        sim.run("hold")
        self.assertEqual([call["action"] for call in sim.calls], ["test.press", "test.hold"])
        self.assertEqual(sim.states[DROPDOWN], "unavailable")


if __name__ == "__main__":
    unittest.main()
