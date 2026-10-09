"""Check the actual sunrise palette, capability fallbacks, and absolute timing."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest

from test_sunrise_recovery import BLUEPRINT, FINISH, LIGHTS, START, Simulation, record


COLOR_INPUTS = [f"sunrise_color_{percent}" for percent in (0, 25, 50, 75, 100)]
DEFAULT_COLORS = [[64, 32, 255], [255, 64, 128], [255, 128, 0],
                  [255, 214, 170], [220, 235, 255]]
CUSTOM_COLORS = [[255, 0, 0], [0, 255, 0], [0, 0, 255],
                 [255, 255, 0], [0, 255, 255]]
PAYLOAD = next(step["repeat"]["sequence"][0]["data"]
               for step in BLUEPRINT["actions"]
               if "repeat" in step and "for_each" in step["repeat"])


class SunriseColorTests(unittest.TestCase):
    def simulation(self, saved=None, **inputs):
        selected_lights = inputs.pop("lights", LIGHTS)
        sim = Simulation(saved, sunrise_style="colorful", **inputs)
        sim.inputs["lights"] = selected_lights
        for entity in LIGHTS:
            sim.attributes[entity]["supported_color_modes"] = ["rgb"]
        return sim

    def initial_payload(self, progress, *, mode="rgb", **inputs):
        sim = self.simulation(**inputs)
        sim.time = datetime.fromtimestamp(START + 1800 * progress, timezone.utc)
        sim.attributes[LIGHTS[0]]["supported_color_modes"] = [mode]
        sim.prepare()
        # Only prepare the run variables; testing the endpoint does not start a new run.
        sim.execute(BLUEPRINT["actions"][1:2])
        if progress == 1:
            sim.context["light_phase"] = "final"
        sim.context["repeat"] = SimpleNamespace(item=LIGHTS[0])
        return sim.render(PAYLOAD)

    def test_default_colors_at_all_five_checkpoints(self):
        for index, expected in enumerate(DEFAULT_COLORS):
            with self.subTest(progress=index / 4):
                payload = self.initial_payload(index / 4)
                self.assertEqual(payload["rgb_color"], expected)
                self.assertNotIn("color_temp_kelvin", payload)

    def test_all_five_colors_are_customizable(self):
        inputs = dict(zip(COLOR_INPUTS, CUSTOM_COLORS))
        for index, expected in enumerate(CUSTOM_COLORS):
            with self.subTest(progress=index / 4):
                self.assertEqual(self.initial_payload(index / 4, **inputs)["rgb_color"], expected)

    def test_intermediate_color_is_blended_and_normalized(self):
        payload = self.initial_payload(0.125, sunrise_color_0=[255, 0, 0],
                                       sunrise_color_25=[0, 0, 255])
        self.assertEqual(payload["rgb_color"], [255, 0, 255])
        self.assertEqual(payload["brightness_pct"], 3)

    def test_dark_rgb_values_do_not_add_another_brightness_curve(self):
        inputs = {name: [10, 20, 40] for name in COLOR_INPUTS}
        payload = self.initial_payload(0.5, initial_brightness=10, final_brightness=50, **inputs)
        self.assertEqual(payload["rgb_color"], [64, 128, 255])
        self.assertEqual(payload["brightness_pct"], 20)

    def test_supported_color_modes_receive_one_rgb_color_field(self):
        for mode in ("rgb", "hs", "xy", "rgbw", "rgbww"):
            with self.subTest(mode=mode):
                payload = self.initial_payload(0, mode=mode)
                self.assertEqual(payload["rgb_color"], DEFAULT_COLORS[0])
                self.assertNotIn("color_temp_kelvin", payload)

    def test_black_checkpoints_cancel_before_any_light_commands(self):
        for name in COLOR_INPUTS:
            with self.subTest(checkpoint=name):
                sim = self.simulation(**{name: [0, 0, 0]})
                self.assertTrue(sim.run())
                self.assertEqual(sim.light_calls, [])
                self.assertNotIn("test.wake_up", sim.calls)
                self.assertEqual(sim.saved_record()["status"], "cancelled")
                self.assertIn("palette", sim.reason)

    def test_malformed_palettes_fail_before_commands(self):
        for color in (None, "red", [], [1, 2], [256, 0, 0], [-1, 255, 0],
                      [1.5, 255, 0], [True, 255, 0], ["bad", 255, 0]):
            with self.subTest(color=color):
                sim = self.simulation(helper=False, sunrise_color_50=color)
                self.assertTrue(sim.run())
                self.assertEqual(sim.light_calls, [])
                self.assertIn("palette", sim.reason)

    def test_white_style_ignores_unused_invalid_palette(self):
        sim = Simulation(sunrise_color_0=[0, 0, 0], step_seconds=60)
        for entity in LIGHTS:
            sim.attributes[entity]["supported_color_modes"] = ["rgb", "color_temp"]
        self.assertTrue(sim.run())
        self.assertIsNone(sim.reason)
        self.assertTrue(all("rgb_color" not in payload for _, _, payload in sim.light_calls))
        self.assertEqual(sim.light_calls[-1][2]["color_temp_kelvin"], 5500)

    def test_mixed_lights_use_palette_temperature_and_brightness_fallbacks(self):
        dimmer = "light.dimmer"
        sim = self.simulation(lights=LIGHTS + [dimmer], step_seconds=60,
                              sunrise_color_100=[128, 0, 64])
        sim.states[dimmer] = "on"
        sim.attributes[dimmer] = {"supported_color_modes": ["brightness"], "supported_features": 0}
        sim.attributes[LIGHTS[0]]["supported_color_modes"] = ["rgb", "color_temp"]
        sim.attributes[LIGHTS[1]].update(supported_color_modes=["color_temp"],
                                       min_color_temp_kelvin=2700, max_color_temp_kelvin=4000)
        self.assertTrue(sim.run())
        rgb = [data for _, entity, data in sim.light_calls if entity == LIGHTS[0]]
        white = [data for _, entity, data in sim.light_calls if entity == LIGHTS[1]]
        dim = [data for _, entity, data in sim.light_calls if entity == dimmer]
        self.assertTrue(all("rgb_color" in data and "color_temp_kelvin" not in data for data in rgb))
        self.assertEqual(rgb[-1]["rgb_color"], [255, 0, 128])
        self.assertTrue(all(2700 <= data["color_temp_kelvin"] <= 4000 and "rgb_color" not in data
                            for data in white))
        self.assertEqual(white[-1]["color_temp_kelvin"], 4000)
        self.assertTrue(all(set(data) == {"brightness_pct"} for data in dim))
        self.assertEqual(sim.calls.count("test.wake_up"), 1)

    def test_fades_reach_checkpoints_without_crossing_them(self):
        sim = self.simulation(step_seconds=60)
        sim.time = datetime.fromtimestamp(START + 432, timezone.utc)
        sim.command_latencies = {entity: 2 for entity in LIGHTS}
        self.assertTrue(sim.run())
        first, second = sim.light_calls[2:4]
        self.assertEqual(first[2]["rgb_color"], DEFAULT_COLORS[1])
        self.assertEqual(second[2]["rgb_color"], DEFAULT_COLORS[1])
        self.assertEqual(first[0] + first[2]["transition"], START + 450)
        self.assertEqual(second[0] + second[2]["transition"], START + 450)
        self.assertEqual(sim.call_times[-1], ("test.wake_up", FINISH + 4))

    def test_stepping_lights_use_color_at_actual_command_time(self):
        sim = self.simulation(step_seconds=60, sunrise_color_0=[255, 0, 0],
                              sunrise_color_25=[0, 0, 255])
        sim.time = datetime.fromtimestamp(START + 225, timezone.utc)
        for entity in LIGHTS:
            sim.attributes[entity]["supported_features"] = 0
        self.assertTrue(sim.run())
        self.assertEqual(sim.light_calls[2][2]["rgb_color"], [255, 0, 255])
        self.assertTrue(all("transition" not in data for _, _, data in sim.light_calls))
        self.assertEqual(sim.light_calls[-1][0], FINISH)

    def test_late_commands_catch_up_to_current_color(self):
        sim = self.simulation(**dict(zip(COLOR_INPUTS, CUSTOM_COLORS)))
        sim.time = datetime.fromtimestamp(FINISH - 110, timezone.utc)
        sim.command_latencies = {entity: 20 for entity in LIGHTS}
        self.assertTrue(sim.run())
        when, _, payload = sim.light_calls[3]
        self.assertEqual(when, FINISH - 50)
        self.assertEqual(payload["transition"], 0)
        self.assertEqual(payload["brightness_pct"], 95)
        self.assertEqual(payload["rgb_color"], [28, 255, 227])
        self.assertTrue(all(data.get("transition", 0) >= 0 for _, _, data in sim.light_calls))

    def test_recovery_uses_original_times_and_current_palette(self):
        sim = self.simulation(record(), sunrise_duration=60, wake_up_time="08:00:00", step_seconds=60)
        self.assertTrue(sim.run())
        self.assertEqual(sim.light_calls[0][2]["rgb_color"], [255, 85, 85])
        self.assertEqual(sim.saved_record(), record("completed"))
        changed = self.simulation(record(), **{name: [0, 64, 0] for name in COLOR_INPUTS})
        self.assertTrue(changed.run())
        self.assertEqual(changed.light_calls[0][2]["rgb_color"], [0, 255, 0])

    def test_cancellation_does_not_apply_final_color_or_wake_up_actions(self):
        sim = self.simulation(step_seconds=60, sunrise_color_100=[0, 255, 0])
        sim.events = [(sim.time + timedelta(seconds=20), LIGHTS[0], "off")]
        self.assertTrue(sim.run())
        self.assertEqual(sim.saved_record()["status"], "cancelled")
        self.assertNotIn("test.wake_up", sim.calls)
        self.assertTrue(all(data["rgb_color"] != [0, 255, 0] for _, _, data in sim.light_calls))


if __name__ == "__main__":
    unittest.main()
