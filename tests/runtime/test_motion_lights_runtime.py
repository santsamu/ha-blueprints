"""Exercise motion sessions, native light services, and sticky per-light overrides."""

import asyncio
import inspect
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from homeassistant import bootstrap, loader
from homeassistant.components import light
from homeassistant.components.light import ColorMode
from homeassistant.components.blueprint.models import Blueprint
from homeassistant.const import __version__
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util.yaml import load_yaml

from test_sunrise_runtime import RecordingLight


PATH = "sonoff_motion_lights/sonoff_motion_lights.yaml"
MOTION = "binary_sensor.motion_test"
DAYLIGHT = "binary_sensor.daylight_test"
AUTOMATION = "automation.motion_runtime"
SUPPORTED = tuple(int(part) for part in __version__.split(".")[:2]) >= (2025, 4)


class MotionLight(RecordingLight):
    def __init__(self, name, modes):
        super().__init__(name, modes)
        self.off_calls = 0
        self.fail = False
        self.ignore = False
        self.command_delay = 0

    async def async_turn_on(self, **kwargs):
        if self.fail:
            raise HomeAssistantError("Simulated light service failure")
        if self.ignore:
            self.calls.append(dict(kwargs))
            return
        if self.command_delay:
            await asyncio.sleep(self.command_delay)
        await super().async_turn_on(**kwargs)

    async def async_turn_off(self, **kwargs):
        self.off_calls += 1
        await super().async_turn_off(**kwargs)


class MotionLightsVersionTests(unittest.TestCase):
    def test_blueprint_requires_new_script_variable_scoping(self):
        data = load_yaml(str(Path(__file__).resolve().parents[2] / PATH))
        # Recent HA releases require the caller to supply a domain schema.
        # This test concerns the native min-version validator; the runtime
        # harness separately exercises the actual automation schema/importer.
        kwargs = {"schema": lambda value: value} if "schema" in inspect.signature(Blueprint).parameters else {}
        blueprint = Blueprint(data, **kwargs)
        for unsupported in ("2024.10.0", "2025.3.0"):
            with patch("homeassistant.components.blueprint.models.__version__", unsupported):
                self.assertEqual(blueprint.validate(), ["Requires at least Home Assistant 2025.4.0"])
        with patch("homeassistant.components.blueprint.models.__version__", "2025.4.0"):
            self.assertIsNone(blueprint.validate())


