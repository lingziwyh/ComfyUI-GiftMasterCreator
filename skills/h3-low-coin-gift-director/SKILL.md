---
name: h3-low-coin-gift-director
description: Write production-ready English H3 prompts for single-play Douyin live gifts priced from 99 through 999 coins. Use when GiftMaster receives a low-coin gift name, price, creative direction, aspect ratio, and optional reference images in T2VA, I2VA, FL2VA, L2VA, or Ref2VA mode and must enforce the low-tier duration, single-shot, silence, background, reference, and price-effect rules.
---

# H3 Low-Coin Gift Director

Create one compact, readable live-gift animation. Preserve the user's named subject and requested action while keeping the result feasible for its price tier.

## Required workflow

1. Read [references/price-profile.json](references/price-profile.json) and apply the tier selected by the explicit gift price. Use 499 coins only when no price is available.
2. Read [references/format.md](references/format.md) and select the H3 mode from the assigned image role. Validate the image count before writing.
3. Extract the gift name, price, aspect ratio, creative request, reference role, and hard constraints. Reject an explicit price outside 99–999 instead of silently moving it into this range.
4. Preserve reference identity, subject count, silhouette, core materials, recognizable colors, prop direction, and any exact endpoint assigned by the task.
5. Design one continuous shot with one dominant motion idea. Use a short entrance, a readable presentation or action, and a clean exit or settling finish. When an exact first or last frame is assigned, the endpoint contract overrides a generic entrance or exit.
6. Express motion through observable subject actions, object state changes, or a simple spatial trajectory. Keep secondary effects subordinate to the gift object.
7. Write the final H3 prompt in the selected schema, then verify duration, aspect ratio, one-shot structure, silence, image labels, background behavior, and endpoint semantics.

## Non-negotiable rules

- Treat 99–299 coins as a 3-second product tier, implemented as 73 frames at 24 fps (about 3.04 seconds).
- Treat 300–999 coins as a 4-second product tier, implemented as 90 frames at 24 fps (3.75 seconds).
- Use exactly one `[Shot 1]`. Do not describe a cut, hidden cut, dissolve, or transition to another shot.
- Use one play only. Do not invent combo, loop, accumulation, multiplier, or repeated-trigger behavior.
- Use only `1:1` or `4:3`; default to `1:1`.
- Keep `overall_soundscape: N/A` and `non_diegetic_music: N/A`. Do not add dialogue, lyrics, speakers, or audio references.
- For 99–499 coins, use one uniform solid-color background and state positively that it remains unchanged for the entire video. Do not prescribe a hue or color value. Let the upstream image choice remain authoritative when a solid background already exists.
- For 500–999 coins, allow either a compact scene or a solid-color background. If solid color is used, keep it uniform and unchanged.
- Maintain stable identity, geometry, material continuity, clean framing, and deliberate camera motion at every price. Price limits content capacity, not production quality.

## Price-effect conflict handling

When the user or reference explicitly contains imagery that is richer than the normal tier capacity, preserve it and emit one concise Chinese warning before the H3 prompt. Simplify only inferred decoration or secondary action. Never replace or downgrade explicit content.

## Output

Return at most:

1. One Chinese price-effect warning when required.
2. One complete English H3 prompt without a Markdown fence.

Do not expose reasoning, alternatives, implementation markers, or a negative-prompt tail.
