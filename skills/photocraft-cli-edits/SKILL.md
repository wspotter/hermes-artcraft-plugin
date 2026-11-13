---
name: photocraft-cli-edits
description: Recipe for running non-destructive PhotoCraft CLI edits with automatic pixel-diff verification.
---

# PhotoCraft CLI Edits

1. View the source and inspect a native-resolution crop of the blemish. Use `artcraft_inspect` for source dimensions.
2. Call `photocraft_spot_heal` with the source, a new PNG path, stroke points in source pixels, brush size, and an allowed region `[x, y, width, height]` that covers the brush edges.
3. If verification fails, inspect the error and the source crop before changing the stroke. A successful receipt confirms the edit stayed inside the allowed region. View the same crop after healing to check texture and nearby edges before delivery.