@unittest.skipUnless(SUPPORTED, "Motion Lights requires HA 2025.4 variable scoping")
class MotionLightsRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        asyncio.get_running_loop().slow_callback_duration = 1
        self.temp = TemporaryDirectory(prefix="ha-motion-runtime-")
        self.addCleanup(self.temp.cleanup)
        destination = Path(self.temp.name) / "blueprints/automation" / PATH
        destination.parent.mkdir(parents=True)
        shutil.copyfile(Path(__file__).resolve().parents[2] / PATH, destination)
        self.hass = HomeAssistant(self.temp.name)
        self.hass.config.skip_pip = True
        loader.async_setup(self.hass)

    async def asyncTearDown(self):
        async with asyncio.timeout(10):
            await self.hass.async_stop(force=True)

    async def wait_until(self, predicate, timeout=5):
        async with asyncio.timeout(timeout):
            while not predicate():
                await asyncio.sleep(0.005)

    async def load(self, lamps, *, activate=True, sun="above_horizon", daylight="on", **inputs):
        self.lamps = lamps
        config = {"homeassistant": {
            "latitude": 47.0, "longitude": 8.0, "elevation": 400,
            "time_zone": "UTC", "unit_system": "metric", "currency": "CHF",
        }, "light": [], "automation": [{
            "id": "motion_runtime", "alias": "Motion runtime",
            "use_blueprint": {"path": PATH, "input": {
                "motion_sensor": MOTION, "lights": [lamp.entity_id for lamp in lamps],
                "duration": {"seconds": 1.2}, "timer_mode": "fixed", **inputs,
            }},
        }]}
        # Native automation.reload reads this file rather than bootstrap's dict.
        (Path(self.temp.name) / "configuration.yaml").write_text(json.dumps(config), encoding="utf-8")
        self.assertIs(await bootstrap.async_from_config_dict(config, self.hass), self.hass)
        await self.hass.data[light.DATA_COMPONENT].async_add_entities(lamps)
        self.hass.states.async_set(MOTION, "off", {"device_class": "motion"})
        self.hass.states.async_set("sun.sun", sun)
        self.hass.states.async_set(DAYLIGHT, daylight)
        await self.hass.async_start()
        self.assertIsNotNone(self.hass.states.get(AUTOMATION), "Blueprint import failed")
        if activate:
            expected = [lamp for lamp in lamps if not lamp.fail
                        and (not lamp.is_on or not inputs.get("only_if_off", True))]
            blocked = (inputs.get("day_style") == "color" and inputs.get("day_color") == [0, 0, 0]
                       or inputs.get("daylight_mode") == "binary" and not inputs.get("daylight_sensor"))
            await self.motion("on")
            if expected and not blocked:
                await self.wait_until(lambda: all(lamp.calls for lamp in expected))
                await asyncio.sleep(0.02)

    async def motion(self, value):
        self.hass.states.async_set(MOTION, value, {"device_class": "motion"})
        # block_till_done waits for timer tasks on some HA releases and can
        # consume this short session before the test can send an override.
        await asyncio.sleep(0.03)

    async def finish(self):
        await self.wait_until(lambda: self.hass.states.get(AUTOMATION).attributes["current"] == 0)

    async def change(self, lamp, **attributes):
        # Go through the entity to simulate a physical device report.
        for key, value in attributes.items():
            setattr(lamp, "_attr_" + key, value)
        lamp.async_write_ha_state()
        await asyncio.sleep(0.02)

    async def test_fixed_duration_controls_multiple_lights_and_clamps_temperature(self):
        white = MotionLight("motion_white", [ColorMode.COLOR_TEMP])
        dimmer = MotionLight("motion_dimmer", [ColorMode.BRIGHTNESS])
        switch = MotionLight("motion_switch", [ColorMode.ONOFF])
        await self.load([white, dimmer, switch], day_temperature=1500)
        await self.finish()
        self.assertEqual(white.calls[0]["color_temp_kelvin"], 2700)
        self.assertEqual(dimmer.calls[0]["brightness"], 204)
        self.assertNotIn("brightness", switch.calls[0])
        self.assertEqual([lamp.off_calls for lamp in self.lamps], [1, 1, 1])

    async def test_existing_light_is_skipped_independently(self):
        existing = MotionLight("motion_existing", [ColorMode.BRIGHTNESS])
        existing._attr_is_on = True
        fresh = MotionLight("motion_fresh", [ColorMode.BRIGHTNESS])
        await self.load([existing, fresh])
        await self.finish()
        self.assertEqual(existing.calls, [])
        self.assertEqual(existing.off_calls, 0)
        self.assertEqual(fresh.off_calls, 1)

    async def test_off_only_disabled_adopts_existing_light(self):
        lamp = MotionLight("motion_adopt", [ColorMode.BRIGHTNESS])
        lamp._attr_is_on = True
        await self.load([lamp], only_if_off=False)
        await self.finish()
        self.assertEqual(lamp.off_calls, 1)

    async def test_brightness_override_is_sticky_when_reverted_and_motion_repeats(self):
        changed = MotionLight("motion_override", [ColorMode.BRIGHTNESS])
        normal = MotionLight("motion_normal", [ColorMode.BRIGHTNESS])
        await self.load([changed, normal], only_if_off=False)
        await self.change(changed, brightness=100)
        await self.change(changed, brightness=204)
        await self.motion("off")
        await self.motion("on")
        await self.finish()
        self.assertEqual(changed.off_calls, 0)
        self.assertEqual(normal.off_calls, 1)
        self.assertEqual(len(changed.calls), 1)

    async def test_all_released_lights_keep_session_lock_until_deadline(self):
        lamp = MotionLight("motion_all_released", [ColorMode.BRIGHTNESS])
        await self.load([lamp], only_if_off=False)
        await self.change(lamp, brightness=100)
        self.assertEqual(self.hass.states.get(AUTOMATION).attributes["current"], 1)
        await self.motion("off")
        await self.motion("on")
        await self.finish()
        self.assertEqual(len(lamp.calls), 1)
        self.assertEqual(lamp.off_calls, 0)

    async def test_temperature_override_preserves_only_changed_light(self):
        changed = MotionLight("motion_temperature", [ColorMode.COLOR_TEMP])
        normal = MotionLight("motion_temperature_normal", [ColorMode.COLOR_TEMP])
        await self.load([changed, normal])
        await self.change(changed, color_temp_kelvin=5000)
        await self.finish()
        self.assertEqual([changed.off_calls, normal.off_calls], [0, 1])

    async def test_color_override_is_preserved(self):
        lamp = MotionLight("motion_rgb", [ColorMode.RGB])
        await self.load([lamp], day_style="color", day_color=[128, 0, 0])
        self.assertEqual(lamp.calls[0]["rgb_color"], (255, 0, 0))
        await self.change(lamp, rgb_color=(0, 0, 255))
        await self.finish()
        self.assertEqual(lamp.off_calls, 0)

    async def test_color_mode_change_is_preserved(self):
        lamp = MotionLight("motion_mode", [ColorMode.RGB, ColorMode.COLOR_TEMP])
        await self.load([lamp])
        await self.change(lamp, color_mode=ColorMode.RGB, rgb_color=(255, 0, 0))
        await self.finish()
        self.assertEqual(lamp.off_calls, 0)

    async def test_unrelated_report_and_small_rounding_do_not_release_light(self):
        lamp = MotionLight("motion_rounding", [ColorMode.COLOR_TEMP])
        await self.load([lamp])
        await self.change(lamp, brightness=203, color_temp_kelvin=4010,
                          extra_state_attributes={"linkquality": 80})
        await self.finish()
        self.assertEqual(lamp.off_calls, 1)

    async def test_motion_clear_countdown_is_reset_without_reapplying_profile(self):
        lamp = MotionLight("motion_reset", [ColorMode.BRIGHTNESS])
        await self.load([lamp], timer_mode="motion_clear")
        await asyncio.sleep(1.3)
        self.assertEqual(lamp.off_calls, 0, "Motion still active")
        await self.motion("off")
        await asyncio.sleep(0.7)
        await self.motion("on")
        await asyncio.sleep(0.6)
        self.assertEqual(lamp.off_calls, 0, "New motion cancelled the countdown")
        await self.motion("off")
        await self.finish()
        self.assertEqual(lamp.off_calls, 1)
        self.assertEqual(len(lamp.calls), 1)

    async def test_sun_selects_night_profile_once_per_session(self):
        lamp = MotionLight("motion_night", [ColorMode.COLOR_TEMP])
        await self.load([lamp], sun="below_horizon", daylight_mode="sun")
        self.assertEqual(lamp.calls[0]["brightness"], 51)
        self.assertEqual(lamp.calls[0]["color_temp_kelvin"], 2700)
        self.hass.states.async_set("sun.sun", "above_horizon")
        await self.finish()
        self.assertEqual(len(lamp.calls), 1)
        self.assertEqual(lamp.off_calls, 1)

    async def test_binary_daylight_selects_day_profile(self):
        lamp = MotionLight("motion_daylight", [ColorMode.COLOR_TEMP])
        await self.load([lamp], daylight_mode="binary", daylight_sensor=DAYLIGHT)
        self.assertEqual(lamp.calls[0]["brightness"], 204)
        await self.finish()

    async def test_missing_daylight_source_blocks_activation(self):
        lamp = MotionLight("motion_invalid_daylight", [ColorMode.BRIGHTNESS])
        await self.load([lamp], daylight_mode="binary")
        self.assertEqual(lamp.calls, [])
        await self.finish()

    async def test_manual_off_then_on_is_not_switched_off(self):
        lamp = MotionLight("motion_manual_power", [ColorMode.BRIGHTNESS])
        await self.load([lamp])
        await self.change(lamp, is_on=False)
        await self.change(lamp, is_on=True)
        await self.finish()
        self.assertEqual(lamp.off_calls, 0)

    async def test_light_unavailable_then_recovered_remains_released(self):
        lamp = MotionLight("motion_unavailable", [ColorMode.BRIGHTNESS])
        await self.load([lamp])
        await self.change(lamp, available=False)
        await self.change(lamp, available=True)
        await self.finish()
        self.assertEqual(lamp.off_calls, 0)

    async def test_sensor_unavailable_cancels_session_without_shutoff(self):
        lamp = MotionLight("motion_sensor_failure", [ColorMode.BRIGHTNESS])
        await self.load([lamp])
        await self.motion("unavailable")
        await self.finish()
        self.assertEqual(lamp.off_calls, 0)

    async def test_color_falls_back_to_temperature_and_brightness(self):
        white = MotionLight("motion_color_fallback", [ColorMode.COLOR_TEMP])
        dimmer = MotionLight("motion_brightness_fallback", [ColorMode.BRIGHTNESS])
        await self.load([white, dimmer], day_style="color")
        self.assertIn("color_temp_kelvin", white.calls[0])
        self.assertNotIn("rgb_color", dimmer.calls[0])
        await self.finish()
        self.assertEqual([white.off_calls, dimmer.off_calls], [1, 1])

    async def test_keep_mode_does_not_send_color_parameters(self):
        lamp = MotionLight("motion_keep", [ColorMode.COLOR_TEMP])
        await self.load([lamp], day_style="keep")
        self.assertNotIn("color_temp_kelvin", lamp.calls[0])
        self.assertNotIn("rgb_color", lamp.calls[0])
        await self.finish()
        self.assertEqual(lamp.off_calls, 1)

    async def test_failed_light_does_not_prevent_healthy_light_activation(self):
        broken = MotionLight("motion_broken", [ColorMode.BRIGHTNESS])
        broken.fail = True
        normal = MotionLight("motion_after_broken", [ColorMode.BRIGHTNESS])
        await self.load([broken, normal], duration={"seconds": 2.5})
        await self.wait_until(lambda: bool(normal.calls))
        await self.finish()
        self.assertEqual(broken.off_calls, 0)
        self.assertEqual(normal.off_calls, 1)

    async def test_changes_during_another_light_startup_are_preserved(self):
        first = MotionLight("motion_first_startup", [ColorMode.BRIGHTNESS])
        slow = MotionLight("motion_slow_startup", [ColorMode.BRIGHTNESS])
        slow.command_delay = 0.15
        await self.load([first, slow], activate=False, duration={"seconds": 0.5})
        self.hass.states.async_set(MOTION, "on")
        await self.wait_until(lambda: bool(first.calls))
        await self.change(first, brightness=100)
        await self.change(first, brightness=204)
        await self.wait_until(lambda: bool(slow.calls))
        await self.finish()
        self.assertEqual([first.off_calls, slow.off_calls], [0, 1])

    async def test_reload_cancels_active_session_without_switching_off(self):
        lamp = MotionLight("motion_reload", [ColorMode.BRIGHTNESS])
        await self.load([lamp], timer_mode="motion_clear")
        async with asyncio.timeout(5):
            await self.hass.services.async_call("automation", "reload", blocking=True)
        await self.wait_until(lambda: self.hass.states.get(AUTOMATION).attributes["current"] == 0)
        self.assertEqual(lamp.off_calls, 0)

    async def test_black_color_blocks_commands(self):
        lamp = MotionLight("motion_black", [ColorMode.RGB])
        await self.load([lamp], day_style="color", day_color=[0, 0, 0])
        await self.finish()
        self.assertEqual(lamp.calls, [])

    async def test_unconfirmed_light_is_not_adopted(self):
        lamp = MotionLight("motion_unconfirmed", [ColorMode.BRIGHTNESS])
        lamp.ignore = True
        await self.load([lamp], duration={"seconds": 2.5})
        await self.finish()
        self.assertEqual(len(lamp.calls), 1)
        self.assertEqual(lamp.off_calls, 0)

    async def test_native_color_conversion_for_all_color_modes(self):
        modes = (ColorMode.RGB, ColorMode.RGBW, ColorMode.RGBWW, ColorMode.HS, ColorMode.XY)
        lamps = [MotionLight("motion_native_" + mode.value, [mode]) for mode in modes]
        await self.load(lamps, day_style="color", day_color=[128, 0, 0], duration={"seconds": 1})
        await self.wait_until(lambda: all(lamp.calls for lamp in lamps))
        for lamp, field in zip(lamps, ("rgb_color", "rgbw_color", "rgbww_color", "hs_color", "xy_color")):
            self.assertIn(field, lamp.calls[0])
        await self.finish()
        self.assertEqual([lamp.off_calls for lamp in lamps], [1] * len(lamps))

    async def test_new_session_after_completion_controls_lights_again(self):
        lamp = MotionLight("motion_new_session", [ColorMode.BRIGHTNESS])
        await self.load([lamp])
        await self.finish()
        await self.motion("off")
        await self.motion("on")
        await self.finish()
        self.assertEqual(lamp.off_calls, 2)
        self.assertEqual(len(lamp.calls), 2)

    async def test_automation_disable_cancels_session_without_shutoff(self):
        lamp = MotionLight("motion_disabled", [ColorMode.BRIGHTNESS])
        await self.load([lamp], timer_mode="motion_clear")
        await self.hass.services.async_call("automation", "turn_off",
                                            {"entity_id": AUTOMATION}, blocking=True)
        self.assertEqual(lamp.off_calls, 0)
        self.assertEqual(self.hass.states.get(AUTOMATION).state, "off")


if __name__ == "__main__":
    unittest.main()
