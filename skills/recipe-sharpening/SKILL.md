---
name: recipe-sharpening
description: Restrained sharpening recipe avoiding distracting halos, ringing, and noise amplification for soft photographs.
---

# Recipe: Soft Photograph (Sharpening)

## 1. Recognition
- **Visual indicators**: Mild lens softness, slight motion blur, soft focus on subject, or scanning MTF loss where edge transitions lack crisp acutance.
- **Distinction**: Severe out-of-focus blur cannot be cured by sharpening without creating severe ringing artifacts.

## 2. Operation
- **CLI Tool**: `photocraft-cli run <in> --cmd filter.sharpen.unsharpMask --params <JSON> --out <out>`
- **Safe parameter bounds**:
  - `amount`: 30 to 80 (default 50; safe maximum 120).
  - `radius`: 0.6 to 1.5 (default 1.0; safe maximum 2.2).
  - `threshold`: 1 to 6 (default 2; threshold is vital to prevent sharpening smooth film grain or sky noise).
- **Alternative (LightCraft)**:
  `lightcraft-cli render <in> -o <out> --set detail.sharpenAmount=50 --set detail.sharpenRadius=1.0 --set detail.sharpenMasking=25`

## 3. Before/After Comparison
- **1:1 Native Crops**:
  - Inspect high-contrast edges (dark jacket against light wall, tree branches against sky, dark eyelashes against sclera).
  - Check for **halos**: Ensure there is no white outline, glowing fringe, or dark border along high-contrast transitions.
  - Inspect flat tones (skin, sky): Ensure smooth surfaces remain smooth and grain was not exaggerated into sandpaper.
- **Print-Scale Crops**: Confirm perceived sharpness increases naturally at the target print size.

## 4. Stop Conditions
- Stop and return `status: "needs_decision"` if:
  - Sharpening produces noticeable halos or fringing around edges.
  - The photograph is severely misfocused such that sharpening only emphasizes artifacts.
  - Requested `amount > 120` or `radius > 2.2`.

## 5. Unsupported CLI Operations
- High-pass convolution that adds glowing halos across subject contours.
- AI hallucination models that draw fictional sharp eyelashes or synthetic pupils into blurry faces.
