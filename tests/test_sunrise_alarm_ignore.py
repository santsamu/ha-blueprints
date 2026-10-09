"""Check daily next-alarm exclusions against the actual blueprint templates."""

from datetime import datetime, timedelta, timezone
import unittest

from test_sunrise_recovery import FINISH, HELPER, Simulation, record


class SunriseAlarmIgnoreTests(unittest.TestCase):
    def alarm_sim(self, alarm_time="07:00:00", start="06:00:00", end="08:00:00",
                  enabled=True, local_timezone=timezone.utc, **inputs):
        sim = Simulation(time_source="next_alarm", next_alarm_sensor="sensor.alarm",
                         next_alarm_ignore_enabled=enabled,
                         next_alarm_ignore_start=start, next_alarm_ignore_end=end,
                         **inputs)
        alarm = datetime.fromisoformat(f"2026-10-09T{alarm_time}").replace(
            tzinfo=local_timezone)
        sim.time = alarm - timedelta(minutes=20)
        # Use a UTC sensor state, as phones commonly do, and a separate local zone.
        sim.states["sensor.alarm"] = alarm.astimezone(timezone.utc).isoformat()
        sim.env.filters["timestamp_custom"] = lambda ts, fmt, local: (
            datetime.fromtimestamp(float(ts), local_timezone if local else timezone.utc)
            .strftime(fmt))
        return sim

    def test_ignored_alarm_does_not_start_lights_or_write_checkpoint(self):
        sim = self.alarm_sim()
        self.assertFalse(sim.run())
        self.assertEqual(sim.context["scheduled_wake_timestamp"], 0)
        self.assertEqual(sim.calls, [])
        self.assertEqual(sim.states[HELPER], "")

    def test_disabled_range_retains_normal_alarm_schedule(self):
        sim = self.alarm_sim(enabled=False)
        self.assertTrue(sim.eligible())
        self.assertEqual(sim.context["wake_timestamp"], FINISH)

    def test_same_day_boundaries_include_start_and_exclude_end(self):
        for alarm_time, allowed in (("05:59:59", True), ("06:00:00", False),
                                    ("07:00:00", False), ("07:59:59", False),
                                    ("08:00:00", True), ("08:00:01", True)):
            with self.subTest(alarm_time=alarm_time):
                self.assertEqual(self.alarm_sim(alarm_time).eligible(), allowed)

    def test_overnight_range_handles_both_sides_of_midnight(self):
        for alarm_time, allowed in (("21:59:59", True), ("22:00:00", False),
                                    ("23:30:00", False), ("00:00:00", False),
                                    ("05:59:59", False), ("06:00:00", True),
                                    ("12:00:00", True)):
            with self.subTest(alarm_time=alarm_time):
                self.assertEqual(self.alarm_sim(alarm_time, start="22:00:00",
                                               end="06:00:00").eligible(), allowed)

    def test_equal_endpoints_disable_exclusion(self):
        self.assertTrue(self.alarm_sim(start="07:00:00", end="07:00:00").eligible())

    def test_seconds_are_respected(self):
        for alarm_time, allowed in (("07:00:00", True), ("07:00:01", False),
                                    ("07:00:02", False), ("07:00:03", True)):
            with self.subTest(alarm_time=alarm_time):
                self.assertEqual(self.alarm_sim(alarm_time, start="07:00:01",
                                               end="07:00:03").eligible(), allowed)

    def test_alarm_time_is_checked_instead_of_current_time(self):
        # The current time is 06:40, inside this range, but the alarm is at its end.
        self.assertTrue(self.alarm_sim(start="06:30:00", end="07:00:00").eligible())
        # Conversely, the check precedes this range, but the alarm falls inside it.
        self.assertFalse(self.alarm_sim(start="07:00:00", end="08:00:00").eligible())

    def test_utc_sensor_timestamp_is_converted_to_local_alarm_time(self):
        for offset in (-5, 2):
            with self.subTest(offset=offset):
                local_zone = timezone(timedelta(hours=offset))
                sim = self.alarm_sim(local_timezone=local_zone)
                self.assertFalse(sim.eligible())
                sim.inputs["next_alarm_ignore_enabled"] = False
                self.assertTrue(sim.eligible())

    def test_manual_mode_is_unaffected(self):
        sim = Simulation(next_alarm_ignore_enabled=True,
                         next_alarm_ignore_start="06:00:00",
                         next_alarm_ignore_end="08:00:00")
        self.assertTrue(sim.eligible())
        self.assertEqual(sim.context["wake_timestamp"], FINISH)

    def test_invalid_missing_and_expired_alarms_are_still_skipped(self):
        for alarm in ("unknown", "unavailable", "invalid", "", "2026-10-08T07:00:00Z"):
            with self.subTest(alarm=alarm):
                sim = self.alarm_sim(enabled=False)
                sim.states["sensor.alarm"] = alarm
                self.assertFalse(sim.eligible())
        sim = self.alarm_sim()
        sim.inputs["next_alarm_sensor"] = ""
        self.assertFalse(sim.eligible())

    def test_legacy_single_sensor_selection_is_filtered(self):
        sim = self.alarm_sim()
        sim.inputs["next_alarm_sensor"] = ["sensor.alarm"]
        self.assertFalse(sim.eligible())
        sim.inputs["next_alarm_ignore_enabled"] = False
        self.assertTrue(sim.eligible())

    def test_recovery_preserves_started_run_even_if_range_now_excludes_alarm(self):
        sim = Simulation(record(), time_source="next_alarm", next_alarm_sensor="sensor.alarm",
                         next_alarm_ignore_enabled=True,
                         next_alarm_ignore_start="06:00:00",
                         next_alarm_ignore_end="08:00:00")
        sim.states["sensor.alarm"] = datetime.fromtimestamp(FINISH, timezone.utc).isoformat()
        self.assertTrue(sim.run())
        self.assertEqual(sim.context["scheduled_wake_timestamp"], 0)
        self.assertEqual(sim.context["wake_timestamp"], FINISH)
        self.assertEqual(sim.calls.count("test.wake_up"), 1)
        self.assertEqual(sim.saved_record()["status"], "completed")


if __name__ == "__main__":
    unittest.main()
