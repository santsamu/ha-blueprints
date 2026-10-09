# Sunrise Wake-up

Simulate a gentle sunrise that finishes at your wake-up time. Brightness rises slowly at first. Choose a warm-white-to-daylight fade or a colorful sunrise with five editable colors, and schedule it using a daily manual time or a timestamp sensor containing your next alarm.

For example, a **07:00 wake-up time** with a **30-minute duration** starts the sunrise at approximately **06:30** and reaches the final light settings at **07:00**.

[Blueprint YAML](sunrise_wake_up.yaml) · [All blueprints](../README.md)

## Requirements

- Home Assistant **2024.10.0 or newer**.
- One or more lights reporting dimming support through `supported_color_modes`. Color-temperature and transition support are optional.
- For next-alarm mode, exactly one sensor with the `timestamp` device class whose state contains the alarm date and time, preferably with a time-zone offset.

No helpers or Time & Date integration are required for normal operation. Restart recovery uses an optional dedicated Text helper. Lights that support transitions can fade smoothly between updates.

## Installation

[![Import blueprint into Home Assistant](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fsantsamu%2Fha-blueprints%2Fblob%2Fmain%2Fsunrise_wake_up%2Fsunrise_wake_up.yaml)

Alternatively, follow the official [blueprint import guide](https://www.home-assistant.io/docs/automation/using_blueprints/) and import this URL:

```text
https://github.com/santsamu/ha-blueprints/blob/main/sunrise_wake_up/sunrise_wake_up.yaml
```

The GitHub import link works once the blueprint is published to this repository's `main` branch.

For a local installation, copy [sunrise_wake_up.yaml](sunrise_wake_up.yaml) into your Home Assistant configuration directory at:

```text
blueprints/automation/ha-blueprints/sunrise_wake_up.yaml
```

After importing or installing it, select **Create automation** for the blueprint, choose your lights and schedule, then save and enable the automation.

## Wake-up time sources

### Manual wake-up time

Choose **Manual wake-up time** and set the time at which the sunrise should finish. The blueprint uses Home Assistant's local time zone and repeats on the selected wake-up days. Leave the days empty to run every day.

### Smartphone next alarm

Choose **Smartphone next alarm** and select a next-alarm sensor. The input accepts a single sensor and is required for this mode. Leave it empty when using manual mode.

Existing automations saved with the previous one-item sensor list remain supported. If an existing automation has multiple alarm sensors selected, edit it and select just one.

On Android, enable the Companion App's **Next Alarm** sensor and select its entity in the automation. Android can report alarms scheduled by different apps; the sensor's package allow list can help filter these. See the official [Next alarm sensor documentation](https://companion.home-assistant.io/docs/core/sensors/#next-alarm-sensor).

For an iPhone, supply a timestamp sensor separately, as described in the blueprint's input help.

Missing, invalid, or expired alarms are skipped. This mode does not fall back to the manual wake-up time. Once a sunrise starts, its finish time is fixed: changing or clearing the phone alarm does not move or cancel that active run.

Enable **Ignore next alarms in a time range** to skip alarms whose **scheduled time** falls within a daily range in Home Assistant's local time zone. For example, **09:00–21:00** ignores daytime alarms. The range checks the alarm time, rather than the time when the sensor is checked or the sunrise begins.

The start is included and the end is excluded: an alarm at 09:00 is ignored, while one at 21:00 is allowed. Ranges can cross midnight; **22:00–06:00** ignores late-night and early-morning alarms. Equal start and end times disable the range. The option defaults to off, applies only to next-alarm mode, and has no manual-time fallback. The sensor exposes only its next alarm, so the blueprint cannot look past an ignored alarm to find a later one. Already-started sunrises, including restart recovery, keep their original deadline even if the range or phone alarm changes.

## Settings

| Setting | Default | Details |
| --- | --- | --- |
| Wake-up lights | Required | Select one or more dimmable light entities. A selection containing an on/off-only light or missing dimming capabilities stops before any light commands. |
| Wake-up time source | Manual wake-up time | Choose a fixed daily time or a smartphone next alarm. |
| Manual wake-up time | `07:00:00` | Finish time in Home Assistant's local time zone; used only in manual mode. |
| Next alarm sensor | None | Select exactly one timestamp sensor for next-alarm mode; ignored in manual mode. |
| Ignore next alarms in a time range | Off | Skip alarms scheduled inside the daily local-time range; applies to new next-alarm runs. |
| Next-alarm ignore range start | `09:00:00` | Inclusive start; used when the ignore range is enabled. |
| Next-alarm ignore range end | `21:00:00` | Exclusive end; supports crossing midnight. Equal start and end disable the range. |
| Sunrise duration | 30 minutes | Time before wake-up to begin the sunrise; 5–120 minutes. |
| Wake-up days | Every day | Applies to the day of the wake-up time, even if the sunrise starts the previous evening. |
| Starting brightness | 1% | 1–100%; limited to the final brightness if set higher. Raise this if bulbs flicker at low brightness. |
| Final brightness | 100% | 1–100%; brightness at wake-up time. |
| Sunrise style | White sunrise | Existing temperature fade, or Colorful sunrise using the editable palette on color-capable lights. |
| Sunrise color at 0% | Blue/purple `[64, 32, 255]` | Starting color; used only in Colorful sunrise. |
| Sunrise color at 25% | Pink `[255, 64, 128]` | Color one quarter through the duration. |
| Sunrise color at 50% | Orange `[255, 128, 0]` | Color halfway through the duration. |
| Sunrise color at 75% | Warm white `[255, 214, 170]` | Color three quarters through the duration. |
| Sunrise color at 100% | Daylight-like white `[220, 235, 255]` | Final color; overrides Final color temperature for color-capable lights in Colorful sunrise. |
| Starting color temperature | 2000 K | 1500–6500 K; limited to each light's supported range. |
| Final color temperature | 5500 K | 1500–6500 K; limited to each light's supported range. |
| Update interval | 15 seconds | 5–60 seconds between light updates; shorter intervals give smaller steps on lights without transitions. Separate from the schedule check interval. |
| Restart recovery helper | None | Optional dedicated Text helper storing the original run times and outcome; enables restart/reload recovery. |
| Actions at wake-up time | None | Optional actions, such as playing music, after successful completion. |

## Sunrise styles and editable colors

**White sunrise** is the default and preserves the existing behavior: tunable-white
lights fade from the starting to the final color temperature, while RGB lights
without temperature support keep their previous color as brightness increases.

Choose **Colorful sunrise** to blend through five colors on color-capable lights.
Each checkpoint has a color picker in the automation options, so you can replace
any default without editing YAML. Positions are fixed at **0%, 25%, 50%, 75%, and
100% of elapsed time**. With a 30-minute sunrise, the colors occur at the start,
7 minutes 30 seconds, 15 minutes, 22 minutes 30 seconds, and wake-up time.
All selected color lights share the same palette and show one color at a time.
This approximates a sunrise appearance; it does not reproduce Hue's proprietary
effect or control multiple gradient segments independently.

Colors blend between neighboring checkpoints using RGB channels. Their intensity
is normalized so the brightest channel is 255, including between checkpoints;
the **Starting brightness** and **Final brightness** settings control dimming
separately. For example, selecting `[10, 20, 40]` produces the same tint as
`[64, 128, 255]`. Choose non-black colors: an invalid or entirely black checkpoint
stops a Colorful sunrise before any light commands, with a reason in the trace.
Unused palette values do not affect White sunrise.

The 100% color can be any color and is applied at the final brightness. On
color-capable lights in Colorful sunrise, it takes precedence over the Kelvin
settings. White-only tunable lights still use the original temperature fade and
per-light limits, and brightness-only lights still dim. Exact colors and apparent
brightness depend on the bulb's color range and hardware.

## Light compatibility

Before sending light commands, the blueprint checks that every selected light reports a dimmable color mode. Brightness-only, tunable-white, and RGB lights are supported. On/off-only lights and lights with missing or unknown color modes stop the whole run; the automation trace explains the failure and lists the affected entities in `unsupported_lights`.

Transition support is checked separately for each light using its reported capabilities. Lights supporting transitions fade toward the next update's brightness and color. Other lights step to the settings appropriate to the current elapsed time, with no transition parameter sent. You can mix both types in one automation. Use a shorter update interval to reduce visible steps. When Colorful sunrise includes a color-capable light, update deadlines also stop at palette checkpoints so a fade does not skip a color boundary. Slow commands can still miss a checkpoint; later updates catch up to the current progress.

Color-temperature commands are sent only to lights reporting `color_temp` support and are limited to each light's supported Kelvin range. In Colorful sunrise, lights reporting `hs`, `xy`, `rgb`, `rgbw`, or `rgbww` receive the palette instead; Home Assistant converts RGB commands to their native color format. Each command contains either RGB color or color temperature. The final settings are applied at wake-up time for both fading and stepping lights. See Home Assistant's [light capability documentation](https://developers.home-assistant.io/docs/core/entity/light/#color-modes).

## Restart and reload recovery

To enable recovery, create a **Text** helper under **Settings > Devices & services > Helpers**, set its maximum length to **255**, and select it in **Restart recovery helper**. Use a separate helper for each automation. Leave its contents under the blueprint's control; if configured in YAML, omit `initial` so its saved state is restored. See the official [Text helper documentation](https://www.home-assistant.io/integrations/input_text/#restore-state).

The blueprint saves the original start and finish times and whether the run is running, cancelled, or completed. Following a Home Assistant restart or automation reload, a saved running sunrise can resume at the progress appropriate to the current time, even if the phone alarm was changed or cleared. The original duration and finish time are retained. Recovery is checked at Home Assistant startup and on the usual 15-second schedule checks.

Colorful sunrise also resumes at the color appropriate to that progress. The
recovery record format is unchanged. Style and palette values come from the
currently saved automation options, just like brightness and temperature settings;
changing those options before recovery can change the resumed appearance. Colors
are calculated from elapsed time, so recovery does not replay earlier checkpoints.

Recovery requires the saved wake-up time to still be in the future, the wake-up day to be allowed, and all selected lights to be available and already on. If any light reports `off`, the saved run is marked cancelled without switching it back on. Unavailable lights defer recovery until their states are known; the run expires at its original wake-up time. Cancelled and completed runs are not resumed.

The helper is marked completed before optional wake-up actions run. Those actions are not replayed after an interruption, so a restart during them can leave them unfinished. Recovery cannot observe a light being switched off and back on while Home Assistant is down. State restoration depends on Home Assistant saving the helper's latest state; an abrupt power loss can lose recent updates.

Leave the helper unset to retain normal operation without recovery. If a selected helper is unavailable, the automation waits for it rather than starting without saved state.

## Behavior and cancellation

- The schedule is checked every **15 seconds**, so the start can occur shortly after the calculated start time.
- A run can start only during the sunrise window, before the wake-up time, with the selected lights reporting `on` or `off`.
- Lights already on are adjusted too. The blueprint does not require them to be off before starting.
- After the initial light commands, the blueprint waits up to **15 seconds**, or until wake-up time if sooner, for every selected light to report `on`. It continues immediately once all lights are on. If the wait times out, the run stops with a startup timeout reason in the automation trace and skips wake-up actions.
- If a run starts partway through its window, it begins at the brightness and color appropriate to the elapsed time.
- Brightness follows a quadratic curve, rising slowly at first and faster toward the end.
- Each update has an absolute deadline capped at wake-up time. Command latency reduces later lights' transition durations and the remaining wait, instead of adding another full interval. If commands overrun an update, the wait is zero and settings catch up to the current progress. Slow service calls or device responses can still delay final settings and wake-up actions; those actions run after the final light commands complete.
- Turning any selected light off, or a light becoming unavailable during the ramp, cancels the entire sunrise. Remaining lights keep their current state; cancellation does not turn them off.
- The automation blocks another start within the same sunrise window, including after cancellation. With recovery enabled, a saved running sunrise may resume within its original window.
- On successful completion, lights stay on at the final settings, then any configured wake-up actions run. Those actions are skipped after cancellation.

## Try it out

1. Use manual mode and set a wake-up time about **6 minutes from now**.
2. Set the duration to **5 minutes** and leave wake-up days empty.
3. Save and enable the automation, then wait for the scheduled start.
4. To check cancellation, turn one selected light off during the ramp. Use a later wake-up window for another test.

The automation's **Run actions** control still checks whether the current time is inside the sunrise window, so running it outside that window will not start the lights.

For a physical color test, select a color-capable bulb and **Colorful sunrise**,
then use the five-minute test above. The default colors should progress through
blue/purple, pink, orange, warm white, and daylight-like white. Replace the 100%
color with an obvious color to check that it overrides the Kelvin setting and
remains on at completion. Add a tunable-white or brightness-only light to check
the fallback behavior. Turning any selected light off during the ramp should
still cancel the whole sunrise and skip wake-up actions.

The [automated checks](../tests/README.md) cover palette interpolation, timing,
recovery, cancellation, and native Home Assistant light-command conversion.

To check recovery, select a recovery helper, start a sunrise, then reload automations while the lights stay on. It should resume within about 15 seconds with the original finish time. Repeat with a new window, cancel by switching a light off, and reload; that cancelled run should stay stopped.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Sunrise does not start | Enable the automation, select at least one light, check the wake-up day and time zone, and confirm all selected lights are available. A run already started in this window prevents a scheduled retry. |
| Trace reports missing dimming support | Inspect `unsupported_lights` in the trace and each entity's `supported_color_modes`. Remove on/off-only lights, or check the integration if a dimmable bulb reports missing or unknown capabilities. |
| Sunrise stops just after turning lights on | Check the automation trace for a startup timeout. All selected lights must report `on` within 15 seconds of the initial commands completing, or before wake-up time if sooner. Check bulb connectivity and state updates. |
| Interrupted sunrise does not resume | Check the dedicated recovery helper, its saved running state, the original finish time, and the selected lights. Recovery requires all lights to be available and already on; an off light cancels recovery. |
| Next-alarm mode does nothing | Select exactly one timestamp sensor and check its state in Home Assistant. It must contain a valid future alarm date and time outside any enabled ignore range. |
| Wrong phone alarm is used | Check the Android sensor's package information and allow list. |
| Lights flicker or visibly step | Increase starting brightness for flicker. Lights without reported transition support use steps; reduce the update interval for smaller changes. |
| Color temperature does not change | Check the light's color-temperature support and range. Brightness-only lights skip color changes. |
| Final settings or wake-up actions arrive late | Inspect light service durations in the automation trace and bulb connectivity. The loop subtracts command time from its waits, but it cannot remove delays from slow service calls or devices. |
| Wake-up actions do not run | Check whether a selected light was switched off or became unavailable before completion. |

## Credits

Inspired by seanharsh's Sunrise Light Simulator; independently implemented, as noted in the blueprint.
