---
name: recipe-color-cast
description: Neutral-balance and color correction recipe preserving believable skin tones and intentional warmth.
---

# Recipe: Color Cast

## 1. Recognition
- **Visual indicators**: Overall unnatural tint covering the entire photograph (e.g. yellow aged paper, green tungsten/fluorescent cast, or cyan fading).
- **Distinction**: Distinguish between an unwanted technical color cast and intentional warm golden-hour atmosphere, sunset hues, or deliberate sepia styling.
- **Measured clues**: Neutral gray elements (concrete, white collars, neutral backgrounds) show significant chromatic imbalance between red, green, and blue channels.

## 2. Operation
- **CLI Tool**: `photocraft-cli run <in> --cmd image.adjustments.colorBalance --params <JSON> --out <out>`
- **Safe parameter bounds**:
  - `midtones`: `[cyan_red, magenta_green, yellow_blue]` where each is in range -25 to +25 (default for yellow aged cast: `[0, 0, 15]`). Maximum safe absolute shift: 45.
  - `preserveLuminosity`: `true` (strictly required to prevent darkening or blowing tones).
  - `shadows` and `highlights`: `[0, 0, 0]` unless subtle counter-balance is needed (-15 to +15).
- **Alternative (LightCraft)**:
  `lightcraft-cli render <in> -o <out> --set wb.temp=6500 --set wb.tint=0`

## 3. Before/After Comparison
- **1:1 Native Crops**: Inspect skin tones (cheeks, hands, faces). Ensure skin retains natural pink/peach warmth and does not turn chalky gray, greenish, or purplish.
- **Neutral Reference**: Inspect known neutral elements (white shirts, gray roads) to ensure they look neutral.
- **Print-Scale Crops**: Verify overall color harmony at simulated print PPI.

## 4. Stop Conditions
- Stop and return `status: "needs_decision"` if:
  - Extreme channel shift (> 45) is requested.
  - Skin tones begin shifting into unnatural purple or cyan tones.
  - The photo appears to have an intentional artistic toning or sepia bath that the requester might want to preserve.

## 5. Unsupported CLI Operations
- Automatic color replacement that re-paints arbitrary colors without respect to lighting.
- Extreme hue shifts that destroy believable human skin tones.
