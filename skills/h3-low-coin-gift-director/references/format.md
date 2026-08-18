# GiftMaster H3 prompt format

Use this compact schema for GiftMaster output. Write the field contents in English. Preserve user-supplied visible text in its original language.

## Mode and image contract

| Mode | Images | Meaning |
| --- | ---: | --- |
| T2VA | 0 | Build the full shot from text. |
| I2VA | 1 | Picture 1 is the exact frame at 0.00 seconds. |
| FL2VA | 2 | Picture 1 is the exact first frame and Picture 2 is the exact last frame. |
| L2VA | 1 | Picture 1 is the exact last frame. |
| Ref2VA | 1–9 | Pictures guide identity, objects, materials, style, composition, or background without becoming exact endpoints. |

Do not reinterpret a contact sheet, storyboard, or multi-frame collage as one exact endpoint.

## Base-mode fields

T2VA, I2VA, FL2VA, and L2VA use these fields once and in this order:

```text
integrated_multimodal_description:
overall_soundscape:
non_diegetic_music:
```

Place `[Shot 1]` at the beginning of the description. The low-coin profile permits no other shot marker. State the requested aspect ratio and describe the motion as one continuous camera-and-subject event.

- T2VA begins directly with the three fields.
- I2VA places one short English alignment statement before the fields, assigning Picture 1 to 0.00 seconds.
- FL2VA places one short English alignment statement before the fields, assigning Picture 1 to 0.00 seconds and Picture 2 to the exact ending time.
- L2VA places one short English alignment statement before the fields, assigning Picture 1 to the exact ending time.

For an exact endpoint, describe a physically continuous path into or out of that frame. Do not add an entrance or exit that contradicts the assigned endpoint.

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

Define every connected image as `<Picture N>` and every reusable visible subject as `<Subject N>`. Use the same labels in all sections. Do not create `<Video N>` or `<Audio N>` labels. Begin `detailed_description` with `[Shot 1]`.

Begin `summary` with one applicable task type in square brackets. For image-guided gift creation, use `[reference generation]`.

Put each definition on its own line, for example `<Picture 1>: ...` and `<Subject 1>: ...`. In `retention_analysis`, give every defined label exactly one relationship line using one of these visual relationships: `fully_preserved`, `partially_preserved`, `attribute_transfer`, or `weak_reference`.

## Shared checks

- Use `N/A` as the complete value of both audio fields.
- Do not use `<d>` dialogue tags or speaker IDs.
- Keep all timing inside the requested effective duration.
- Describe desired visible states positively.
- Do not add `--wm false`, a negative-prompt block, explanations, or Markdown fences around the final answer.
