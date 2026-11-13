---
name: photo-inspection
description: Recipe for visual photograph inspection using whole-photo previews, native crops, and measured clues before choosing restoration or print actions.
---

# Photograph Inspection Recipe

Never apply repairs blindly without inspecting the original photograph. Visual inspection identifies genuine defects, protects authentic scene features, evaluates print readiness, and establishes whether an edit is actually needed.

---

## 1. Prepare Inspection Artifacts

Call `artcraft_prepare_inspection` on the input image:

```json
{
  "path": "/path/to/source.png",
  "working_dir": "/path/to/job/inspection",
  "crop_size": 256
}
```

This non-destructive tool produces:
- **Whole-photo preview**: Bounded-size image for composition, overall balance, and scene layout.
- **Native-resolution crops (1:1 pixels)**: Center and corner crops (plus custom regions) without resampling, revealing fine details, grain, and micro-defects.
- **Dimensions & Orientation**: Exact width, height, orientation (`landscape`, `portrait`, `square`), and aspect ratio.
- **Color profile**: Embedded ICC profile name (e.g. sRGB, Display P3, Adobe RGB) or uncalibrated flag.
- **Effective print PPI**: Calculated PPI at standard print sizes (8×10, 11×14, 5×7, 4×6, 16×20), identifying whether cropping or enlargement is needed.
- **Measured clues**: Highlight/shadow clipping percentages, luminance dynamic range, sharpness score (Laplacian variance), and noise standard deviation, accompanied by explicit measurement limits.

---

## 2. Visual Inspection Protocol

Examine the whole-photo preview first, then inspect the 1:1 native crops across five key areas:

### 1. Faces and Skin (if present)
- Examine facial contours, eyes, lips, and skin texture.
- Look for localized blemishes, emulsion pits, scratches, or dust specks.
- Check whether skin texture is preserved or unnaturally smoothed.
- Distinguish authentic beauty marks, wrinkles, and freckles from foreign dust or scratches.

### 2. Lettering, Signs, and Fine Textures
- Check edge crispness and legibility on text, signs, fabric weave, or architectural patterns.
- Look for optical blur, motion smear, compression ringing, or scanning artifacts.

### 3. High-Contrast Edges
- Inspect boundaries between dark and light objects.
- Check for chromatic aberration (color fringing), optical flare, or halos from prior over-sharpening.
- Determine whether edge softness is scene-appropriate (optical depth of field) or scanning degradation.

### 4. Smooth Areas (Sky, Backdrops, Flat Surfaces)
- Smooth areas are prime locations for visible scratches, sensor dust specks, banding, and chemical stains.
- Inspect the grain structure: is it uniform and organic, or blotchy and digital?

### 5. Corners and Borders
- Check all four corners for lens vignetting (corner falloff), physical paper folds, emulsion chipping, tears, scanner bed borders, or adhesive tape marks.

---

## 3. Distinguishing Defects from Authentic Scene Features

Do not treat every line as a scratch or every high-frequency variation as noise:

| Feature | Authentic Feature (Leave Untouched) | Actionable Defect (Record for Repair) |
|---|---|---|
| **Linear marks** | Telegraph wires, tree branches, fabric seams, wrinkles, facial creases. Follow perspective and lighting logic. | Scratches: sharp, erratic or straight trajectories that cut across texture boundaries, often white or dark core with jagged emulsion edges. |
| **Texture & Grain** | Film grain: uniform, monochromatic or luminance-coherent, organic pattern that belongs to the medium. | Sensor noise, chromatic blotches, hot pixels, JPEG compression blocks, or scanner banding. |
| **High Highlights** | Specular catchlights in eyes, sun reflections, bright lamps, clean white backdrops, snow. | Blown-out highlights where expected gradations or textures (skin, clouds, fabric) are lost at 255. |
| **Deep Shadows** | Silhouettes, night scenes, dark suits, intentional chiaroscuro. | Crushed shadows where critical shadow detail is clipped at 0 due to underexposure or bad scan. |

---

## 4. Recording Suspected Issues

For every identified defect, record a structured entry with source-pixel coordinates and confidence:

```json
{
  "issue_type": "scratch",
  "location": [180, 240, 24, 85],
  "confidence": "high",
  "severity": "moderate",
  "description": "Hairline physical scratch cutting vertically across smooth sky background.",
  "recommended_action": "photocraft_spot_heal"
}
```

- **`issue_type`**: `scratch`, `dust_speck`, `crease`, `tear`, `color_cast`, `blown_highlights`, `crushed_shadows`, `sensor_noise`, `soft_focus`, or `vignetting`.
- **`location`**: `[x, y, width, height]` in source-pixel coordinates.
- **`confidence`**:
  - `high`: Unambiguous defect cutting across textures or abnormal pixel artifact.
  - `medium`: Likely defect, but adjacent to complex texture or structure.
  - `low`: Possible defect or possible authentic feature; requires human clarification.
- **`recommended_action`**: `leave_untouched`, `photocraft_spot_heal`, `tonal_correction`, or `clarify_with_user`.

---

## 5. Action vs. Stop Decisions

- **Clean photograph**: If no actionable defects are identified, **recommend leaving the photo untouched**. Unnecessary edits degrade original image authenticity and risk introducing artifacts.
- **Clear localized defect**: When confidence is high and defect is in an uncritical area (e.g., scratch across background or clothing), proceed with localized spot healing (`photocraft_spot_heal`).
- **Ambiguous or critical area**: If a defect crosses a person's eye, mouth, or important lettering, do not guess. Record the suspected issue with coordinates and flag for human clarification.
