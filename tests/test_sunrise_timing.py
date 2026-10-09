"""Regressions for command latency and the original wake-up deadline."""

from datetime import datetime, timedelta, timezone
import unittest

from test_sunrise_recovery import FINISH, LIGHTS, Simulation


class SunriseTimingTests(unittest.TestCase):
    def simulation(self, latency, **inputs):
        sim = Simulation(**inputs)
        sim.command_latencies = {entity: latency for entity in LIGHTS}
        return sim

    def test_commands_do_not_add_their_latency_to_each_update_interval(self):
        sim = self.simulation(2, step_seconds=60)
        self.assertTrue(sim.run())
        times = [time for time, entity, _ in sim.light_calls if entity == LIGHTS[0]]
        self.assertEqual(times[2] - times[1], 60)
        self.assertEqual(times[3] - times[2], 60)

    def test_later_lights_share_the_same_transition_deadline(self):
        sim = self.simulation(2, step_seconds=60)
        self.assertTrue(sim.run())
        first = sim.light_calls[2]
        second = sim.light_calls[3]
        self.assertEqual(first[2]["transition"], 60)
        self.assertEqual(second[2]["transition"], 58)
        self.assertEqual(first[0] + first[2]["transition"],
                         second[0] + second[2]["transition"])

    def test_last_wait_stops_at_wake_up_time(self):
        sim = self.simulation(2, step_seconds=60)
        sim.time = datetime.fromtimestamp(FINISH - 30, timezone.utc)
        self.assertTrue(sim.run())
        self.assertEqual(sim.wait_calls[-1], (FINISH - 22, 22, FINISH))
        # Final commands still take four seconds; the loop adds no extra wait.
        self.assertEqual(sim.call_times[-1], ("test.wake_up", FINISH + 4))

    def test_commands_crossing_wake_up_time_do_not_add_another_wait(self):
        sim = self.simulation(6, step_seconds=60)
        sim.time = datetime.fromtimestamp(FINISH - 20, timezone.utc)
        self.assertTrue(sim.run())
        self.assertEqual(sim.wait_calls[-1], (FINISH + 4, 0, FINISH + 4))
        self.assertEqual(sim.call_times[-1], ("test.wake_up", FINISH + 16))
        self.assertTrue(all(payload.get("transition", 0) >= 0
                            for _, _, payload in sim.light_calls))

    def test_missed_update_uses_current_progress_without_a_negative_transition(self):
        sim = self.simulation(20)
        sim.time = datetime.fromtimestamp(FINISH - 110, timezone.utc)
        self.assertTrue(sim.run())
        time, _, payload = sim.light_calls[3]
        self.assertEqual(time, FINISH - 50)
        self.assertEqual(payload["transition"], 0)
        self.assertEqual(payload["brightness_pct"], 95)

    def test_stepping_lights_use_their_actual_command_time(self):
        sim = self.simulation(30, step_seconds=60)
        for entity in LIGHTS:
            sim.attributes[entity]["supported_features"] = 0
        self.assertTrue(sim.run())
        first = sim.light_calls[2]
        second = sim.light_calls[3]
        self.assertEqual(second[0] - first[0], 30)
        self.assertEqual(first[2]["brightness_pct"], 14)
        self.assertEqual(second[2]["brightness_pct"], 16)

    def test_cancellation_after_slow_commands_still_skips_wake_up_actions(self):
        sim = self.simulation(2, step_seconds=60)
        sim.events = [(sim.time + timedelta(seconds=20), LIGHTS[0], "off")]
        self.assertTrue(sim.run())
        self.assertIn("switched off", sim.reason)
        self.assertEqual(sim.saved_record()["status"], "cancelled")
        self.assertNotIn("test.wake_up", sim.calls)


if __name__ == "__main__":
    unittest.main()
