# Sunrise Wake-up

Simulate a gentle sunrise that finishes at your wake-up time. Brightness rises slowly at first, and tunable-white lights fade from warm white toward daylight. Choose a daily manual time or a timestamp sensor containing your next alarm.

For example, a **07:00 wake-up time** with a **30-minute duration** starts the sunrise at approximately **06:30** and reaches the final light settings at **07:00**.

[Blueprint YAML](sunrise_wake_up.yaml) · [All blueprints](../README.md)

## Requirements

- Home Assistant **2024.10.0 or newer**.
- One or more dimmable lights. Color-temperature support is optional; lights without it receive brightness changes only.
- For next-alarm mode, exactly one sensor with the `timestamp` device class whose state contains the alarm date and time, preferably with a time-zone offset.

No helpers or Time & Date integration are required. Lights that support transitions can fade smoothly between updates.

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

## Settings

| Setting | Default | Details |
| --- | --- | --- |
| Wake-up lights | Required | Select one or more dimmable light entities. |
| Wake-up time source | Manual wake-up time | Choose a fixed daily time or a smartphone next alarm. |
| Manual wake-up time | `07:00:00` | Finish time in Home Assistant's local time zone; used only in manual mode. |
| Next alarm sensor | None | Select exactly one timestamp sensor for next-alarm mode; ignored in manual mode. |
| Sunrise duration | 30 minutes | Time before wake-up to begin the sunrise; 5–120 minutes. |
| Wake-up days | Every day | Applies to the day of the wake-up time, even if the sunrise starts the previous evening. |
| Starting brightness | 1% | 1–100%; limited to the final brightness if set higher. Raise this if bulbs flicker at low brightness. |
| Final brightness | 100% | 1–100%; brightness at wake-up time. |
| Starting color temperature | 2000 K | 1500–6500 K; limited to each light's supported range. |
| Final color temperature | 5500 K | 1500–6500 K; limited to each light's supported range. |
| Update interval | 15 seconds | 5–60 seconds between light updates; separate from the schedule check interval. |
| Actions at wake-up time | None | Optional actions, such as playing music, after successful completion. |

## Behavior and cancellation

- The schedule is checked every **15 seconds**, so the start can occur shortly after the calculated start time.
- A run can start only during the sunrise window, before the wake-up time, with the selected lights reporting `on` or `off`.
- Lights already on are adjusted too. The blueprint does not require them to be off before starting.
- After the initial light commands, the blueprint waits up to **15 seconds**, or until wake-up time if sooner, for every selected light to report `on`. It continues immediately once all lights are on. If the wait times out, the run stops with a startup timeout reason in the automation trace and skips wake-up actions.
- If a run starts partway through its window, it begins at the brightness and color temperature appropriate to the elapsed time.
- Brightness follows a quadratic curve, rising slowly at first and faster toward the end.
- Turning any selected light off, or a light becoming unavailable during the ramp, cancels the entire sunrise. Remaining lights keep their current state; cancellation does not turn them off.
- The automation blocks another start within the same sunrise window, including after cancellation.
- On successful completion, lights stay on at the final settings, then any configured wake-up actions run. Those actions are skipped after cancellation.

## Try it out

1. Use manual mode and set a wake-up time about **6 minutes from now**.
2. Set the duration to **5 minutes** and leave wake-up days empty.
3. Save and enable the automation, then wait for the scheduled start.
4. To check cancellation, turn one selected light off during the ramp. Use a later wake-up window for another test.

The automation's **Run actions** control still checks whether the current time is inside the sunrise window, so running it outside that window will not start the lights.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Sunrise does not start | Enable the automation, select at least one light, check the wake-up day and time zone, and confirm all selected lights are available. A run already started in this window prevents a scheduled retry. |
| Sunrise stops just after turning lights on | Check the automation trace for a startup timeout. All selected lights must report `on` within 15 seconds of the initial commands completing, or before wake-up time if sooner. Check bulb connectivity and state updates. |
| Next-alarm mode does nothing | Select exactly one timestamp sensor and check its state in Home Assistant. It must contain a valid future alarm date and time. |
| Wrong phone alarm is used | Check the Android sensor's package information and allow list. |
| Lights flicker or visibly step | Increase starting brightness for flicker. For stepping, check whether the lights support transitions and adjust the update interval. |
| Color temperature does not change | Check the light's color-temperature support and range. Brightness-only lights skip color changes. |
| Wake-up actions do not run | Check whether a selected light was switched off or became unavailable before completion. |

## Credits

Inspired by seanharsh's Sunrise Light Simulator; independently implemented, as noted in the blueprint.
