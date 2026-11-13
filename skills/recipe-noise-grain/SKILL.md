---
name: recipe-noise-grain
description: Modest selective noise reduction recipe retaining facial detail, lettering, and authentic photographic texture.
---

# Recipe: Noise and Grain

## 1. Recognition
- **Visual indicators**: High-frequency speckling, digital sensor chroma noise (red/blue pixel blotches), or harsh scanning grain in smooth tonal areas (skies, flat walls, out-of-focus backgrounds).
- **Distinction**: Distinguish between ugly electronic sensor noise and authentic, desirable film grain that gives character and sharp perceptual acuity to vintage photographs.

## 2. Operation
- **CLI Tool**: `photocraft-cli run <in> --cmd filter.noise.reduceNoise --params <JSON> --out <out>`
- **Safe parameter bounds**:
  - `strength`: 2 to 6 (default 4; maximum safe 8).
  - `preserveDetails`: 50 to 85 (default 70; minimum safe 35).
  - `reduceColorNoise`: 25 to 65 (default 45).
  - `sharpenDetails`: 10 to 25 (default 15).
  - `removeJpegArtifact`: `false` (set `true` only for blocky JPEG compression artifacts).
- **Alternative (LightCraft)**:
  `lightcraft-cli render <in> -o <out> --set detail.nrLuminance=25 --set detail.nrColor=40 --set detail.nrDetail=60`

## 3. Before/After Comparison
- **1:1 Native Crops**:
  - Inspect smooth areas: Verify chroma noise and harsh speckling are calmed.
  - Inspect detail areas (eyes, eyelashes, fabric texture, lettering, signs): Verify edge acuity and fine structures are **strictly retained** and not plasticized into waxy skin.
- **Print-Scale Crops**: Verify the image does not look artificially smudged or airbrushed at print resolution.

## 4. Stop Conditions
- Stop and return `status: "needs_decision"` if:
  - Applying noise reduction causes fine lettering or facial features to blur or dissolve.
  - Requested parameters would wipe out texture (`strength > 8` and `preserveDetails < 35`).

## 5. Unsupported CLI Operations
- Aggressive AI face "enhancement" models that replace genuine human skin texture with synthetic cartoonish porcelain skin.
- Heavy bilateral blurring that destroys genuine lens bokeh and depth of field.
