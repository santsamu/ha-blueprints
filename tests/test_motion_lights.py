"""Evaluate the motion blueprint's actual templates with representative state reports."""

import ast
from copy import deepcopy
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from types import SimpleNamespace
import unittest

from jinja2 import Environment, StrictUndefined
import yaml


class Input(str):
    pass


class Loader(yaml.SafeLoader):
    pass


Loader.add_constructor("!input", lambda loader, node: Input(loader.construct_scalar(node)))
BLUEPRINT = yaml.load(
    (Path(__file__).resolve().parents[1] / "sonoff_motion_lights/sonoff_motion_lights.yaml")
    .read_text(encoding="utf-8"), Loader=Loader,
)


def variable_template(name, node=BLUEPRINT):
    """Find an action variable without coupling tests to action indices."""
    if isinstance(node, dict):
        if name in node.get("variables", {}):
            return node["variables"][name]
        for value in node.values():
            result = variable_template(name, value)
            if result is not None:
                return result
    elif isinstance(node, list):
        for value in node:
            result = variable_template(name, value)
            if result is not None:
                return result
    return None


def find_step(key, node=BLUEPRINT):
    if isinstance(node, dict):
        if key in node:
            return node
        for value in node.values():
            result = find_step(key, value)
            if result is not None:
                return result
    elif isinstance(node, list):
        for value in node:
            result = find_step(key, value)
            if result is not None:
                return result
    return None


class States(dict):
    def __call__(self, entity):
        return self[entity].state if entity in self else "unknown"


class Templates:
    def __init__(self, **inputs):
        self.inputs = {name: details.get("default")
                       for name, details in BLUEPRINT["blueprint"]["input"].items()}
        self.inputs.update(motion_sensor="binary_sensor.motion", lights=["light.test"], **inputs)
        self.states = States()
        self.set("binary_sensor.motion", "on")
        self.set("light.test", "off", supported_color_modes=["brightness"])
        self.env = Environment(undefined=StrictUndefined)
        self.env.filters["bitwise_and"] = lambda value, mask: int(value) & mask
        self.env.globals.update(states=self.states, is_state=lambda e, s: self.states(e) == s,
                                state_attr=lambda e, a: self.states[e].attributes.get(a)
                                if e in self.states else None,
                                as_timestamp=lambda d: d.timestamp(),
                                now=lambda: datetime.fromtimestamp(1000, timezone.utc))
        self.context = {}
        self.assign(BLUEPRINT["variables"])

    def set(self, entity, power, updated=1000, changed=1000, **attrs):
        self.states[entity] = SimpleNamespace(
            entity_id=entity, state=power, attributes=attrs,
            last_updated=datetime.fromtimestamp(updated, timezone.utc),
            last_changed=datetime.fromtimestamp(changed, timezone.utc),
        )

    def render(self, value):
        if isinstance(value, Input):
            return self.inputs[value]
        if not isinstance(value, str) or not ("{{" in value or "{%" in value):
            return value
        rendered = self.env.from_string(value).render(self.context).strip()
        try:
            return ast.literal_eval(rendered)
        except (ValueError, SyntaxError):
            return rendered

    def assign(self, values):
        for key, value in values.items():
            self.context[key] = self.render(value)

    def command(self, modes, **attrs):
        self.set("light.test", "on", supported_color_modes=modes, **attrs)
        for name in ("night", "style", "brightness", "temperature", "color"):
            self.context[name] = self.render(variable_template(name))
        self.context.update(observed_entity="light.test")
        self.context["modes"] = self.render(variable_template("modes"))
        result = self.render(variable_template("command"))
        self.context["command"] = result
        return result

    def unchanged(self, reference, observed):
        self.context.update(reference=reference, observed=observed)
        return self.render(variable_template("unchanged"))


def report(mode="brightness", brightness=204, updated=1000, changed=1000, **attrs):
    return dict(entity_id="light.test", state="on", updated=updated, changed=changed,
                attributes=dict(color_mode=mode, brightness=brightness, **attrs))


