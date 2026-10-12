# Sunrise Wake-up Simple

A sunrise scheduled by a **time helper** and controlled by an **on/off helper**. Choose a white fade or a colorful sunrise with five editable colors. Wake-up days, restart recovery, and actions at wake-up time are included.

For example, a helper set to **06:30** with a **30-minute duration** starts the sunrise at approximately **06:00** and reaches the final light settings at **06:30**.

[Blueprint YAML](sunrise_wake_up_simple.yaml) · [All blueprints](../README.md) · [Sunrise Wake-up with additional time sources](../sunrise_wake_up/README.md)

## Requirements

- Home Assistant **2024.10.0 or newer**.
- One or more dimmable lights. Color and transition support are optional.
- A time-only `input_datetime` helper (`has_time: true`, `has_date: false`).
- An `input_boolean` toggle helper to enable or disable the sunrise.

## Installation and setup

[![Import blueprint into Home Assistant](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fsantsamu%2Fha-blueprints%2Fblob%2Fmain%2Fsunrise_wake_up_simple%2Fsunrise_wake_up_simple.yaml)

The import link works once this blueprint is published to the repository's `main` branch. For a local installation, copy [sunrise_wake_up_simple.yaml](sunrise_wake_up_simple.yaml) into:

```text
blueprints/automation/ha-blueprints/sunrise_wake_up_simple.yaml
```

1. Under **Settings > Devices & services > Helpers**, create a **Date and/or time** helper with **time only**, without a date. Set it to the time at which the sunrise should finish.
2. Create a **Toggle** helper, such as “Sunrise enabled”.
3. Create an automation from this blueprint. Select your lights, **Wake-up time helper**, and **Sunrise enabled helper**.
4. Set the duration, wake-up days, and light settings, then save and enable the automation.
5. Turn the toggle helper **on** to enable the sunrise schedule. You can add both helpers to a dashboard or change them from another automation.

See the official [Input Datetime](https://www.home-assistant.io/integrations/input_datetime/) and [Toggle helper](https://www.home-assistant.io/integrations/input_boolean/) documentation for helper setup.

## Settings

| Setting | Default | Details |
| --- | --- | --- |
| Wake-up lights | Required | Select one or more dimmable lights. |
| Wake-up time helper | Required | One time-only `input_datetime` helper, using Home Assistant's local time zone. |
| Sunrise enabled helper | Required | One `input_boolean` helper. On enables the sunrise; off blocks new runs and cancels an active run. |
| Sunrise duration | 30 minutes | Begin this many minutes before the helper's wake-up time; 5–120 minutes. |
| Wake-up days | Every day | Applies to the wake-up day, including when the sunrise begins the previous evening. Leave empty for every day. |
| Starting brightness | 1% | Raise this if bulbs flicker at low brightness; limited to the final brightness. |
| Final brightness | 100% | Brightness at wake-up time. |
| Sunrise style | White sunrise | A warm-white-to-daylight fade, or Colorful sunrise. |
| Sunrise colors | Blue/purple, pink, orange, warm white, daylight | Five editable colors at 0%, 25%, 50%, 75%, and 100% of the duration. Choose non-black colors. |
| Starting color temperature | 2000 K | Used for White sunrise and tunable-white lights in Colorful sunrise; limited to each light's supported range. |
| Final color temperature | 5500 K | Final white temperature. Color-capable lights in Colorful sunrise use the 100% palette color instead. |
| Update interval | 15 seconds | 5–60 seconds between light updates; transitions are used when supported. |
| Restart recovery helper | None | Optional dedicated Text helper storing the original run times and outcome. |
| Actions at wake-up time | None | Optional actions after successful completion; skipped after cancellation. |

## Sunrise behavior and the on/off helper

The schedule is checked every **15 seconds**. The time helper supplies a daily wake-up time; there is no manual-time or next-alarm setting. An empty, invalid, unknown, or unavailable time helper, or a helper containing a date, skips new runs. Once a sunrise starts, changing the time helper does not move or cancel its original finish time.

The toggle must be **on** to start or resume a sunrise. Turning it off, or it becoming unknown or unavailable, cancels an active sunrise and skips wake-up actions. Cancellation stops further light updates; lights retain their last commanded settings, and a transition already sent to a bulb may finish. Wake-up actions that have already begun are not interrupted or undone. The blueprint does not switch the lights off or change the toggle. On leaves the schedule enabled for future allowed days.

Turning the toggle on partway through a sunrise window can start a run at the brightness and color appropriate to the elapsed time. After a run has started, turning the toggle off and back on does not restart it in that same window. Turning any selected light off, or a light becoming unavailable during the ramp, also cancels the entire sunrise.

Brightness rises slowly at first, following a quadratic curve. White sunrise changes the temperature on tunable-white lights. Colorful sunrise blends through the five palette colors on color-capable lights; color intensity is normalized independently of brightness. Tunable-white lights retain the white fade, and brightness-only lights dim. All selected color lights use the same palette.

Every selected light must report dimming support. Unsupported lights or an invalid/black palette in Colorful sunrise stop the run before any light commands. Lights must report on within 15 seconds of the initial commands completing, or before wake-up time if sooner. Successful runs leave the lights on at their final settings, then execute any wake-up actions. Slow light commands can still delay completion.

## Restart recovery

Create a dedicated **Text** helper with a maximum length of **255**, and select it in **Restart recovery helper**. Use one helper per automation, leave its contents under the blueprint's control, and omit `initial` if configuring it in YAML. See the official [Text helper documentation](https://www.home-assistant.io/integrations/input_text/#restore-state).

If a newly created YAML Text helper reports `unknown`, initialize it once before the first run using `input_text.set_value` with an empty string as the value. Leave `initial` unset so future restarts can restore the saved record.

A saved running sunrise can resume after a Home Assistant restart or automation reload, with its original start time, duration, and finish time. Recovery requires the toggle to be on, the original wake-up day to be allowed, the deadline to still be in the future, and all selected lights to be available and already on. Changes to the time helper, or it becoming unavailable, do not change that saved deadline. Current brightness, style, and palette settings are used when resuming.

If the toggle is off or unavailable when an otherwise eligible recovery is checked, the saved run is marked cancelled without changing the lights. Turning the toggle back on does not resume that cancelled run. Off lights also cancel recovery; unavailable lights defer it while the toggle is on. Cancelled and completed runs are not resumed.

The recovery helper is marked completed before wake-up actions run, so those actions are not replayed after an interruption. Recovery cannot detect a toggle or light being switched off and back on while Home Assistant is down. An abrupt power loss can lose the latest saved helper state.

Leave the recovery helper unset to disable recovery. If a selected recovery helper is unknown or unavailable, the automation waits for it. Without recovery, restart/reload behavior relies on Home Assistant retaining the automation's last-triggered state.

## Try it out

Set the time helper to about **6 minutes from now**, set the duration to **5 minutes**, leave wake-up days empty, and turn the toggle on. The sunrise should start about one minute later. Turn the toggle off during the ramp to check cancellation; turn it back on and verify that the same window does not restart. Use a later wake-up time for another test.

For recovery, select a recovery helper, start a new run, and reload automations while the toggle and lights stay on. The run should resume within about 15 seconds with the original deadline. Wake-up actions run only after successful completion.

The [automated checks](../tests/README.md) cover helper scheduling, enable/disable behavior, weekdays, colors, cancellation, and recovery, including native Home Assistant execution.
