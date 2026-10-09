"""Import the sunrise blueprint and send commands through the native light service."""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from homeassistant import bootstrap, loader
from homeassistant.components import light
from homeassistant.components.light import ColorMode, LightEntity, LightEntityFeature
from homeassistant.core import HomeAssistant


BLUEPRINT_PATH = "sunrise_wake_up/sunrise_wake_up.yaml"
BLUEPRINT = Path(__file__).resolve().parents[2] / BLUEPRINT_PATH
AUTOMATION = "automation.sunrise_runtime"
COLOR_INPUTS = [f"sunrise_color_{percent}" for percent in (0, 25, 50, 75, 100)]


class RecordingLight(LightEntity):
    """Replace hardware only; Home Assistant still validates and converts commands."""

    _attr_should_poll = False
    _attr_supported_features = LightEntityFeature.TRANSITION
    _attr_min_color_temp_kelvin = 2700
    _attr_max_color_temp_kelvin = 6500

    def __init__(self, name, modes):
        self.entity_id = "light." + name
        self._attr_name = name
        self._attr_unique_id = name
        self._attr_supported_color_modes = set(modes)
        self._attr_color_mode = modes[0]
        self._attr_is_on = False
        self._attr_brightness = 255
        self._attr_rgb_color = (16, 32, 64)
        self._attr_color_temp_kelvin = 3000
        self.calls = []

    async def async_turn_on(self, **kwargs):
        self.calls.append(dict(kwargs))
        self._attr_is_on = True
        self._attr_brightness = kwargs.get("brightness", self._attr_brightness)
        for field, mode in (("rgb_color", ColorMode.RGB), ("hs_color", ColorMode.HS),
                            ("xy_color", ColorMode.XY), ("rgbw_color", ColorMode.RGBW),
                            ("rgbww_color", ColorMode.RGBWW), ("color_temp_kelvin", ColorMode.COLOR_TEMP)):
            if field in kwargs:
                setattr(self, "_attr_" + field, kwargs[field])
                self._attr_color_mode = mode
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        self._attr_is_on = False
        self.async_write_ha_state()


class SunriseRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TemporaryDirectory(prefix="ha-sunrise-runtime-")
        self.addCleanup(self.temp.cleanup)
        destination = Path(self.temp.name) / "blueprints/automation" / BLUEPRINT_PATH
        destination.parent.mkdir(parents=True)
        shutil.copyfile(BLUEPRINT, destination)
        self.hass = HomeAssistant(self.temp.name)
        self.hass.config.skip_pip = True
        loader.async_setup(self.hass)

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)

    async def wait_until(self, predicate):
        async with asyncio.timeout(5):
            while not predicate():
                await asyncio.sleep(0.005)

    async def load(self, lamps, *, rejected=False, **inputs):
        blueprint_inputs = {
            "lights": [lamp.entity_id for lamp in lamps],
            "time_source": "next_alarm", "next_alarm_sensor": "sensor.sunrise_runtime_alarm",
            "sunrise_duration": 5, "initial_brightness": 20, "final_brightness": 20,
            **inputs,
        }
        config = {"homeassistant": {
            "latitude": 47.0, "longitude": 8.0, "elevation": 400,
            "time_zone": "UTC", "unit_system": "metric", "currency": "CHF",
        }, "light": [], "automation": [{
            "id": "sunrise_runtime", "alias": "Sunrise runtime",
            "use_blueprint": {"path": BLUEPRINT_PATH, "input": blueprint_inputs},
        }]}
        self.assertIs(await bootstrap.async_from_config_dict(config, self.hass), self.hass)
        await self.hass.data[light.DATA_COMPONENT].async_add_entities(lamps)
        self.hass.states.async_set("sensor.sunrise_runtime_alarm",
                                   (datetime.now(timezone.utc) + timedelta(minutes=4)).isoformat(),
                                   {"device_class": "timestamp"})
        await self.hass.async_start()
        state = self.hass.states.get(AUTOMATION)
        self.assertIsNotNone(state, "The repository blueprint must import successfully")
        self.assertEqual(state.state, "on")
        if rejected:
            async with asyncio.timeout(5):
                await self.hass.async_block_till_done()
            self.assertIsNotNone(self.hass.states.get(AUTOMATION).attributes["last_triggered"])
        else:
            await self.wait_until(lambda: all(lamp.calls for lamp in lamps))

    async def test_rgb_palette_is_converted_to_each_supported_native_color_mode(self):
        fields = [(ColorMode.RGB, "rgb_color"), (ColorMode.HS, "hs_color"),
                  (ColorMode.XY, "xy_color"), (ColorMode.RGBW, "rgbw_color"),
                  (ColorMode.RGBWW, "rgbww_color")]
        lamps = [RecordingLight("runtime_" + mode.value, [mode]) for mode, _ in fields]
        await self.load(lamps, sunrise_style="colorful", **{name: [128, 0, 0] for name in COLOR_INPUTS})
        for lamp, (_, field) in zip(lamps, fields):
            with self.subTest(light=lamp.entity_id):
                data = lamp.calls[0]
                self.assertIn(field, data)
                self.assertEqual(data["brightness"], 51)
                self.assertEqual(data["transition"], 0)
                self.assertNotIn("color_temp_kelvin", data)
                self.assertEqual(sum(key in data for _, key in fields), 1)
        self.assertEqual(lamps[0].calls[0]["rgb_color"], (255, 0, 0))
        self.assertEqual(lamps[1].calls[0]["hs_color"], (0, 100))
        self.assertEqual(lamps[3].calls[0]["rgbw_color"], (255, 0, 0, 0))
        self.assertEqual(lamps[4].calls[0]["rgbww_color"], (255, 0, 0, 0, 0))

    async def test_colorful_style_prefers_color_and_falls_back_for_white_and_dimmer(self):
        color = RecordingLight("runtime_color", [ColorMode.RGB, ColorMode.COLOR_TEMP])
        white = RecordingLight("runtime_white", [ColorMode.COLOR_TEMP])
        dimmer = RecordingLight("runtime_dimmer", [ColorMode.BRIGHTNESS])
        await self.load([color, white, dimmer], sunrise_style="colorful",
                        **{name: [0, 64, 0] for name in COLOR_INPUTS})
        self.assertEqual(color.calls[0]["rgb_color"], (0, 255, 0))
        self.assertNotIn("color_temp_kelvin", color.calls[0])
        self.assertEqual(white.calls[0]["color_temp_kelvin"], 2700)
        self.assertNotIn("rgb_color", white.calls[0])
        self.assertNotIn("rgb_color", dimmer.calls[0])
        self.assertNotIn("color_temp_kelvin", dimmer.calls[0])
        self.assertEqual(dimmer.calls[0]["brightness"], 51)

    async def test_default_white_style_preserves_temperature_and_existing_rgb_color(self):
        color = RecordingLight("runtime_color", [ColorMode.RGB])
        white = RecordingLight("runtime_white", [ColorMode.COLOR_TEMP])
        await self.load([color, white], sunrise_color_0=[0, 0, 0])
        self.assertNotIn("rgb_color", color.calls[0])
        self.assertEqual(color.rgb_color, (16, 32, 64))
        self.assertEqual(white.calls[0]["color_temp_kelvin"], 2700)

    async def test_black_palette_stops_before_native_light_commands(self):
        lamp = RecordingLight("runtime_color", [ColorMode.RGB])
        await self.load([lamp], rejected=True, sunrise_style="colorful", sunrise_color_50=[0, 0, 0])
        self.assertEqual(lamp.calls, [])
        self.assertEqual(self.hass.states.get(AUTOMATION).attributes["current"], 0)


if __name__ == "__main__":
    unittest.main()
