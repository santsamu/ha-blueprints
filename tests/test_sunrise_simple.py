"""Exercise the helper-only sunrise and its enable/disable lifecycle."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

import yaml

from test_sunrise_recovery import BlueprintLoader, FINISH, LIGHTS, START, Simulation, record


BLUEPRINT = yaml.load(
    (Path(__file__).resolve().parents[1] / "sunrise_wake_up_simple/sunrise_wake_up_simple.yaml")
    .read_text(encoding="utf-8"), Loader=BlueprintLoader
)
TIME_HELPER = "input_datetime.wake_up"
ENABLED = "input_boolean.sunrise_enabled"


class SimpleSimulation(Simulation):
    def __init__(self, saved=None, enabled="on", time="07:00:00", **inputs):
        super().__init__(saved, blueprint=BLUEPRINT, wake_up_time_helper=TIME_HELPER,
                         enabled_helper=ENABLED, **inputs)
        self.states[TIME_HELPER] = time
        self.attributes[TIME_HELPER] = {"has_time": True, "has_date": False}
        self.states[ENABLED] = enabled


class SunriseSimpleTests(unittest.TestCase):
    def test_disabled_and_unavailable_toggle_skip_new_runs(self):
        for enabled in ("off", "unknown", "unavailable"):
            with self.subTest(enabled=enabled):
                sim = SimpleSimulation(enabled=enabled)
                self.assertFalse(sim.run())
                self.assertEqual(sim.calls, [])

    def test_helper_supplies_daily_schedule_and_next_day_rollover(self):
        sim = SimpleSimulation()
        self.assertTrue(sim.eligible())
        self.assertEqual(sim.context["start_timestamp"], START)
        self.assertEqual(sim.context["wake_timestamp"], FINISH)
        sim.time = datetime.fromtimestamp(FINISH, timezone.utc)
        self.assertFalse(sim.eligible())
        self.assertEqual(sim.context["wake_timestamp"], FINISH + 86400)

    def test_invalid_time_helpers_are_skipped(self):
        for time in ("unavailable", "unknown", "", "bad", "24:00:00", "2026-10-09 07:00:00"):
            with self.subTest(time=time):
                self.assertFalse(SimpleSimulation(time=time).run())
        sim = SimpleSimulation()
        sim.attributes[TIME_HELPER]["has_date"] = True
        self.assertFalse(sim.run())

    def test_midnight_start_uses_the_wake_up_weekday(self):
        sim = SimpleSimulation(time="00:15:00", weekdays=["sat"])
        sim.time = datetime(2026, 10, 9, 23, 50, tzinfo=timezone.utc)
        self.assertTrue(sim.eligible())
        sim.inputs["weekdays"] = ["fri"]
        self.assertFalse(sim.eligible())

    def test_turning_on_during_window_starts_at_current_progress(self):
        sim = SimpleSimulation(enabled="off")
        self.assertFalse(sim.run())
        sim.states[ENABLED] = "on"
        self.assertTrue(sim.run())
        self.assertEqual(sim.light_calls[0][2]["brightness_pct"], 12)
        self.assertEqual(sim.saved_record()["status"], "completed")
        self.assertEqual(sim.calls.count("test.wake_up"), 1)

    def test_disabling_during_ramp_cancels_and_blocks_same_window_restart(self):
        for state in ("off", "unavailable"):
            with self.subTest(state=state):
                sim = SimpleSimulation()
                disabled_at = sim.time + timedelta(seconds=20)
                sim.events = [(disabled_at, ENABLED, state)]
                self.assertTrue(sim.run())
                self.assertEqual(sim.saved_record()["status"], "cancelled")
                self.assertNotIn("test.wake_up", sim.calls)
                self.assertTrue(all(at < disabled_at.timestamp() for at, _, _ in sim.light_calls))
                sim.states[ENABLED] = "on"
                self.assertFalse(sim.eligible())

    def test_disabling_during_startup_wait_cancels_without_waiting_for_bulbs(self):
        sim = SimpleSimulation(light_state="off")
        sim.turn_on_delays = {entity: 30 for entity in LIGHTS}
        sim.events = [(sim.time + timedelta(seconds=2), ENABLED, "off")]
        self.assertTrue(sim.run())
        self.assertEqual(sim.saved_record()["status"], "cancelled")
        self.assertEqual(sim.wait_calls[0][2] - sim.wait_calls[0][0], 2)
        self.assertNotIn("test.wake_up", sim.calls)

    def test_disabling_between_initial_commands_skips_later_lights_and_cancels(self):
        sim = SimpleSimulation()
        sim.command_latencies = {LIGHTS[0]: 5}
        sim.events = [(sim.time + timedelta(seconds=2), ENABLED, "off")]
        self.assertTrue(sim.run())
        self.assertEqual(len(sim.light_calls), 1)
        self.assertEqual(sim.saved_record()["status"], "cancelled")
        self.assertNotIn("test.wake_up", sim.calls)

    def test_cancellation_during_final_commands_skips_wake_up_actions(self):
        for entity in (ENABLED, LIGHTS[1]):
            with self.subTest(entity=entity):
                sim = SimpleSimulation()
                sim.time = datetime.fromtimestamp(FINISH - 6, timezone.utc)
                sim.command_latencies = {light: 2 for light in LIGHTS}
                sim.events = [(datetime.fromtimestamp(FINISH + 3, timezone.utc), entity, "off")]
                self.assertTrue(sim.run())
                self.assertGreaterEqual(sim.light_calls[-1][0], FINISH)
                self.assertEqual(sim.saved_record()["status"], "cancelled")
                self.assertNotIn("test.wake_up", sim.calls)

    def test_toggle_cancellation_without_recovery_still_blocks_same_window_restart(self):
        sim = SimpleSimulation(helper=False)
        sim.events = [(sim.time + timedelta(seconds=20), ENABLED, "off")]
        self.assertTrue(sim.run())
        sim.states[ENABLED] = "on"
        self.assertFalse(sim.eligible())
        self.assertNotIn("test.wake_up", sim.calls)

    def test_recovery_retains_deadline_after_time_helper_changes_or_becomes_unavailable(self):
        for time in ("09:00:00", "unavailable"):
            with self.subTest(time=time):
                sim = SimpleSimulation(record(), time=time, sunrise_duration=60)
                self.assertTrue(sim.run())
                self.assertEqual(sim.context["start_timestamp"], START)
                self.assertEqual(sim.context["wake_timestamp"], FINISH)
                self.assertEqual(sim.saved_record()["status"], "completed")
                self.assertEqual(sim.calls.count("test.wake_up"), 1)

    def test_disabled_recovery_is_cancelled_even_with_unavailable_lights(self):
        for state in ("off", "unavailable"):
            with self.subTest(state=state):
                sim = SimpleSimulation(record(), enabled=state, light_state="unavailable")
                self.assertTrue(sim.run())
                self.assertEqual(sim.saved_record()["status"], "cancelled")
                self.assertEqual(sim.light_calls, [])
                sim.states[ENABLED] = "on"
                sim.states.update({entity: "on" for entity in LIGHTS})
                self.assertFalse(sim.eligible())

    def test_recovery_still_requires_allowed_day_and_lights_on(self):
        sim = SimpleSimulation(record(), weekdays=["sat"])
        self.assertFalse(sim.eligible())
        sim = SimpleSimulation(record(), light_state="off")
        self.assertTrue(sim.run())
        self.assertEqual(sim.saved_record()["status"], "cancelled")
        self.assertEqual(sim.light_calls, [])

    def test_white_sunrise_clamps_temperature_and_keeps_brightness_only_fallback(self):
        sim = SimpleSimulation(step_seconds=60)
        sim.attributes[LIGHTS[0]].update(supported_color_modes=["color_temp"],
                                        min_color_temp_kelvin=2700, max_color_temp_kelvin=4000)
        self.assertTrue(sim.run())
        white = [data for _, entity, data in sim.light_calls if entity == LIGHTS[0]]
        dimmer = [data for _, entity, data in sim.light_calls if entity == LIGHTS[1]]
        self.assertEqual(white[-1]["color_temp_kelvin"], 4000)
        self.assertTrue(all("color_temp_kelvin" not in data for data in dimmer))
        self.assertTrue(all(data["brightness_pct"] == 100 for data in (white[-1], dimmer[-1])))

    def test_colorful_palette_and_completion_actions_are_retained(self):
        sim = SimpleSimulation(sunrise_style="colorful", step_seconds=60,
                               sunrise_color_100=[0, 255, 0])
        sim.attributes[LIGHTS[0]]["supported_color_modes"] = ["rgb"]
        self.assertTrue(sim.run())
        colors = [data for _, entity, data in sim.light_calls if entity == LIGHTS[0]]
        self.assertEqual(colors[-1]["rgb_color"], [0, 255, 0])
        self.assertEqual(sim.saved_record()["status"], "completed")
        self.assertEqual(sim.calls.count("test.wake_up"), 1)

    def test_invalid_palette_and_unsupported_lights_stop_before_commands(self):
        sim = SimpleSimulation(sunrise_style="colorful", sunrise_color_25=[0, 0, 0])
        self.assertTrue(sim.run())
        self.assertEqual(sim.light_calls, [])
        self.assertEqual(sim.saved_record()["status"], "cancelled")
        sim = SimpleSimulation()
        sim.attributes[LIGHTS[0]]["supported_color_modes"] = ["onoff"]
        self.assertTrue(sim.run())
        self.assertEqual(sim.light_calls, [])
        self.assertEqual(sim.saved_record()["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
