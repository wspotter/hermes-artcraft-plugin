---
name: print-preparation
description: Recipe for preparing print-ready files at exact dimensions and PPI with aspect ratio validation, clarification gates, color-profile preservation, and delivery file verification.
---

# Print Preparation Recipe

Preparing a photograph for physical printing requires turning an agreed request into an exact, correctly dimensioned, color-managed delivery file. Proportions must be strictly preserved, aspect ratio conflicts must be resolved before cropping, and the resulting file must be verified by decoding it directly from disk.

---

## 1. Parameters and Calculation

Every print preparation requires:
- **Physical dimensions**: `width_in` and `height_in` in inches (e.g., 8×10, 11×14, 5×7).
- **Target resolution**: `ppi` (default 300 PPI for archival and fine-art printing).
- **Orientation**: `auto` (aligns image long side with sheet long side), `portrait`, or `landscape`.
- **Fit mode**:
  - `borderless` / `crop`: Fills the entire paper with no white borders.
  - `margins` / `fit`: Preserves the complete photograph without cropping, centering it with margins (`margin_color`, default white).
- **Output format**: `PNG`, `TIFF`, or `JPEG` (default inferred from file extension).

Target pixel dimensions are calculated as:
$$\text{width\_px} = \text{round}(\text{width\_in} \times \text{ppi})$$
$$\text{height\_px} = \text{round}(\text{height\_in} \times \text{ppi})$$

---

## 2. The Clarification Gate

When the source aspect ratio does not match the target print sheet ratio:

1. **If `fit_mode="margins"` / `"fit"` is requested**:
   The user explicitly requested full-picture preservation with margins. Proceed without clarification.

2. **If `fit_mode="borderless"` / `"crop"` or `"auto"` is requested without `confirm_crop=True`**:
   **STOP** immediately without writing any output file. Return `status: "needs_clarification"` with the exact parameterized question:
   > *"Should the photo fill the [sheet] sheet with a [target_ratio] crop, or keep the [source_ratio] crop and add margins?"*
   >
   > *(Example: "Should the photo fill the 8×10 sheet with a 4:5 crop, or keep the 3:4 crop and add margins?")*

3. **Wait for confirmation**:
   Only proceed with borderless cropping when `confirm_crop=True` is explicitly passed.

---

## 3. Strict Proportion & Resolution Governance

- **Never stretch or distort**: The pixel aspect ratio must remain 1:1. Resizing must use high-quality Lanczos resampling.
- **Separate effective source resolution from export resolution**:
  - `effective_source_ppi`: Measures the physical pixel density of the source data across the printed sheet.
  - `export_ppi`: The metadata PPI and physical dimensions written to the deliverable file.
- **Low-resolution warning**: When source pixels are smaller than target print pixels (`effective_source_ppi < ppi`), emit a clear warning. If `allow_upscale=False`, stop and require explicit permission before upscaling.

---

## 4. Color Profiles & Master Copy Preservation

- **Color profiles**: Retain embedded ICC color profiles (e.g., sRGB, Adobe RGB, Display P3) through to the export file. If a target ICC profile is specified, apply or embed it cleanly.
- **Master copy**: When `preserve_master_path` is specified, preserve an untouched copy of the original input file and verify its SHA-256 checksum before performing export edits.

---

## 5. Delivery File Verification

Every prepared print file must be verified by reopening and decoding:
1. Reopen the output file from disk and fully decode its raster data.
2. Confirm that decoded dimensions match target width and height in pixels.
3. Confirm that format matches requested format.
4. Confirm DPI metadata matches requested export PPI.
5. Confirm embedded ICC profile presence.
6. Generate a visual composition preview (`max_preview_dimension: 1024`) for visual review before publishing.

---

## 6. Tool & CLI Usage

### Hermes Tool
```json
{
  "name": "artcraft_prepare_print",
  "arguments": {
    "input_path": "/path/to/source.png",
    "output_path": "/path/to/export/print_8x10.png",
    "width_in": 8.0,
    "height_in": 10.0,
    "ppi": 300,
    "fit_mode": "margins",
    "margin_color": "white",
    "preserve_master_path": "/path/to/archive/source_master.png"
  }
}
```

### CLI Subcommand
```bash
# Print preparation with margins
hermes artcraft prep-print source.png print_8x10.png --width 8.0 --height 10.0 --fit-mode margins --ppi 300

# Borderless with confirmed crop
hermes artcraft prep-print source.png print_8x10.png --width 8.0 --height 10.0 --fit-mode borderless --confirm-crop --ppi 300
```
