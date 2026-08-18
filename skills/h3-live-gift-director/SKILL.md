---
name: h3-live-gift-director
description: Write production-ready English H3 prompts for Douyin live gifts priced from 1000 through 3000 coins. Use when GiftMaster receives a gift name, price, duration, aspect ratio, shot preference, creative direction, audio request, and optional reference images in T2VA, I2VA, FL2VA, L2VA, or Ref2VA mode and must calibrate story scale, effects, camera work, continuity, and reference fidelity to the selected price tier.
---

# H3 Live Gift Director

Design a polished live-gift animation whose visible content capacity matches 1000–3000 coins. Keep identity, causality, camera control, and transitions production-ready at every price.

## Required workflow

1. Read [references/price-profile.json](references/price-profile.json). Apply the explicit price, duration, aspect ratio, and shot request. Use the documented defaults only for missing values.
2. Read [references/format.md](references/format.md). Select the H3 mode from the assigned image role and validate the image count before writing.
3. Reject an explicit price outside 1000–3000 instead of pretending to calibrate another range.
4. Inspect every reference for subject identity, count, silhouette, structure, materials, palette, props, environment, composition, and motion affordances. Preserve the identity and structural anchors before secondary decoration.
5. Choose one main subject, one immediate hook, one causal progression, and one memorable moving climax unless the user explicitly requests an ensemble or a different story.
6. Add visual effects only when they support the supplied design or an indispensable story mechanism. Prefer physical reactions such as fabric, water, foliage, wheels, doors, weather, or practical light.
7. Give each requested shot a distinct visual job. Connect multiple shots through a physically motivated action, occlusion, direction, shape, or environment bridge unless a literal hard cut is requested.
8. Keep exact first- and last-frame assignments authoritative. Ref2VA references guide appearance and composition but do not become endpoints unless the task says so.
9. Write the final H3 prompt, then verify price capacity, timing, shot count, image labels, continuity, audio fields, and ending motion.

## Price-effect policy

- Price changes the amount of visible story, spatial reveal, coordinated response, and effect layering; it never licenses unstable subjects, rough camera work, accidental transitions, or weak composition.
- Keep inferred content within a compact-to-medium gift scale. Do not invent civilization-scale worlds, prestige adult mythical beasts, extensive jewel systems, or prolonged full-frame effect storms merely to make the result feel expensive.
- When the user or reference explicitly contains content above the usual range, preserve it and emit one concise Chinese warning before the H3 prompt. Simplify only inferred secondary material.
- Prefer one or two shots. Use three only when the user requests it or the upper tier has three necessary, visually distinct stages.
- Make the closing moment a readable moving cover, not an inert pause, except where an exact last-frame contract requires convergence to a specific image.

## Defaults for missing information

- Price: 2000 coins.
- Duration: 5 seconds.
- Aspect ratio: `1:1`.
- Structure: one continuous shot or two purposeful shots.
- Single unassigned image: Ref2VA.
- Audio: `overall_soundscape: N/A` and `non_diegetic_music: N/A`.

Respect explicit coherent duration, shot count, audio, image role, and story instructions instead of replacing them with defaults.

## Output

Return at most:

1. One Chinese price-effect warning when required.
2. One complete English H3 prompt without a Markdown fence.

Do not expose reasoning, alternative concepts, implementation markers, or a negative-prompt tail.
