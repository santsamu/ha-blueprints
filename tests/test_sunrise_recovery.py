"""Exercise the blueprint itself with a small simulated Home Assistant context."""

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from datetime import datetime, timedelta, timezone

import yaml
from jinja2 import Environment, StrictUndefined


class BlueprintInput(str):
    pass


class BlueprintLoader(yaml.SafeLoader):
    pass


BlueprintLoader.add_constructor(
    "!input", lambda loader, node: BlueprintInput(loader.construct_scalar(node))
)
BLUEPRINT = yaml.load(
    (Path(__file__).resolve().parents[1] / "sunrise_wake_up/sunrise_wake_up.yaml")
    .read_text(encoding="utf-8"), Loader=BlueprintLoader
)
HELPER = "input_text.sunrise_recovery"
LIGHTS = ["light.bedside_left", "light.bedside_right"]
START = datetime(2026, 10, 9, 6, 30, tzinfo=timezone.utc).timestamp()
FINISH = START + 1800


def as_timestamp(value, default=0):
    if isinstance(value, datetime):
        return value.timestamp()
    try:
        return float(value)
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except (AttributeError, TypeError, ValueError):
            return default


class Stopped(Exception):
    pass


class Simulation:
    def __init__(self, record=None, helper=True, light_state="on", **inputs):
        self.time = datetime.fromtimestamp(START + 600, timezone.utc)
        self.inputs = {key: value.get("default")
                       for key, value in BLUEPRINT["blueprint"]["input"].items()}
        self.inputs.update(lights=LIGHTS, recovery_helper=HELPER if helper else "",
                           after_sunrise=[{"action": "test.wake_up"}], **inputs)
        self.states = {entity: light_state for entity in LIGHTS}
        self.attributes = {entity: {"supported_color_modes": ["brightness"],
                                   "supported_features": 32} for entity in LIGHTS}
        self.states[HELPER] = (
            f"{record['status']}|{record['beginning']}|{record['finish']}"
            if record is not None else ""
        )
        self.last_triggered = START + 1 if record is not None else None
        self.events = []
        self.turn_on_delays = {}
        self.command_latencies = {}
        self.calls = []
        self.call_times = []
        self.light_calls = []
        self.wait_calls = []
        self.reason = None
        self.after_wait = lambda completed: None
        self.env = Environment(undefined=StrictUndefined)
        self.env.filters.update(
            bitwise_and=lambda value, mask: int(value) & mask,
            timestamp_custom=lambda ts, fmt, local: datetime.fromtimestamp(
                float(ts), timezone.utc).strftime(fmt),
        )
        self.env.globals.update(
            now=lambda: self.time, timedelta=timedelta,
            today_at=lambda value: self.time.replace(
                hour=int(value.split(":")[0]), minute=int(value.split(":")[1]),
                second=int(value.split(":")[2]), microsecond=0),
            states=lambda entity: self.states.get(entity, "unknown"),
            as_timestamp=as_timestamp,
            expand=lambda entities: [SimpleNamespace(entity_id=entity,
                state=self.states.get(entity, "unknown")) for entity in sorted(set(entities))],
            is_state=lambda entity, state: self.states.get(entity) == state,
            state_attr=lambda entity, attr: self.attributes.get(entity, {}).get(attr),
        )

    def render(self, value, text=False):
        if isinstance(value, BlueprintInput):
            return self.inputs[value]
        if isinstance(value, dict):
            return {key: self.render(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.render(item) for item in value]
        if not isinstance(value, str) or not ("{{" in value or "{%" in value):
            return value
        rendered = self.env.from_string(value).render(self.context).strip()
        if text:
            return rendered
        try:
            return ast.literal_eval(rendered)
        except (ValueError, SyntaxError):
            return rendered

    def prepare(self):
        self.context = {"this": SimpleNamespace(
            attributes={"last_triggered": self.last_triggered})}
        for name, value in BLUEPRINT["variables"].items():
            self.context[name] = self.render(value)

    def matches(self, conditions):
        return all(bool(self.render(item["value_template"])) for item in conditions)

    def eligible(self):
        self.prepare()
        return self.matches(BLUEPRINT["conditions"])

    def advance(self, seconds):
        deadline = self.time + timedelta(seconds=seconds)
        while self.events and self.events[0][0] <= deadline:
            event_time, entity, state = self.events.pop(0)
            self.time = max(self.time, event_time)
            self.states[entity] = state
        self.time = deadline

    def wait(self, step):
        started = self.time.timestamp()
        timeout = float(self.render(step["timeout"]["seconds"]))
        assert timeout >= 0
        deadline = self.time + timedelta(seconds=timeout)
        completed = bool(self.render(step["wait_template"]))
        while not completed and self.events and self.events[0][0] <= deadline:
            event_time, entity, state = self.events.pop(0)
            self.time = max(self.time, event_time)
            self.states[entity] = state
            completed = bool(self.render(step["wait_template"]))
        if not completed:
            self.time = deadline
        self.context["wait"] = SimpleNamespace(completed=completed)
        self.wait_calls.append((started, timeout, self.time.timestamp()))
        self.after_wait(completed)

    def execute_nested(self, steps):
        # Nested sequence variables must not be relied on to modify parent scope.
        parent_context = self.context
        self.context = parent_context.copy()
        try:
            self.execute(steps)
        finally:
            self.context = parent_context

    def execute(self, steps):
        for step in steps:
            if "variables" in step:
                for name, value in step["variables"].items():
                    self.context[name] = self.render(value)
            elif "condition" in step:
                if not self.matches([step]):
                    raise Stopped("Condition failed")
            elif "if" in step:
                self.execute_nested(step["then"] if self.matches(step["if"])
                                    else step.get("else", []))
            elif "stop" in step:
                raise Stopped(step["stop"])
            elif "wait_template" in step:
                self.wait(step)
            elif "repeat" in step:
                repeat = step["repeat"]
                if "for_each" in repeat:
                    for item in self.render(repeat["for_each"]):
                        self.context["repeat"] = SimpleNamespace(item=item)
                        self.execute_nested(repeat["sequence"])
                else:
                    for _ in range(2000):
                        if not self.matches(repeat["while"]):
                            break
                        self.execute_nested(repeat["sequence"])
                    else:
                        raise AssertionError("Loop did not finish")
            elif "choose" in step:
                self.execute(self.render(step["default"]))
            elif "action" in step:
                action = step["action"]
                self.calls.append(action)
                self.call_times.append((action, self.time.timestamp()))
                if action == "input_text.set_value":
                    value = self.render(step["data"]["value"], text=True)
                    assert len(value) <= 255
                    self.states[self.render(step["target"]["entity_id"])] = value
                elif action == "light.turn_on":
                    payload = self.render(step["data"])
                    entity = self.render(step["target"]["entity_id"])
                    self.light_calls.append((self.time.timestamp(), entity, payload))
                    delay = self.turn_on_delays.get(entity, 0)
                    if delay:
                        self.events.append((self.time + timedelta(seconds=delay), entity, "on"))
                        self.events.sort()
                    else:
                        self.states[entity] = "on"
                    self.advance(self.command_latencies.get(entity, 0))
            else:
                raise AssertionError(f"Unsupported step: {step}")

    def run(self):
        if not self.eligible():
            return False
        self.last_triggered = self.time
        try:
            self.execute(BLUEPRINT["actions"])
        except Stopped as exc:
            self.reason = str(exc)
        return True

    def saved_record(self):
        status, beginning, finish = self.states[HELPER].split("|")
        return dict(status=status, beginning=float(beginning), finish=float(finish))


def record(status="running", beginning=START, finish=FINISH):
    return dict(status=status, beginning=beginning, finish=finish)


class SunriseRecoveryTests(unittest.TestCase):
    def test_recovery_keeps_original_schedule_after_settings_change(self):
        sim = Simulation(record(), wake_up_time="08:00:00", sunrise_duration=60)
        self.assertTrue(sim.eligible())
        self.assertEqual(sim.context["wake_timestamp"], FINISH)
        self.assertEqual(sim.context["start_timestamp"], START)
        self.assertEqual(sim.context["duration_seconds"], 1800)
        sim.execute(BLUEPRINT["actions"][:2])
        self.assertAlmostEqual(sim.context["initial_progress"], 1 / 3)
        self.assertAlmostEqual(sim.context["initial_level"], 12)

    def test_recovery_works_with_cleared_phone_alarm(self):
        sim = Simulation(record(), time_source="next_alarm", next_alarm_sensor="sensor.alarm")
        sim.states["sensor.alarm"] = "unavailable"
        self.assertTrue(sim.run())
        self.assertEqual(sim.calls.count("test.wake_up"), 1)
        self.assertEqual(sim.saved_record()["status"], "completed")
        self.assertEqual(sim.time.timestamp(), FINISH)

    def test_off_light_cancels_recovery_without_turning_lights_on(self):
        sim = Simulation(record())
        sim.states[LIGHTS[0]] = "off"
        self.assertTrue(sim.run())
        self.assertNotIn("light.turn_on", sim.calls)
        self.assertNotIn("test.wake_up", sim.calls)
        self.assertEqual(sim.saved_record()["status"], "cancelled")
        sim.states[LIGHTS[0]] = "on"
        sim.last_triggered = None
        self.assertFalse(sim.eligible())

    def test_unavailable_light_defers_recovery(self):
        sim = Simulation(record())
        sim.states[LIGHTS[0]] = "unavailable"
        self.assertFalse(sim.run())
        self.assertEqual(sim.saved_record()["status"], "running")
        sim.states[LIGHTS[0]] = "on"
        self.assertTrue(sim.eligible())

    def test_expired_recovery_does_not_run_wake_up_actions(self):
        sim = Simulation(record(), time_source="next_alarm", next_alarm_sensor="sensor.alarm")
        sim.time = datetime.fromtimestamp(FINISH, timezone.utc)
        self.assertFalse(sim.run())
        self.assertEqual(sim.calls, [])

    def test_cancelled_and_completed_records_block_even_if_last_triggered_lost(self):
        for status in ("cancelled", "completed"):
            with self.subTest(status=status):
                sim = Simulation(record(status))
                sim.last_triggered = None
                self.assertFalse(sim.run())

    def test_old_outcome_does_not_block_next_day(self):
        sim = Simulation(record("cancelled"))
        sim.time += timedelta(days=1)
        self.assertTrue(sim.eligible())
        self.assertFalse(sim.context["recovery_pending"])

    def test_recovery_honors_weekdays(self):
        self.assertFalse(Simulation(record(), weekdays=["mon"]).eligible())
        self.assertTrue(Simulation(record(), weekdays=["fri"]).eligible())

    def test_malformed_helper_contents_are_safe(self):
        for value in ("not a checkpoint", "[]", "null", "running|bad|bad"):
            with self.subTest(value=value):
                sim = Simulation()
                sim.states[HELPER] = value
                self.assertTrue(sim.eligible())
                self.assertFalse(sim.context["recovery_pending"])

    def test_unavailable_helper_blocks_start(self):
        sim = Simulation()
        sim.states[HELPER] = "unavailable"
        self.assertFalse(sim.run())
        self.assertEqual(sim.calls, [])

    def test_helper_free_mode_does_not_resume(self):
        sim = Simulation(helper=False)
        sim.last_triggered = START + 1
        self.assertFalse(sim.eligible())
        sim.last_triggered = None
        self.assertTrue(sim.run())
        self.assertNotIn("input_text.set_value", sim.calls)

    def test_slow_light_start_succeeds(self):
        sim = Simulation(light_state="off")
        sim.turn_on_delays[LIGHTS[0]] = 5
        self.assertTrue(sim.run())
        self.assertIsNone(sim.reason)
        self.assertEqual(sim.saved_record()["status"], "completed")

    def test_startup_timeout_records_cancellation(self):
        sim = Simulation(light_state="off")
        sim.turn_on_delays[LIGHTS[0]] = 30
        self.assertTrue(sim.run())
        self.assertIn("startup timeout", sim.reason)
        self.assertEqual(sim.saved_record()["status"], "cancelled")
        self.assertNotIn("test.wake_up", sim.calls)

    def test_ramp_cancellation_is_persisted(self):
        sim = Simulation()
        sim.events = [(sim.time + timedelta(seconds=20), LIGHTS[0], "off")]
        self.assertTrue(sim.run())
        self.assertIn("switched off", sim.reason)
        self.assertEqual(sim.saved_record()["status"], "cancelled")
        self.assertNotIn("test.wake_up", sim.calls)

    def test_cancellation_survives_light_reporting_on_again(self):
        sim = Simulation()
        sim.events = [(sim.time + timedelta(seconds=20), LIGHTS[0], "off")]
        # Simulate another state report arriving before the next action executes.
        sim.after_wait = lambda completed: sim.states.update({LIGHTS[0]: "on"})
        self.assertTrue(sim.run())
        self.assertEqual(sim.saved_record()["status"], "cancelled")
        self.assertNotIn("test.wake_up", sim.calls)


if __name__ == "__main__":
    unittest.main()
