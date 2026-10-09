# Home Assistant Blueprints

A collection of automation blueprints for Home Assistant. Each blueprint has its own folder with the YAML file and a README covering setup, settings, and behavior.

## Available blueprints

| Blueprint | Description | Minimum Home Assistant version |
| --- | --- | --- |
| [Sunrise Wake-up](sunrise_wake_up/README.md) | Gradually brighten your lights before a fixed wake-up time or your next phone alarm, with an optional warm-white-to-daylight fade. | 2024.10.0 |

## Getting started

1. Open a blueprint's README and check its requirements.
2. Import the blueprint into Home Assistant using its import link, or copy the YAML into your Home Assistant configuration's `blueprints/automation/` directory.
3. Create an automation from the imported blueprint, configure its inputs, and save it.

See the official [Using automation blueprints](https://www.home-assistant.io/docs/automation/using_blueprints/) guide for import and automation creation instructions.

## Repository layout

```text
sunrise_wake_up/
  README.md                 Setup and configuration guide
  sunrise_wake_up.yaml       Automation blueprint
```
