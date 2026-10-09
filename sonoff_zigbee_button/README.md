# Sonoff Zigbee Button

Assign separate Home Assistant actions to **press**, **double press**, and **hold** on a SONOFF Zigbee button. For example, use press to toggle a light, double press to activate a scene, and hold to turn off the room's lights.

[Blueprint YAML](sonoff_zigbee_button.yaml) · [All blueprints](../README.md)

## Requirements

- Home Assistant **2024.10.0 or newer**.
- A button paired through [Zigbee Home Automation (ZHA)](https://www.home-assistant.io/integrations/zha/).
- A device reported as manufacturer **eWeLink**, model **WB01** (SONOFF SNZB-01) or **SNZB-01P**, matching the supplied reference blueprint.

This blueprint listens to `zha_event` events. Zigbee2MQTT uses different triggers and needs a separate blueprint. No helpers are required.

## Installation

[![Import blueprint into Home Assistant](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fsantsamu%2Fha-blueprints%2Fblob%2Fmain%2Fsonoff_zigbee_button%2Fsonoff_zigbee_button.yaml)

Alternatively, follow the official [blueprint import guide](https://www.home-assistant.io/docs/automation/using_blueprints/) and import:

```text
https://github.com/santsamu/ha-blueprints/blob/main/sonoff_zigbee_button/sonoff_zigbee_button.yaml
```

The import link works once this file is published to the repository's `main` branch. For a local installation, copy the YAML file into your Home Assistant configuration directory at:

```text
blueprints/automation/ha-blueprints/sonoff_zigbee_button.yaml
```

Create an automation from the blueprint, select your button, configure the actions you want, and save and enable the automation. Leave unused gesture actions empty.

## Settings

| Setting | Default | Details |
| --- | --- | --- |
| Button | Required | One supported button paired through ZHA. |
| Automation mode | `single` | Determines how new gestures are handled while actions are running. |
| Press Action | None | Actions for a single press (`toggle`). |
| Double Press Action | None | Actions for a double press (`on`). |
| Hold Action | None | Actions for hold (`off`). |

The command names identify button gestures; they do not force your configured actions to toggle, turn on, or turn off anything.

## Automation modes

| Mode | Behavior when another gesture arrives |
| --- | --- |
| `single` | Ignore the new gesture while the current sequence runs. |
| `restart` | Stop the current sequence and start the new gesture's sequence. |
| `queued` | Run sequences in the order gestures arrive. |
| `parallel` | Run each gesture's sequence concurrently. |

Queued and parallel modes use Home Assistant's default limit of **10 runs**; queued includes the active run and waiting runs. Requests exceeding the limit are ignored. With `single`, requests during an active run are also ignored. The blueprint suppresses warnings for these ignored requests with `max_exceeded: silent`. See [Automation modes](https://www.home-assistant.io/docs/automation/modes/).

Hold runs its configured sequence once for each matching hold event. It does not add repeated actions while the button stays held or a separate release action.

## Verify and troubleshoot

Test all three gestures using short actions you can observe, such as changing a light. Use the automation trace to check which gesture triggered and which actions ran.

If nothing happens, open **Developer tools > Events**, listen to `zha_event`, and operate the button. Confirm that the event's `device_id` matches the selected button and its `command` is `toggle` for press, `on` for double press, or `off` for hold. These are the mappings used by the supplied reference; actual device events should be checked on your installation.

If the button is absent from the picker, check that it is paired through ZHA and that its manufacturer and model match the requirements above. If presses are ignored while an action is running, check the selected automation mode and any long delays or waits in your actions.

Home Assistant's **Run actions** control has no button trigger ID, so it does not select a gesture branch. Test by operating the actual button.

## Credits

Based on the [Sonoff Zigbee Button blueprint by apollo1220](https://github.com/apollo1220/blueprints/blob/main/sonoff_zigbee_button.yaml), supplied as the reference. This version uses ZHA-only device filters and trigger IDs to select gesture actions.
