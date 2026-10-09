"""Exercise the imported blueprint with Home Assistant's real event/script engine."""

import asyncio
import logging
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from homeassistant import bootstrap, loader
from homeassistant.components.trace import DATA_TRACE
from homeassistant.core import Context, HomeAssistant, callback


BLUEPRINT = Path(__file__).resolve().parents[2] / "sonoff_zigbee_button/sonoff_zigbee_button.yaml"
BLUEPRINT_PATH = "sonoff_zigbee_button/sonoff_zigbee_button.yaml"
BUTTON_ID = "sonoff-runtime-button"
AUTOMATION = "automation.sonoff_runtime"
STARTED = "sonoff_runtime_started"
FINISHED = "sonoff_runtime_finished"
COMMANDS = {"press": "toggle", "double_press": "on", "hold": "off"}


class CaptureLogs(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.records = []

    def emit(self, record):
        self.records.append(record)


class SonoffRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TemporaryDirectory(prefix="ha-sonoff-runtime-")
        self.addCleanup(self.temp.cleanup)
        config_dir = Path(self.temp.name)
        destination = config_dir / "blueprints/automation" / BLUEPRINT_PATH
        destination.parent.mkdir(parents=True)
        shutil.copyfile(BLUEPRINT, destination)
        self.hass = HomeAssistant(str(config_dir))
        self.hass.config.skip_pip = True
        loader.async_setup(self.hass)
        self.events = []
        self.logs = CaptureLogs()
        logger = logging.getLogger("homeassistant.components.automation")
        logger.addHandler(self.logs)
        self.addCleanup(logger.removeHandler, self.logs)

        @callback
        def record(event):
            self.events.append((event.event_type, event.data["gesture"]))

        self.hass.bus.async_listen(STARTED, record)
        self.hass.bus.async_listen(FINISHED, record)

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)

    def sequence(self, gesture, *, wait=False):
        actions = [{"event": STARTED, "event_data": {"gesture": gesture}}]
        if wait:
            actions.append({
                "wait_for_trigger": [{"trigger": "event", "event_type": self.release_event(gesture)}],
                "timeout": {"seconds": 30},
                "continue_on_timeout": False,
            })
        actions.append({"event": FINISHED, "event_data": {"gesture": gesture}})
        return actions

    @staticmethod
    def release_event(gesture):
        return "sonoff_runtime_release_" + gesture

    async def load(self, *, mode=None, log_level=None, **actions):
        inputs = {"button_id": BUTTON_ID}
        if mode is not None:
            inputs["mode"] = mode
        if log_level is not None:
            inputs["ignored_press_log_level"] = log_level
        inputs.update({name + "_action": sequence for name, sequence in actions.items()})
        config = {"homeassistant": {
            "latitude": 47.0, "longitude": 8.0, "elevation": 400,
            "time_zone": "UTC", "unit_system": "metric", "currency": "CHF",
        }, "automation": [{
            "id": "sonoff_runtime", "alias": "Sonoff runtime",
            "use_blueprint": {"path": BLUEPRINT_PATH, "input": inputs},
        }]}
        self.assertIs(await bootstrap.async_from_config_dict(config, self.hass), self.hass)
        await self.hass.async_start()
        await self.settle()
        state = self.hass.states.get(AUTOMATION)
        self.assertIsNotNone(state, "The actual blueprint must import successfully")
        self.assertEqual(state.state, "on")
        self.assertEqual(state.attributes["mode"], mode or "single")

    async def settle(self):
        async with asyncio.timeout(5):
            await self.hass.async_block_till_done()

    async def wait_until(self, predicate):
        async with asyncio.timeout(5):
            while not predicate():
                await asyncio.sleep(0.005)

    def trace_for(self, context):
        bucket = self.hass.data[DATA_TRACE].get(AUTOMATION, {})
        # Newer releases keep executed and not-triggered traces in separate buckets.
        runs = getattr(bucket, "runs", bucket)
        return next((trace for trace in runs.values()
                     if trace.context.parent_id == context.id), None)

    def waiting(self, gesture):
        return self.hass.bus.async_listeners().get(self.release_event(gesture), 0)

    async def fire(self, gesture, *, device_id=BUTTON_ID, current=None,
                   started=None, waiting=None):
        context = Context()
        self.hass.bus.async_fire("zha_event", {"device_id": device_id, "command": COMMANDS[gesture]},
                                 context=context)
        if device_id != BUTTON_ID:
            await self.settle()
            return
        await self.wait_until(lambda: self.trace_for(context) is not None)
        if current is None:
            # Rejected or short actions must actually finish before negative assertions.
            await self.wait_until(lambda: self.trace_for(context).as_short_dict()["state"] == "stopped")
        else:
            await self.wait_until(lambda: self.current() == current
                                 and (started is None or sum(event == STARTED for event, _ in self.events) == started)
                                 and (waiting is None or self.waiting(waiting) > 0))

    async def release(self, gesture, *, current=0, finished, waiting=None):
        self.assertGreater(self.waiting(gesture), 0,
                           "The native wait must have subscribed before it is released")
        self.hass.bus.async_fire(self.release_event(gesture))
        await self.wait_until(lambda: self.current() == current
                             and sum(event == FINISHED for event, _ in self.events) == finished
                             and (waiting is None or self.waiting(waiting) > 0))
        if current == 0:
            await self.settle()

    def current(self):
        return self.hass.states.get(AUTOMATION).attributes["current"]

    def warnings(self):
        return [record.getMessage() for record in self.logs.records]

    async def test_import_and_all_gestures_route_to_their_actions(self):
        await self.load(**{gesture: self.sequence(gesture) for gesture in COMMANDS})
        for gesture in COMMANDS:
            await self.fire(gesture)
        self.assertEqual(self.events, [(event, gesture) for gesture in COMMANDS
                                      for event in (STARTED, FINISHED)])

    async def test_events_from_other_devices_and_unknown_commands_are_ignored(self):
        await self.load(press=self.sequence("press"))
        await self.fire("press", device_id="another-button")
        self.hass.bus.async_fire("zha_event", {"device_id": BUTTON_ID, "command": "unknown"})
        self.hass.bus.async_fire("zha_event", {"device_id": BUTTON_ID})
        await self.settle()
        self.assertEqual(self.events, [])
        self.assertEqual(self.current(), 0)

    async def test_empty_gestures_do_not_cancel_a_running_restart_sequence(self):
        await self.load(mode="restart", press=self.sequence("press", wait=True))
        await self.fire("press", current=1, started=1, waiting="press")
        await self.fire("double_press")
        await self.fire("hold")
        self.assertEqual(self.current(), 1)
        self.assertEqual(self.events, [(STARTED, "press")])
        await self.release("press", finished=1)
        self.assertEqual(self.events, [(STARTED, "press"), (FINISHED, "press")])

    async def test_configured_gesture_restarts_and_cancels_the_previous_wait(self):
        await self.load(mode="restart", press=self.sequence("press", wait=True),
                        hold=self.sequence("hold", wait=True))
        await self.fire("press", current=1, started=1, waiting="press")
        await self.fire("hold", current=1, started=2, waiting="hold")
        self.assertEqual(self.current(), 1)
        self.assertEqual(self.hass.bus.async_listeners().get(self.release_event("press"), 0), 0)
        await self.release("hold", finished=1)
        self.assertEqual(self.events, [(STARTED, "press"), (STARTED, "hold"), (FINISHED, "hold")])

    async def test_single_mode_ignores_overlap_without_warning_by_default(self):
        await self.load(press=self.sequence("press", wait=True), hold=self.sequence("hold"))
        await self.fire("press", current=1, started=1, waiting="press")
        await self.fire("hold")
        self.assertEqual(self.events, [(STARTED, "press")])
        self.assertFalse(any("Already running" in message for message in self.warnings()))
        await self.release("press", finished=1)

    async def test_single_mode_warning_identifies_an_ignored_configured_gesture(self):
        await self.load(log_level="warning", press=self.sequence("press", wait=True),
                        hold=self.sequence("hold"))
        await self.fire("press", current=1, started=1, waiting="press")
        await self.fire("hold")
        self.assertTrue(any("Already running" in message for message in self.warnings()))
        self.assertEqual(self.events, [(STARTED, "press")])
        await self.release("press", finished=1)

    async def test_queued_mode_preserves_gesture_order(self):
        await self.load(mode="queued", press=self.sequence("press", wait=True),
                        double_press=self.sequence("double_press"), hold=self.sequence("hold"))
        await self.fire("press", current=1, started=1, waiting="press")
        await self.fire("double_press", current=2)
        await self.fire("hold", current=3)
        self.assertEqual(self.current(), 3)
        self.assertEqual(self.events, [(STARTED, "press")])
        await self.release("press", finished=3)
        self.assertEqual(self.events, [(event, gesture) for gesture in COMMANDS
                                      for event in (STARTED, FINISHED)])

    async def test_parallel_mode_runs_gestures_concurrently(self):
        await self.load(mode="parallel", press=self.sequence("press", wait=True),
                        double_press=self.sequence("double_press", wait=True))
        await self.fire("press", current=1, started=1, waiting="press")
        await self.fire("double_press", current=2, started=2, waiting="double_press")
        self.assertEqual(self.current(), 2)
        await self.release("press", current=1, finished=1, waiting="double_press")
        self.assertEqual(self.current(), 1)
        await self.release("double_press", finished=2)
        self.assertEqual(self.events, [(STARTED, "press"), (STARTED, "double_press"),
                                      (FINISHED, "press"), (FINISHED, "double_press")])

    async def test_queued_limit_includes_active_run_and_reports_overflow(self):
        await self.load(mode="queued", log_level="warning", press=self.sequence("press", wait=True))
        for index in range(10):
            await self.fire("press", current=index + 1, started=1, waiting="press")
        # Wait for the rejected overflow trace to finish as well.
        await self.fire("press")
        self.assertEqual(self.current(), 10)
        self.assertEqual(self.events, [(STARTED, "press")])
        self.assertEqual(sum("Maximum number of runs exceeded" in message for message in self.warnings()), 1)
        for index in range(10):
            await self.release("press", current=9 - index, finished=index + 1,
                               waiting="press" if index < 9 else None)
        self.assertEqual(self.events.count((FINISHED, "press")), 10)
        self.assertEqual(self.current(), 0)

    async def test_parallel_limit_reports_overflow_and_releases_all_runs(self):
        await self.load(mode="parallel", log_level="warning", press=self.sequence("press", wait=True))
        for index in range(10):
            await self.fire("press", current=index + 1, started=index + 1, waiting="press")
        await self.fire("press")
        self.assertEqual(self.current(), 10)
        self.assertEqual(self.events.count((STARTED, "press")), 10)
        self.assertEqual(sum("Maximum number of runs exceeded" in message for message in self.warnings()), 1)
        await self.release("press", finished=10)
        self.assertEqual(self.events.count((FINISHED, "press")), 10)
        self.assertEqual(self.current(), 0)

    async def test_empty_actions_do_not_start_runs_or_produce_busy_warnings(self):
        await self.load(mode="restart", log_level="warning")
        for gesture in COMMANDS:
            await self.fire(gesture)
        self.assertEqual(self.current(), 0)
        self.assertEqual(self.events, [])
        self.assertEqual(self.warnings(), [])


if __name__ == "__main__":
    unittest.main()
