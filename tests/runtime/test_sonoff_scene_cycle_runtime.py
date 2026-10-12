"""Cycle native scenes through real ZHA events, a Number helper, and the queue."""

import asyncio
import logging
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from homeassistant import bootstrap, loader
from homeassistant.components import light
from homeassistant.components.light import ColorMode
from homeassistant.components.trace import DATA_TRACE
from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from test_sonoff_runtime import CaptureLogs
from test_sunrise_runtime import RecordingLight


BLUEPRINT_PATH = "sonoff_zigbee_scene_cycle/sonoff_zigbee_scene_cycle.yaml"
BUTTON = "scene-cycle-button"
AUTOMATION = "automation.scene_cycle"
HELPER = "input_number.cycle_position"
SCENES = ["scene.cycle_one", "scene.cycle_two", "scene.cycle_three"]
GESTURE_EVENT = "scene_cycle_gesture"


class GateLight(RecordingLight):
    def __init__(self):
        super().__init__("cycle_lamp", [ColorMode.BRIGHTNESS])
        self.block_next = False
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def async_turn_on(self, **kwargs):
        if self.block_next:
            self.block_next = False
            self.entered.set()
            await self.release.wait()
        await super().async_turn_on(**kwargs)


class SonoffSceneCycleRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TemporaryDirectory(prefix="ha-scene-cycle-")
        self.addCleanup(self.temp.cleanup)
        destination = Path(self.temp.name) / "blueprints/automation" / BLUEPRINT_PATH
        destination.parent.mkdir(parents=True)
        shutil.copyfile(Path(__file__).resolve().parents[2] / BLUEPRINT_PATH, destination)
        self.gestures = []
        self.logs = CaptureLogs()
        logger = logging.getLogger("homeassistant.components.automation")
        logger.addHandler(self.logs)
        self.addCleanup(logger.removeHandler, self.logs)
        self.new_hass()

    def new_hass(self):
        self.hass = HomeAssistant(self.temp.name)
        self.hass.config.skip_pip = True
        loader.async_setup(self.hass)

        @callback
        def record(event):
            self.gestures.append(event.data["gesture"])

        self.hass.bus.async_listen(GESTURE_EVENT, record)

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)

    async def load(self, *, maximum=3, position=0, scenes=None, press=None, hold=None):
        self.lamp = GateLight()
        inputs = {"button_id": BUTTON, "state_helper": HELPER,
                  "scenes": SCENES if scenes is None else scenes,
                  "press_action": press or [], "hold_action": hold or []}
        config = {"homeassistant": {
            "latitude": 47.0, "longitude": 8.0, "elevation": 400,
            "time_zone": "UTC", "unit_system": "metric", "currency": "CHF",
        }, "light": [], "input_number": {"cycle_position": {
            "min": 0, "max": maximum, "step": 1,
        }}, "scene": [{
            "name": name, "entities": {self.lamp.entity_id: {"state": "on", "brightness": level}},
        } for name, level in zip(("Cycle One", "Cycle Two", "Cycle Three"), (40, 80, 120))],
            "automation": [{"id": "scene_cycle", "alias": "Scene cycle",
                            "use_blueprint": {"path": BLUEPRINT_PATH, "input": inputs}}]}
        self.assertIs(await bootstrap.async_from_config_dict(config, self.hass), self.hass)
        await self.hass.data[light.DATA_COMPONENT].async_add_entities([self.lamp])
        if position is not None:
            await self.set_position(position)
        await self.hass.async_start()
        await self.settle()
        self.assertEqual(self.hass.states.get(AUTOMATION).attributes["mode"], "queued")

    async def settle(self):
        async with asyncio.timeout(5):
            await self.hass.async_block_till_done()

    async def wait_until(self, predicate):
        async with asyncio.timeout(5):
            while not predicate():
                await asyncio.sleep(0.005)

    def trace_for(self, context):
        bucket = self.hass.data[DATA_TRACE].get(AUTOMATION, {})
        runs = getattr(bucket, "runs", bucket)
        return next((trace for trace in runs.values() if trace.context.parent_id == context.id), None)

    def current(self):
        return self.hass.states.get(AUTOMATION).attributes["current"]

    def position(self):
        return int(float(self.hass.states.get(HELPER).state))

    async def set_position(self, value):
        await self.hass.services.async_call("input_number", "set_value",
                                            {"entity_id": HELPER, "value": value}, blocking=True)

    async def fire(self, command="on", *, device=BUTTON, current=None):
        context = Context()
        self.hass.bus.async_fire("zha_event", {"device_id": device, "command": command}, context=context)
        if device != BUTTON or command not in ("toggle", "on", "off"):
            await self.settle()
            return
        await self.wait_until(lambda: self.trace_for(context) is not None)
        if current is None:
            await self.wait_until(lambda: self.trace_for(context).as_short_dict()["state"] == "stopped")
        else:
            await self.wait_until(lambda: self.current() == current)

    @staticmethod
    def gesture_action(name):
        return [{"event": GESTURE_EVENT, "event_data": {"gesture": name}}]

    async def test_native_scenes_follow_configured_order_and_wrap_at_three(self):
        await self.load(scenes=[SCENES[2], SCENES[0], SCENES[1]])
        for index in (1, 2, 3, 1):
            await self.fire()
            self.assertEqual(self.position(), index)
        self.assertEqual([call["brightness"] for call in self.lamp.calls], [120, 40, 80, 120])

    async def test_helper_maximum_four_still_wraps_and_repairs_position_four(self):
        await self.load(maximum=4, position=3)
        await self.fire()
        self.assertEqual(self.position(), 1)
        first_activation = self.hass.states.get(SCENES[0]).state
        await self.set_position(4)
        await self.fire()
        self.assertEqual(self.position(), 1)
        self.assertNotEqual(self.hass.states.get(SCENES[0]).state, first_activation)
        # Scene reactivation can skip a light already at the requested settings.
        self.assertEqual(self.hass.states.get(self.lamp.entity_id).attributes["brightness"], 40)

    async def test_press_hold_and_other_devices_do_not_advance_cycle(self):
        await self.load(position=2, press=self.gesture_action("press"), hold=self.gesture_action("hold"))
        await self.fire("toggle")
        await self.fire("off")
        await self.fire(device="other-button")
        await self.fire("unknown")
        self.assertEqual(self.position(), 2)
        self.assertEqual(self.gestures, ["press", "hold"])
        self.assertEqual(self.lamp.calls, [])

    async def test_rapid_queued_double_presses_read_position_when_they_execute(self):
        await self.load()
        self.lamp.block_next = True
        await self.fire(current=1)
        await self.wait_until(self.lamp.entered.is_set)
        for current in (2, 3, 4):
            await self.fire(current=current)
        self.assertEqual(self.position(), 0)
        self.lamp.release.set()
        await self.wait_until(lambda: self.current() == 0 and len(self.lamp.calls) == 4)
        self.assertEqual([call["brightness"] for call in self.lamp.calls], [40, 80, 120, 40])
        self.assertEqual(self.position(), 1)

    async def test_empty_gestures_do_not_occupy_queue_during_scene_activation(self):
        await self.load()
        self.lamp.block_next = True
        await self.fire(current=1)
        await self.wait_until(self.lamp.entered.is_set)
        await self.fire("toggle")
        await self.fire("off")
        self.assertEqual(self.current(), 1)
        self.lamp.release.set()
        await self.wait_until(lambda: self.current() == 0)
        self.assertEqual(self.position(), 1)
        self.assertEqual(len(self.lamp.calls), 1)

    async def test_queue_overflow_logs_warning_and_does_not_advance_extra_scene(self):
        await self.load()
        self.lamp.block_next = True
        await self.fire(current=1)
        await self.wait_until(self.lamp.entered.is_set)
        for current in range(2, 11):
            await self.fire(current=current)
        await self.fire()
        self.assertEqual(self.current(), 10)
        self.assertEqual(sum("Maximum number of runs exceeded" in record.getMessage()
                             for record in self.logs.records), 1)
        self.lamp.release.set()
        await self.wait_until(lambda: self.current() == 0 and len(self.lamp.calls) == 10)
        self.assertEqual(self.position(), 1)

    async def test_missing_scene_and_unavailable_helper_leave_position_unchanged(self):
        await self.load(position=1)
        self.hass.states.async_remove(SCENES[1])
        await self.fire()
        self.assertEqual(self.position(), 1)
        self.assertEqual(self.lamp.calls, [])
        state = self.hass.states.get(HELPER)
        self.hass.states.async_set(HELPER, "unavailable", state.attributes)
        await self.fire()
        self.assertEqual(self.hass.states.get(HELPER).state, "unavailable")
        self.assertEqual(self.lamp.calls, [])

    async def test_failed_scene_service_does_not_write_position(self):
        await self.load(position=1)

        async def fail_scene(call):
            raise HomeAssistantError("Simulated scene activation failure")

        self.hass.services.async_register("scene", "turn_on", fail_scene)
        await self.fire()
        self.assertEqual(self.position(), 1)
        self.assertEqual(self.lamp.calls, [])

    async def test_position_is_restored_after_home_assistant_restart(self):
        await self.load()
        await self.fire()
        await self.fire()
        self.assertEqual(self.position(), 2)
        await self.hass.async_stop(force=True)
        self.new_hass()
        await self.load(position=None)
        self.assertEqual(self.position(), 2)
        await self.fire()
        self.assertEqual(self.position(), 3)
        self.assertEqual(self.lamp.calls[0]["brightness"], 120)

    async def test_too_small_helper_maximum_blocks_cycle_but_not_press_actions(self):
        await self.load(maximum=2, press=self.gesture_action("press"))
        await self.fire()
        self.assertEqual(self.position(), 0)
        self.assertEqual(self.lamp.calls, [])
        await self.fire("toggle")
        self.assertEqual(self.gestures, ["press"])


if __name__ == "__main__":
    unittest.main()
