---
name: recipe-enlargement
description: Proportional upscaling and restrained output sharpening recipe preserving composition and fine details for print preparation.
---

# Recipe: Enlargement

## 1. Recognition
- **Visual indicators**: A photograph has too few native pixels to print at high resolution (e.g. 300 PPI) at the desired physical sheet dimensions (e.g. an 800x1000 px photo targeted for an 8x10 inch print).
- **Measurement**: Effective source resolution (`effective_source_ppi = min(w / width_in, h / height_in)`) is below target print PPI (e.g. 100 PPI instead of 300 PPI).

## 2. Operation
- **CLI Tool (Chained PhotoCraft)**:
  Resamples pixels proportionally using detail-preserving interpolation and applies matched output sharpening:
  ```bash
  photocraft-cli run <in> \
    --cmd image.imageSize --params '{"width": 2400, "height": 3000, "resample": "preserveDetails"}' \
    --cmd filter.sharpen.unsharpMask --params '{"amount": 40, "radius": 0.8, "threshold": 1}' \
    --out <out>
  ```
- **Safe parameter bounds**:
  - `scale`: 1.1x to 3.0x (safe maximum: 4.0x).
  - `resample`: `"preserveDetails"` (preferred for photographs) or `"bicubicSmoother"`.
  - Output sharpening `amount`: 30 to 50; `radius`: 0.6 to 1.0; `threshold`: 1.
- **Composition preservation**:
  Aspect ratio MUST be strictly preserved. Never stretch or distort non-uniformly (`width` and `height` must maintain source ratio within 0.1%).

## 3. Before/After Comparison
- **1:1 Native Crops**: Inspect fine line details (eyebrows, fabric threads, sign edges). Verify edges remain smooth without jagged stair-stepping or pixel blockiness.
- **Print-Scale Crops**: Compare a 1-inch print crop (e.g. 300x300 px) from before (scaled up) and after to evaluate print fidelity and sharpness.

## 4. Stop Conditions
- Stop and return `status: "needs_decision"` if:
  - Enlargement factor exceeds 4.0x. Scaling beyond 4x without specialized human guidance results in severe blur or muddy artifacts.
  - The request would alter aspect ratio or crop content unexpectedly.

## 5. Unsupported CLI Operations
- Generative super-resolution models that hallucinate fictional skin pores, synthetic teeth, or imaginary text into low-resolution source files.
- Non-proportional stretching.
