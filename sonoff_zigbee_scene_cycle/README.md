# SONOFF Zigbee Scene Cycle

Each **double press** activates the next scene in an ordered list. Use a configured scene list with a Number helper, or a Dropdown helper containing the scene list and current selection. With three scenes, the cycle is **Scene 1 → Scene 2 → Scene 3 → Scene 1**. Single press and hold have their own optional actions.

[Blueprint YAML](sonoff_zigbee_scene_cycle.yaml) · [All blueprints](../README.md)

## Requirements

- Home Assistant **2024.10.0 or newer**.
- A SONOFF button paired through **ZHA**, reported as manufacturer **eWeLink**, model **WB01** (SNZB-01) or **SNZB-01P**.
- The scenes you want to cycle through.
- Either a dedicated `input_number` helper for the last selected scene position, or a dedicated `input_select` Dropdown helper containing scene entity IDs as its options.

The blueprint uses `zha_event`: `toggle` for single press, `on` for double press, and `off` for hold. Verify these events on your installation. Zigbee2MQTT requires different triggers.

## Installation and setup

[![Import blueprint into Home Assistant](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fsantsamu%2Fha-blueprints%2Fblob%2Fmain%2Fsonoff_zigbee_scene_cycle%2Fsonoff_zigbee_scene_cycle.yaml)

The import link works once this file is published to the repository's `main` branch. For a local installation, copy the YAML file into:

```text
blueprints/automation/ha-blueprints/sonoff_zigbee_scene_cycle.yaml
```

Create an automation from this blueprint, select the button, and choose **Scene cycle source**. The default is **Scene list and Number helper**, preserving existing configurations.

### Scene list and Number helper

1. Under **Settings > Devices & services > Helpers**, create a **Number** helper with minimum **0**, maximum **at least the number of scenes**, and step **1**. For three scenes, maximum 3 or 4 both work.
2. Set its value to **0** once, so the first double press selects Scene 1. If configuring the helper in YAML, omit `initial` so later restarts restore the saved position. See [Number helper restore behavior](https://www.home-assistant.io/integrations/input_number/#restore-state).
3. Create an automation from the blueprint and select the button and **Scene position helper**.
4. Select **Scenes in cycle order** in the desired order. The saved list order determines scene numbers. To change the order, remove and re-add entries in order, or edit the automation's `scenes` list in YAML. Reset the helper to 0 if you want the next press to start from the new first scene.
5. Optionally configure **Press Action** and **Hold Action**, then save and enable the automation.

Use a separate helper for each scene-cycle automation. Keep it out of the scenes being cycled, and avoid changing it from other automations while a scene is being activated.

### Dropdown helper

1. Under **Settings > Devices & services > Helpers**, create a **Dropdown** helper. Enter the actual scene entity IDs as its options in cycle order, such as `scene.reading`, `scene.relax`, and `scene.bright`. Friendly names such as “Reading” cannot be used as scene targets.
2. Choose **Dropdown helper** as **Scene cycle source**, and select the helper in **Scene dropdown helper**. The blueprint's separate scene list and Number helper inputs are unused in this mode.
3. Select the **last option** once if you want the first double press to activate the first scene. The current selection is treated as the last selected scene, so a dropdown currently showing Scene 1 advances to Scene 2 on the next double press. A new dropdown normally starts with its first option selected.
4. Configure optional single-press and hold actions, then save and enable the automation.

The dropdown provides both the ordered list and the saved cycle position. Each double press activates the next option, then selects it in the dropdown after the scene service succeeds. After the last option, it wraps to the first. Options and selection are read when each queued press executes, so changes to the helper's list are picked up without editing the blueprint automation.

If configuring the dropdown in YAML, omit `initial` to restore its selection after restarts. See the official [Dropdown helper documentation](https://www.home-assistant.io/integrations/input_select/).

Changing the dropdown manually changes where the next double press continues; it does not activate a scene by itself. To restart at the first scene, select the last option. A stale selection outside the current option list starts again with the first option. A missing, unknown, unavailable, or empty dropdown stops the double-press run without falling back to Number helper mode. A missing or unavailable next scene, or a failed scene call, leaves the selection unchanged.

Use a dedicated dropdown, keep it out of the scenes being cycled, and avoid changing its selection or options during scene activation. If its options change after activation but before the selection is saved, the helper update can fail and leave its old selection in place.

## Settings

| Setting | Default | Details |
| --- | --- | --- |
| Button | Required | One supported SONOFF button paired through ZHA. |
| Scene cycle source | Scene list and Number helper | Choose a separate scene list and Number helper, or a Dropdown helper. |
| Scene dropdown helper | Empty | An `input_select` helper whose options are scene entity IDs; used only in Dropdown helper mode. |
| Scenes in cycle order | Empty | Scene entities in activation order; used only in Number helper mode. An empty list ignores double press. |
| Scene position helper | Empty | Required in Number helper mode: an available Number helper with minimum 0, maximum at least the scene count, and step 1. |
| Press Action | Empty | Optional single-press actions. |
| Hold Action | Empty | Optional hold actions. |

Single press and hold do not change the cycle position automatically. You can explicitly reset Number helper mode with `input_number.set_value` and value `0`, or reset Dropdown mode by selecting the last option with `input_select.select_last`. Empty gesture actions are ignored before entering the queue.

If your press or hold actions use templates that depend on variables created later in their sequence, put those actions in a separate script and configure the gesture to call that script. Gesture action templates are evaluated while checking whether the gesture has configured actions.

## Position and wraparound

This section describes **Scene list and Number helper** mode. Dropdown mode uses its selected option instead of a numeric position.

The helper stores the **last selected scene number**, starting at 1. **0** means no scene has been selected yet, or the cycle has been reset.

| Stored position before double press | Scene activated | New position |
| --- | --- | --- |
| 0 | Scene 1 | 1 |
| 1 | Scene 2 | 2 |
| 2 | Scene 3 | 3 |
| 3 | Scene 1 | 1 |
| 4, with only three scenes configured | Scene 1 | 1 |

Wraparound is based on the **number of configured scenes**, not the helper's maximum. There is no automatic intermediate reset to 0. Numeric positions outside the scene range, including fractional positions, start again at Scene 1. A helper that is missing, unknown, unavailable, or incorrectly configured stops the double-press run with a reason in the trace; single press and hold still work.

The position is read when the queued action executes. The scene is activated first, then the new position is saved. A missing/unavailable scene or a failed scene service call leaves the position unchanged so the next double press retries that scene. Scene service success does not confirm that every physical device reached its target state. If the helper write fails after scene activation, the scene may have changed while the stored position remains old; check the trace and helper availability.

Changes made outside this blueprint do not automatically synchronize the helper with the room's current appearance. The helper tracks this cycle's selection history.

## Queued gestures and restarts

Execution uses fixed **queued** mode so gestures run in arrival order and rapid double presses advance one scene at a time. The queue allows **10 active and waiting runs**. Further configured gestures are ignored with a warning. Long single-press or hold actions can delay queued scene changes. See [Home Assistant automation modes](https://www.home-assistant.io/docs/automation/modes/).

The selected helper's restored value determines the next scene after a restart. Pending gestures are not replayed after a Home Assistant restart or automation reload. An interruption between scene activation and the helper write can leave the old position saved.

## Verify and troubleshoot

Set the helper to 0 and double press four times with three scenes configured. Confirm the scene order is **1, 2, 3, 1** and the helper shows those same numbers. Set the helper's maximum to 4 and its value to 4; the next double press should activate Scene 1 and set the helper to 1.

For Dropdown mode, select the last scene option and double press four times. Confirm the scene order is **1, 2, 3, 1** and the dropdown follows each activated scene. Change the options list and verify the next double press follows the updated order.

Test single press and hold separately. If a gesture does nothing, listen to `zha_event` under **Developer tools > Events**, and confirm the selected device ID and command mapping. Check the automation trace for helper or scene validation failures and queue overflow warnings. The **Run actions** control has no gesture trigger ID and does not select a branch; test with the actual button.

The [automated checks](../tests/README.md) verify both modes, including wraparound, invalid positions, helper configuration, dynamic dropdown options, independent gestures, failed scene activation, queue behavior, and restart persistence through Home Assistant's native event and script engine.

## Credits

Uses the gesture mappings and ZHA device filters from this repository's [Sonoff Zigbee Button blueprint](../sonoff_zigbee_button/README.md), based on [apollo1220's reference](https://github.com/apollo1220/blueprints/blob/main/sonoff_zigbee_button.yaml).
