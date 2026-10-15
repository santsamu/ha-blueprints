# SONOFF SNZB-03P Motion Lights

Turn on one or more lights when motion is detected, using brightness and either
color or white temperature. Choose one shared profile or separate day/night
profiles. Lights whose settings change during a session are left on at timeout;
the other lights still switch off normally.

[Blueprint YAML](sonoff_motion_lights.yaml) · [All blueprints](../README.md)

## Requirements

- Home Assistant **2025.4.0 or newer**. This blueprint uses the newer script
  [variable scoping](https://www.home-assistant.io/blog/2025/04/02/release-20254/#automation--script-variable-scopes)
  to retain per-light override flags across nested actions.
- A SONOFF SNZB-03P paired through ZHA or Zigbee2MQTT and exposed as a motion or
  occupancy binary sensor. Other sensors with the same on/off behavior also work.
- At least one light entity. Select individual lights for independent override
  protection. A light group is treated as one entity; changes to a member may not
  be reflected reliably in the group's attributes.

No helpers are required. The blueprint listens to Home Assistant entity states,
so no integration-specific Zigbee event mapping is needed.

## Installation

[![Import blueprint into Home Assistant](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fsantsamu%2Fha-blueprints%2Fblob%2Fmain%2Fsonoff_motion_lights%2Fsonoff_motion_lights.yaml)

The import link works after publication to `main`. For a local installation,
copy the YAML to `blueprints/automation/ha-blueprints/sonoff_motion_lights.yaml`
inside your Home Assistant configuration directory. Create an automation from
the blueprint, select the sensor and lights, configure the profiles, then save
and enable it. Trigger it by moving in front of the sensor after it has cleared.

## Settings

| Setting | Default | Behavior |
| --- | --- | --- |
| Motion sensor | Required | One motion/occupancy binary sensor; `on` means motion. |
| Lights | Required | One or multiple individual light entities. |
| Duration | 2 minutes | Must be greater than zero. |
| Timer mode | After motion clears | Choose a resettable motion-clear countdown or a fixed duration from activation. |
| Only control lights that are off | Enabled | Evaluate each light separately. Already-on lights are skipped. When disabled, already-on lights also receive the profile and can be switched off. |
| Daylight settings | Shared | Use one main profile, sun-based day/night profiles, or an optional daylight binary sensor. |
| Daylight binary sensor | Empty | Only used in binary-sensor mode; `on` must mean bright/day, `off` dark/night. |
| Main/day mode, brightness, temperature, color | White, 80%, 4000 K, warm orange | Main profile in Shared mode, daytime profile otherwise. Color is only used in Color mode. |
| Night mode, brightness, temperature, color | White, 20%, 2700 K, orange | Nighttime profile when daylight settings are enabled. |

Each profile offers **White temperature**, **Color**, or **Keep existing color**.
Brightness applies independently. Colors are normalized to full intensity so
the brightness input controls dimming; black is rejected in Color mode.

Color and white temperature are alternative modes, so the blueprint sends only
one of them per command. Color commands use Home Assistant's native conversion
for RGB, RGBW, RGBWW, HS, and XY lights. In Color mode, tunable-white lights fall
back to the profile's white temperature. White temperature is clamped to each
light's range. Lights without temperature support retain their color in White
mode; dimmers receive brightness only, and on/off lights receive on/off only.
Supported transitions are explicitly set to zero for reliable change tracking.

## Timing and daylight

**After motion clears:** lights remain on while the sensor reports motion. The
configured countdown starts when the sensor reports `off`. Further motion
cancels the countdown; the full duration starts again on the next clear report.
The sensor's own detection-clear delay adds to the configured duration.

**Fixed duration:** the deadline is set when the session starts, before light
commands. Further motion does not extend it. A new session requires a later
`off` → `on` motion transition; continuous motion does not retrigger after timeout.

Further motion never reapplies the profile during an active session. A light
that was already on and skipped initially is not adopted later in that session.

Sun mode uses `sun.sun`: above the horizon means day, below means night. Binary
mode accepts an entity whose `on` state means daylight. The SNZB-03P's ambient
light indication and its exposed entities depend on your integration; do not
assume it supplies numeric lux or that its binary polarity matches this input.
Use Sun mode or a template binary sensor if necessary. An unavailable or missing
daylight source prevents activation in that mode. Shared mode needs no source.

The profile is chosen once per session. Sunrise, sunset, or a daylight-sensor
change during the session does not change the lights.

## Protecting changed lights

Each light is tracked separately after it confirms its requested settings.
Brightness, active color mode, color, white temperature, power changes, or
unavailability release the affected light from automatic shutoff for the
remainder of that session. Changes from other automations get the same protection
as changes from the app, a remote, or a physical switch. Returning to the original
settings does not restore ownership. Small reporting differences are tolerated:
1 brightness step, 25 K, 1 RGB channel step, 0.5 HS units, or 0.001 XY units.
Differences are always compared with the original baseline to prevent drift.

Unrelated attributes normally do not release a light. If an update arrives in
the short gap between event waits, during another light's startup, or immediately
before shutoff, the blueprint conservatively releases it using its update
timestamp. This also protects changes that were rapidly reverted in those gaps.
Delayed reports of the blueprint's own command may likewise leave a light on.

Startup waits up to two seconds per light for confirmation. A light that fails
or does not confirm its settings is left out of automatic shutoff, and remaining
lights are still attempted. The fixed deadline includes this startup time.
Protection relies on the integration reporting device changes; changes never
reported to Home Assistant cannot be detected.

The session stays active until its timer ends even if every tracked light was
released, preventing new motion from taking control again. A fresh session may
control lights again according to the off-only setting.

## Restart, reload, and troubleshooting

Home Assistant restart, automation reload, or disabling the automation stops an
active session and leaves lights in their current state. There is no restart
recovery or deferred shutoff. A motion sensor becoming unknown/unavailable also
ends the session without shutting lights off; recovery to `on` alone does not
start a session. The next normal `off` → `on` transition can start one.

Use one instance per sensor/lighting set and avoid overlapping instances that
control the same lights. Check the automation trace if a light stays on: it may
have been on initially, changed settings, failed to confirm startup, or received
a report in an event-wait gap. Device reporting and the sensor's clear delay
should also be checked with the actual hardware.

The [automated checks](../tests/README.md) evaluate the YAML templates and exercise
the imported blueprint through Home Assistant's actual automation engine and
light services, including reverted changes and repeated motion.

References: [SONOFF SNZB-03P](https://sonoff.tech/en-br/products/sonoff-zigbee-motion-sensor-snzb-03p),
[Home Assistant lights](https://www.home-assistant.io/integrations/light/),
[script waits](https://www.home-assistant.io/docs/scripts/#wait-for-a-trigger),
and [Sun integration](https://www.home-assistant.io/integrations/sun/).
