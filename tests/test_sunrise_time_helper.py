"""Check daily scheduling from a time-only input_datetime helper."""

from datetime import datetime, timedelta, timezone
import unittest

from test_sunrise_recovery import FINISH, LIGHTS, START, Simulation, record


TIME_HELPER = "input_datetime.wake_up"


class SunriseTimeHelperTests(unittest.TestCase):
    def helper_sim(self, value="07:00:00", **inputs):
        sim = Simulation(time_source="time_helper", wake_up_time_helper=TIME_HELPER,
                         **inputs)
        sim.states[TIME_HELPER] = value
        sim.attributes[TIME_HELPER] = {"has_time": True, "has_date": False}
        return sim

    def test_helper_time_sets_sunrise_window_instead_of_manual_time(self):
        sim = self.helper_sim(wake_up_time="09:00:00")
        for offset, eligible in ((-1, False), (0, True), (1799, True), (1800, False)):
            with self.subTest(offset=offset):
                sim.time = datetime.fromtimestamp(START + offset, timezone.utc)
                self.assertEqual(sim.eligible(), eligible)
                if eligible:
                    self.assertEqual(sim.context["start_timestamp"], START)
                    self.assertEqual(sim.context["wake_timestamp"], FINISH)

    def test_elapsed_helper_time_schedules_the_next_day(self):
        sim = self.helper_sim()
        sim.time = datetime.fromtimestamp(FINISH, timezone.utc)
        self.assertFalse(sim.eligible())
        self.assertEqual(sim.context["wake_timestamp"], FINISH + 86400)
        sim.time = datetime.fromtimestamp(START + 86400, timezone.utc)
        self.assertTrue(sim.eligible())

    def test_sunrise_crossing_midnight_uses_wake_up_day(self):
        sim = self.helper_sim("00:15:00", weekdays=["sat"])
        sim.time = datetime(2026, 10, 9, 23, 50, tzinfo=timezone.utc)
        self.assertTrue(sim.eligible())
        self.assertEqual(sim.context["wake_timestamp"],
                         datetime(2026, 10, 10, 0, 15, tzinfo=timezone.utc).timestamp())
        sim.inputs["weekdays"] = ["fri"]
        self.assertFalse(sim.eligible())

    def test_time_is_interpreted_in_home_assistant_local_timezone(self):
        for offset in (-5, 2):
            with self.subTest(offset=offset):
                sim = self.helper_sim()
                local_zone = timezone(timedelta(hours=offset))
                sim.time = datetime(2026, 10, 9, 6, 40, tzinfo=local_zone)
                self.assertTrue(sim.eligible())
                self.assertEqual(sim.context["wake_timestamp"],
                                 sim.time.replace(hour=7, minute=0).timestamp())

    def test_helper_changes_update_schedule_before_a_run(self):
        sim = self.helper_sim("08:00:00")
        self.assertFalse(sim.eligible())
        sim.states[TIME_HELPER] = "07:00:00"
        self.assertTrue(sim.eligible())
        self.assertEqual(sim.context["wake_timestamp"], FINISH)

    def test_helper_changes_during_a_run_keep_original_finish(self):
        sim = self.helper_sim()
        sim.events = [(sim.time + timedelta(seconds=20), TIME_HELPER, "09:00:00")]
        self.assertTrue(sim.run())
        self.assertEqual(sim.states[TIME_HELPER], "09:00:00")
        self.assertEqual(sim.time.timestamp(), FINISH)
        self.assertEqual(sim.saved_record()["finish"], FINISH)
        self.assertEqual(sim.calls.count("test.wake_up"), 1)

    def test_missing_unavailable_and_invalid_helpers_skip_without_fallback(self):
        for value in ("unknown", "unavailable", "", "invalid", "24:00:00",
                      "07:60:00", "07:00:60", "2026-10-09 07:00:00"):
            with self.subTest(value=value):
                sim = self.helper_sim(value)
                self.assertFalse(sim.run())
                self.assertEqual(sim.context["scheduled_wake_timestamp"], 0)
                self.assertEqual(sim.calls, [])
        sim = self.helper_sim()
        sim.inputs["wake_up_time_helper"] = ""
        self.assertFalse(sim.eligible())
        sim = self.helper_sim()
        del sim.states[TIME_HELPER]
        self.assertFalse(sim.eligible())

    def test_date_helpers_and_missing_capability_attributes_are_rejected(self):
        for attrs in ({"has_time": False, "has_date": True},
                      {"has_time": True, "has_date": True}, {}):
            with self.subTest(attributes=attrs):
                sim = self.helper_sim()
                sim.attributes[TIME_HELPER] = attrs
                self.assertFalse(sim.eligible())

    def test_next_alarm_ignore_range_does_not_affect_helper_mode(self):
        sim = self.helper_sim(next_alarm_ignore_enabled=True,
                              next_alarm_ignore_start="06:00:00",
                              next_alarm_ignore_end="08:00:00")
        self.assertTrue(sim.eligible())

    def test_unavailable_helper_does_not_affect_manual_or_next_alarm_mode(self):
        sim = Simulation(wake_up_time_helper=TIME_HELPER)
        self.assertTrue(sim.eligible())
        sim.inputs.update(time_source="next_alarm", next_alarm_sensor="sensor.alarm")
        sim.states["sensor.alarm"] = datetime.fromtimestamp(FINISH, timezone.utc).isoformat()
        self.assertTrue(sim.eligible())

    def test_recovery_preserves_original_schedule_after_helper_changes(self):
        for value in ("09:00:00", "unavailable"):
            with self.subTest(value=value):
                sim = self.helper_sim(value, record=record(), sunrise_duration=60)
                self.assertTrue(sim.run())
                self.assertEqual(sim.context["start_timestamp"], START)
                self.assertEqual(sim.context["wake_timestamp"], FINISH)
                self.assertEqual(sim.saved_record()["finish"], FINISH)
                self.assertEqual(sim.calls.count("test.wake_up"), 1)

    def test_switching_off_a_light_still_cancels_helper_mode(self):
        sim = self.helper_sim()
        sim.events = [(sim.time + timedelta(seconds=20), LIGHTS[0], "off")]
        self.assertTrue(sim.run())
        self.assertEqual(sim.saved_record()["status"], "cancelled")
        self.assertNotIn("test.wake_up", sim.calls)


if __name__ == "__main__":
    unittest.main()
