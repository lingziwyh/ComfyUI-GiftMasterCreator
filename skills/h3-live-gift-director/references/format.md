# GiftMaster H3 prompt format

Write H3 field contents in English. Preserve user-supplied dialogue, lyrics, and visible text in their original language.

## Mode and image contract

| Mode | Images | Meaning |
| --- | ---: | --- |
| T2VA | 0 | Build the complete audiovisual timeline from text. |
| I2VA | 1 | Picture 1 is the exact frame at 0.00 seconds. |
| FL2VA | 2 | Picture 1 is the exact first frame and Picture 2 is the exact last frame. |
| L2VA | 1 | Picture 1 is the exact last frame. |
| Ref2VA | 1–9 | Pictures guide identity, objects, materials, scene, style, or composition without becoming exact endpoints. |

Do not infer an endpoint from a polished cover image. Use an endpoint mode only when the task explicitly assigns that role.

## Base-mode fields

T2VA, I2VA, FL2VA, and L2VA use these fields once and in this order:

```text
integrated_multimodal_description:
overall_soundscape:
non_diegetic_music:
```

- T2VA begins directly with the fields.
- I2VA adds one short English alignment statement before the fields, assigning Picture 1 to 0.00 seconds.
- FL2VA adds one short English alignment statement before the fields, assigning Picture 1 to 0.00 seconds and Picture 2 to the exact ending time.
- L2VA adds one short English alignment statement before the fields, assigning Picture 1 to the exact ending time.

Begin the description with `[Shot 1]`. For later shots, use `[Shot N] At MM:SS.mmm`, with continuous numbering and strictly increasing cut times below the total duration. Describe composition, subject action, environment response, camera behavior, and the physical bridge at each boundary.

## Ref2VA fields

Ref2VA uses these fields once and in this order:

```text
subject_definitions:
summary:
retention_analysis:
detailed_description:
overall_soundscape:
non_diegetic_music:
```

Define each connected image as `<Picture N>` and each reusable visible subject as `<Subject N>`. Keep every label consistent across the six sections. Do not define a video or audio asset that the workflow did not supply.

Begin `summary` with one applicable task type in square brackets. For image-guided gift creation, use `[reference generation]`.

Put each definition on its own line, for example `<Picture 1>: ...` and `<Subject 1>: ...`. In `retention_analysis`, give each defined visual label exactly one relationship line using `fully_preserved`, `partially_preserved`, `attribute_transfer`, or `weak_reference`. Begin `detailed_description` with `[Shot 1]` and use the same later-shot timing syntax as base mode.

## Audio and text

- When no audio is requested, use `N/A` as the complete value of both audio fields.
- When only music is requested, leave `overall_soundscape` as `N/A`.
- When only physical sound is requested, leave `non_diegetic_music` as `N/A`.
- If dialogue is requested, wrap each utterance in one `<d>...</d>` block and begin the block with its language in square brackets.

## Shared checks

- Keep timing inside the requested duration.
- Keep exact image endpoints visually attainable and temporally precise.
- Describe desired states positively.
- Do not add unresolved labels, `--wm false`, a negative-prompt block, explanations, or Markdown fences around the final answer.
