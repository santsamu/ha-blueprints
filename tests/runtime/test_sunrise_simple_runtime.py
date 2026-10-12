"""Import the helper-only blueprint and exercise native toggle cancellation."""

from datetime import datetime, timedelta, timezone
import unittest

from homeassistant.components.light import ColorMode

from test_sunrise_runtime import AUTOMATION, COLOR_INPUTS, RecordingLight, SunriseRuntimeHarness


ENABLED = "input_boolean.sunrise_runtime_enabled"
RECOVERY = "input_text.sunrise_runtime_recovery"


class SunriseSimpleRuntimeTests(SunriseRuntimeHarness):
    blueprint_path = "sunrise_wake_up_simple/sunrise_wake_up_simple.yaml"
    source_inputs = {"wake_up_time_helper": "input_datetime.sunrise_runtime_wake_up",
                     "enabled_helper": ENABLED}

    async def test_enabled_time_helper_starts_white_sunrise(self):
        lamp = RecordingLight("simple_white", [ColorMode.COLOR_TEMP])
        await self.load([lamp])
        self.assertEqual(lamp.calls[0]["brightness"], 51)
        self.assertIn("color_temp_kelvin", lamp.calls[0])
        self.assertNotIn("rgb_color", lamp.calls[0])

    async def test_toggle_off_blocks_new_runs(self):
        lamp = RecordingLight("simple_disabled", [ColorMode.BRIGHTNESS])
        await self.load([lamp], enabled=False, blocked=True)
        self.assertEqual(lamp.calls, [])

    async def test_colorful_sunrise_keeps_native_conversion_and_white_fallback(self):
        color = RecordingLight("simple_rgbw", [ColorMode.RGBW])
        white = RecordingLight("simple_color_temp", [ColorMode.COLOR_TEMP])
        await self.load([color, white], sunrise_style="colorful",
                        **{name: [128, 0, 0] for name in COLOR_INPUTS})
        self.assertEqual(color.calls[0]["rgbw_color"], (255, 0, 0, 0))
        self.assertNotIn("color_temp_kelvin", color.calls[0])
        self.assertIn("color_temp_kelvin", white.calls[0])

    async def test_toggle_off_cancels_native_wait_and_saved_recovery(self):
        lamp = RecordingLight("simple_cancel", [ColorMode.BRIGHTNESS])
        wake_actions = []
        self.hass.services.async_register("test", "wake_up", lambda call: wake_actions.append(call))
        await self.load([lamp], recovery_helper=RECOVERY,
                        after_sunrise=[{"action": "test.wake_up"}])
        await self.hass.services.async_call("input_boolean", "turn_off",
                                            {"entity_id": ENABLED}, blocking=True)
        await self.wait_until(lambda: self.hass.states.get(AUTOMATION).attributes["current"] == 0)
        self.assertTrue(self.hass.states.get(RECOVERY).state.startswith("cancelled|"))
        count = len(lamp.calls)
        await self.hass.services.async_call("input_boolean", "turn_on",
                                            {"entity_id": ENABLED}, blocking=True)
        await self.hass.services.async_call("automation", "trigger",
                                            {"entity_id": AUTOMATION, "skip_condition": False},
                                            blocking=True)
        await self.hass.async_block_till_done()
        self.assertEqual(len(lamp.calls), count)
        self.assertEqual(wake_actions, [])

    async def test_disabled_saved_run_is_cancelled_during_native_startup(self):
        lamp = RecordingLight("simple_recovery", [ColorMode.BRIGHTNESS])
        now = datetime.now(timezone.utc)
        saved = f"running|{(now - timedelta(minutes=1)).timestamp()}|{(now + timedelta(minutes=4)).timestamp()}"
        await self.load([lamp], enabled=False, rejected=True, recovery_helper=RECOVERY,
                        extra_config={"input_text": {"sunrise_runtime_recovery": {
                            "max": 255, "initial": saved,
                        }}})
        self.assertEqual(lamp.calls, [])
        self.assertTrue(self.hass.states.get(RECOVERY).state.startswith("cancelled|"))


if __name__ == "__main__":
    unittest.main()