class MotionLightTemplateTests(unittest.TestCase):
    def test_legacy_color_mode_enums_are_normalized_before_command_rendering(self):
        class LegacyMode(StrEnum):
            RGB = "rgb"

        sim = Templates(day_style="color", day_color=[128, 0, 0])
        self.assertEqual(sim.command([LegacyMode.RGB]), {"brightness": 204, "rgb_color": [255, 0, 0]})
        self.assertEqual(sim.context["modes"], ["rgb"])

    def test_baseline_omits_enum_objects_from_legacy_state_attributes(self):
        class LegacyMode(StrEnum):
            RGB = "rgb"

        sim = Templates()
        sim.set("light.test", "on", supported_color_modes=[LegacyMode.RGB],
                color_mode=LegacyMode.RGB, brightness=204, rgb_color=(255, 0, 0))
        sim.context["observed_entity"] = "light.test"
        snapshot = sim.render(variable_template("observed"))
        self.assertIsInstance(snapshot, dict)
        self.assertEqual(snapshot["attributes"]["color_mode"], "rgb")
        self.assertEqual(snapshot["attributes"]["rgb_color"], (255, 0, 0))
        self.assertNotIn("supported_color_modes", snapshot["attributes"])

    def test_duration_conversion_and_zero_guard(self):
        sim = Templates(duration={"days": 1, "hours": 2, "minutes": 3, "seconds": 4})
        self.assertEqual(sim.context["duration_seconds"], 93784)
        for duration in ({}, {"seconds": 0}, {"seconds": -1}):
            with self.subTest(duration=duration):
                sim = Templates(duration=duration)
                self.assertFalse(sim.render(BLUEPRINT["conditions"][0]["value_template"]))

    def test_shared_profile_does_not_require_a_daylight_source(self):
        sim = Templates()
        self.assertTrue(sim.render(BLUEPRINT["conditions"][0]["value_template"]))
        self.assertEqual(sim.command(["brightness"])["brightness"], 204)

    def test_sun_and_binary_sources_select_profiles(self):
        for mode, entity, day, night in (("sun", "sun.sun", "above_horizon", "below_horizon"),
                                        ("binary", "binary_sensor.daylight", "on", "off")):
            for state, expected in ((day, 204), (night, 51)):
                with self.subTest(mode=mode, state=state):
                    sim = Templates(daylight_mode=mode, daylight_sensor=entity)
                    sim.set(entity, state)
                    self.assertTrue(sim.render(BLUEPRINT["conditions"][0]["value_template"]))
                    self.assertEqual(sim.command(["brightness"])["brightness"], expected)

    def test_invalid_daylight_source_blocks_activation(self):
        for source in ("sun", "binary"):
            sim = Templates(daylight_mode=source)
            self.assertFalse(sim.render(BLUEPRINT["conditions"][0]["value_template"]))

    def test_mixed_capabilities_receive_only_supported_parameters(self):
        for modes, expected in ((["onoff"], {}), (["brightness"], {"brightness": 204}),
                                (["color_temp"], {"brightness": 204, "color_temp_kelvin": 4000}),
                                (["rgb"], {"brightness": 204})):
            with self.subTest(modes=modes):
                self.assertEqual(Templates().command(modes), expected)

    def test_color_is_normalized_and_delegated_to_native_light_conversion(self):
        for mode in ("rgb", "rgbw", "rgbww", "hs", "xy"):
            with self.subTest(mode=mode):
                sim = Templates(day_style="color", day_color=[128, 64, 0])
                self.assertEqual(sim.command([mode]), {"brightness": 204, "rgb_color": [255, 128, 0]})

    def test_color_fallback_and_temperature_limits(self):
        sim = Templates(day_style="color", day_temperature=1500)
        command = sim.command(["color_temp"], min_color_temp_kelvin=2700, max_color_temp_kelvin=6500)
        self.assertEqual(command["color_temp_kelvin"], 2700)
        sim = Templates(day_temperature=9000)
        self.assertEqual(sim.command(["color_temp"], max_color_temp_kelvin=6500)["color_temp_kelvin"], 6500)

    def test_keep_mode_and_transition_support(self):
        sim = Templates(day_style="keep")
        self.assertEqual(sim.command(["color_temp"], supported_features=32), {"brightness": 204, "transition": 0})
        self.assertEqual(sim.command(["color_temp"]), {"brightness": 204})

    def test_confirmation_rejects_unreported_commands(self):
        sim = Templates()
        sim.command(["color_temp"])
        confirmation = find_step("wait_template")["wait_template"]
        self.assertFalse(sim.render(confirmation))
        sim.set("light.test", "on", brightness=204, color_mode="color_temp", color_temp_kelvin=4000)
        self.assertTrue(sim.render(confirmation))
        sim.set("light.test", "on", brightness=100, color_mode="color_temp", color_temp_kelvin=4000)
        self.assertFalse(sim.render(confirmation))

    def test_override_comparison_supports_all_native_color_modes(self):
        sim = Templates()
        for mode, key, value, replacement in (
            ("color_temp", "color_temp_kelvin", 4000, 5000),
            ("rgb", "rgb_color", [255, 0, 0], [0, 255, 0]),
            ("rgbw", "rgbw_color", [255, 0, 0, 0], [0, 255, 0, 0]),
            ("rgbww", "rgbww_color", [255, 0, 0, 0, 0], [0, 255, 0, 0, 0]),
            ("hs", "hs_color", [0, 100], [120, 100]),
            ("xy", "xy_color", [0.7, 0.3], [0.2, 0.4]),
        ):
            with self.subTest(mode=mode):
                reference = report(mode, **{key: value})
                self.assertTrue(sim.unchanged(reference, deepcopy(reference)))
                self.assertFalse(sim.unchanged(reference, report(mode, **{key: replacement})))

    def test_unrelated_attributes_and_rounding_are_ignored_against_original_baseline(self):
        sim = Templates()
        reference = report("color_temp", color_temp_kelvin=4000)
        observed = report("color_temp", brightness=203, updated=1001, color_temp_kelvin=4010, linkquality=80)
        self.assertTrue(sim.unchanged(reference, observed))
        observed["attributes"]["brightness"] = 202
        self.assertFalse(sim.unchanged(reference, observed), "Rounding drift must not move the baseline")
        self.assertTrue(sim.unchanged(report("hs", hs_color=[359.9, 100]), report("hs", hs_color=[0.1, 100])))

    def test_power_mode_and_unavailability_changes_release_light(self):
        sim = Templates()
        reference = report()
        for updates in ({"state": "off"}, {"state": "unavailable"}, {"changed": 1001},
                        {"attributes": {"color_mode": "white", "brightness": 204}}):
            with self.subTest(updates=updates):
                self.assertFalse(sim.unchanged(reference, dict(reference, **updates)))

    def test_deadlines_use_original_start_or_latest_motion_clear_time(self):
        sim = Templates(duration={"seconds": 30})
        sim.context.update(session_start=900)
        self.assertEqual(sim.render(variable_template("deadline")), 0)
        sim.set("binary_sensor.motion", "off", changed=950)
        self.assertEqual(sim.render(variable_template("deadline")), 980)
        sim.context["timer"] = "fixed"
        self.assertEqual(sim.render(variable_template("deadline")), 930)


if __name__ == "__main__":
    unittest.main()
