---
name: recipe-faded-tones
description: Gentle tonal correction recipe preserving highlight and shadow detail for photographs with compressed dynamic range or faded contrast.
---

# Recipe: Faded Tones

## 1. Recognition
- **Visual indicators**: Washed-out blacks, milky shadows, flat midtone contrast, or faded aged prints.
- **Measured clues**:
  - Minimum luminance well above 0 (e.g. minimum luminance > 25).
  - Maximum luminance below 240.
  - Histogram dynamic range compressed into midtones without clipping at ends.
  - Endpoint clipping clues from `artcraft_prepare_inspection` show 0.0% clipped shadows and 0.0% clipped highlights.

## 2. Operation
- **CLI Tool**: `photocraft-cli run <in> --cmd image.adjustments.levels --params <JSON> --out <out>`
- **Safe parameter bounds**:
  - `in_black`: 5 to 30 (default 12; maximum safe 50).
  - `in_white`: 225 to 250 (default 242; minimum safe 200).
  - `gamma`: 0.90 to 1.15 (default 1.05; safe range 0.7 to 1.5).
  - `out_black`: 0 (standard).
  - `out_white`: 255 (standard).
- **Alternative (LightCraft)**:
  `lightcraft-cli render <in> -o <out> --set light.contrast=15 --set light.shadows=-10 --set light.highlights=5`

## 3. Before/After Comparison
- **1:1 Native Crops**: Inspect deep shadow patches and bright cloud/cloth highlights. Verify texture and subtle gradations remain distinct without turning into solid flat blocks of black or white.
- **Print-Scale Crops**: Verify overall image contrast feels natural at intended viewing scale (e.g. 300 PPI) without excessive harshness.

## 4. Stop Conditions
- Stop and return `status: "needs_decision"` if:
  - Shadows are already clipped in the original and adjusting black point crushes remaining shadow details.
  - Requested `in_black > 50` or `in_white < 200`.
  - Contrast adjustment blows out existing highlight headroom.

## 5. Unsupported CLI Operations
- Monolithic one-button automatic dynamic range flattening that ignores existing intentional fog or lighting atmosphere.
- Destructive non-linear curve bends that crush delicate shadow detail.
