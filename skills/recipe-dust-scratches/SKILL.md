---
name: recipe-dust-scratches
description: Localized healing recipe preserving nearby edges and authentic texture for dust speckles, hairs, and scratches.
---

# Recipe: Dust and Scratches

## 1. Recognition
- **Visual indicators**: High-contrast, sharp-edged isolated blemishes such as dust specks, white hairs, dark negative scratches, or emulsion scuffs.
- **Distinction**: Distinguish between accidental damage and real scene details:
  - Scratches cross multiple natural texture boundaries in unnatural straight or curved lines.
  - Wrinkles, fabric seams, whiskers, wire fences, and background twigs follow scene geometry. Do NOT heal real scene features!

## 2. Operation
- **Localized Spot Healing (Preferred)**:
  Use `photocraft_spot_heal` or `artcraft_restore_step(recipe="dust_and_scratches", parameters={"points": [...], "size": brush_size}, region=[x, y, w, h])`.
  - Coordinates must tightly target the defect.
  - Brush `size`: 1 to 2x defect width (typical: 4 to 24 px).
  - Non-destructive post-edit check enforces **zero changed pixels outside the target region**.
- **Filter-based Dust & Scratches (Area approach)**:
  `photocraft-cli run <in> --cmd filter.noise.dustAndScratches --params '{"radius": 1, "threshold": 15}' --out <out>`
  - `radius`: 1 to 2 (safe maximum: 3).
  - `threshold`: 10 to 40 (threshold ensures subtle grain and edges are not blurred).

## 3. Before/After Comparison
- **1:1 Native Crops**: Inspect the repaired defect and immediately adjacent textures (hair strands, fabric weave, brick pattern).
- Verify:
  - Defect is removed seamlessly without smudging or blurry "mush".
  - Surrounding grain and edge sharpness match neighboring undamaged areas.
- **Print-Scale Crops**: Confirm the repair is invisible at normal viewing distance.

## 4. Stop Conditions
- Stop and return `status: "needs_decision"` if:
  - The defect covers or crosses key facial anatomy (eyes, pupils, lips, teeth) or fine lettering. Healing across missing facial features requires explicit operator decision.
  - The damaged area is too large for content-aware patch blending without hallucinating content.

## 5. Unsupported CLI Operations
- Generative AI diffusion inpainting to reconstruct destroyed eyes, smiles, or missing person details.
- Monolithic full-image blurring filters that obliterate authentic film grain across the whole picture.
