"""Check per-light payloads for mixed capabilities using the actual blueprint."""

import unittest

from test_sunrise_recovery import FINISH, LIGHTS, Simulation, record


class SunriseLightCapabilityTests(unittest.TestCase):
    def test_on_off_only_light_stops_before_any_light_commands(self):
        sim = Simulation()
        sim.attributes[LIGHTS[1]]["supported_color_modes"] = ["onoff"]
        self.assertTrue(sim.run())
        self.assertEqual(sim.light_calls, [])
        self.assertNotIn("test.wake_up", sim.calls)
        self.assertIn("dimming support", sim.reason)
        self.assertEqual(sim.context["unsupported_lights"], [LIGHTS[1]])
        self.assertEqual(sim.saved_record()["status"], "cancelled")

    def test_missing_or_unknown_color_modes_do_not_assume_dimming(self):
        for modes in (None, [], ["unknown"]):
            with self.subTest(modes=modes):
                sim = Simulation(helper=False)
                sim.attributes[LIGHTS[0]]["supported_color_modes"] = modes
                self.assertTrue(sim.run())
                self.assertEqual(sim.light_calls, [])
                self.assertIn("dimming support", sim.reason)

    def test_rgb_and_white_modes_are_recognized_as_dimmable(self):
        for mode in ("brightness", "color_temp", "hs", "xy", "rgb", "rgbw", "rgbww", "white"):
            with self.subTest(mode=mode):
                sim = Simulation(step_seconds=60)
                sim.attributes[LIGHTS[0]]["supported_color_modes"] = [mode]
                self.assertTrue(sim.run())
                self.assertIsNone(sim.reason)
                self.assertEqual(sim.calls.count("test.wake_up"), 1)

    def test_mixed_lights_use_fades_and_current_time_steps(self):
        sim = Simulation(step_seconds=60)
        # Other feature bits alongside TRANSITION must not disable fades.
        sim.attributes[LIGHTS[0]]["supported_features"] = 36
        sim.attributes[LIGHTS[1]]["supported_features"] = 4
        self.assertTrue(sim.run())
        fading = [(time, payload) for time, entity, payload in sim.light_calls
                  if entity == LIGHTS[0]]
        stepping = [(time, payload) for time, entity, payload in sim.light_calls
                    if entity == LIGHTS[1]]
        self.assertTrue(all("transition" in payload for _, payload in fading))
        self.assertTrue(all("transition" not in payload for _, payload in stepping))
        self.assertEqual(fading[1][1]["transition"], 60)
        self.assertEqual(fading[1][1]["brightness_pct"], 14)
        self.assertEqual(stepping[1][1]["brightness_pct"], 12)
        self.assertEqual(stepping[1][1]["brightness_pct"], stepping[0][1]["brightness_pct"])
        self.assertEqual(fading[-1][1]["brightness_pct"], 100)
        self.assertEqual(stepping[-1][1]["brightness_pct"], 100)
        self.assertEqual(stepping[-1][0], FINISH)
        self.assertEqual(sim.calls.count("test.wake_up"), 1)

    def test_missing_transition_feature_uses_steps(self):
        sim = Simulation(step_seconds=60)
        sim.attributes[LIGHTS[0]].pop("supported_features")
        self.assertTrue(sim.run())
        payloads = [payload for _, entity, payload in sim.light_calls if entity == LIGHTS[0]]
        self.assertTrue(all("transition" not in payload for payload in payloads))
        self.assertEqual(payloads[-1]["brightness_pct"], 100)

    def test_temperature_is_clamped_per_light_and_skipped_for_rgb(self):
        sim = Simulation(step_seconds=60)
        sim.attributes[LIGHTS[0]].update(
            supported_color_modes=["color_temp"], min_color_temp_kelvin=2700,
            max_color_temp_kelvin=4000,
        )
        sim.attributes[LIGHTS[1]]["supported_color_modes"] = ["rgb"]
        self.assertTrue(sim.run())
        tunable = [payload for _, entity, payload in sim.light_calls if entity == LIGHTS[0]]
        rgb = [payload for _, entity, payload in sim.light_calls if entity == LIGHTS[1]]
        self.assertTrue(all(2700 <= payload["color_temp_kelvin"] <= 4000 for payload in tunable))
        self.assertEqual(tunable[0]["color_temp_kelvin"], 2700)
        self.assertEqual(tunable[-1]["color_temp_kelvin"], 4000)
        self.assertTrue(all("color_temp_kelvin" not in payload for payload in rgb))

    def test_temperature_steps_use_current_progress(self):
        sim = Simulation(step_seconds=60)
        for entity in LIGHTS:
            sim.attributes[entity].update(supported_color_modes=["color_temp"])
        sim.attributes[LIGHTS[1]]["supported_features"] = 0
        self.assertTrue(sim.run())
        fading = [payload for _, entity, payload in sim.light_calls if entity == LIGHTS[0]]
        stepping = [payload for _, entity, payload in sim.light_calls if entity == LIGHTS[1]]
        self.assertEqual(stepping[1]["color_temp_kelvin"], stepping[0]["color_temp_kelvin"])
        self.assertGreater(fading[1]["color_temp_kelvin"], fading[0]["color_temp_kelvin"])
        self.assertEqual(stepping[-1]["color_temp_kelvin"], 5500)

    def test_recovery_with_unsupported_light_is_cancelled_without_light_commands(self):
        sim = Simulation(record())
        sim.attributes[LIGHTS[0]]["supported_color_modes"] = ["onoff"]
        self.assertTrue(sim.run())
        self.assertEqual(sim.light_calls, [])
        self.assertEqual(sim.saved_record()["status"], "cancelled")
        self.assertFalse(sim.eligible())


if __name__ == "__main__":
    unittest.main()
