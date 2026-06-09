# Changes from Upstream sdaps for Pull Request

This document describes all modifications made to the sdaps codebase relative to
the upstream repository (starting from release 1.9.13). Changes are grouped by
area and ordered from simplest to most complex.

---

## 1. Corner Mark Line Width (PDF generation + scan recognition)

**Problem:** The default 1bp corner marks were too thin to be reliably printed
and detected after scanning, particularly with lower-quality printer/scanner
combinations.

**Files changed:**

### `tex/class/sdapsbase.dtx`
```diff
-\dim_gset:Nn \g_sdaps_edge_marker_linewidth_dim { 1bp }
+\dim_gset:Nn \g_sdaps_edge_marker_linewidth_dim { 3bp }
```

### `sdaps/defs.py`
```diff
-# All lines are 1pt wide(1/72 inch or 25.4/72 mm)
-image_line_width = 24.4/72. # mm
+# All lines are 3bp wide(3/72 inch or 3*25.4/72 mm)
+image_line_width = 3*25.4/72. # mm
```
The scan recognition threshold (`image_line_width`) must match the PDF line
width so that the C corner-marker detector uses the correct expected stroke width.

---

## 2. Barcode Text Label Position (PDF generation)

**Problem:** The human-readable text label printed beneath each barcode falls in
the non-printable margin zone on many printers, causing the label to be clipped
or invisible on stamped questionnaires.

**Fix:** Move the label from below the barcode to above it. Applied to all three
barcode nodes (questionnaire ID, survey ID, global ID).

### `tex/class/sdapsbase.dtx` — three identical changes
```diff
-\node[below=1mm~of~barcode,distance=0,anchor=north,outer~sep=0,inner~sep=0]{
+\node[above=1mm~of~barcode,distance=0,anchor=south,outer~sep=0,inner~sep=0]{
```

---

## 3. Fix Type 3 Bitmap Fonts in Printed PDFs

**Problem:** When `pdflatex` cannot find Type 1 outlines for Computer Modern
fonts (e.g. `\ttfamily` used in barcode labels), it falls back to Type 3 PK
bitmap fonts. Many printer drivers and PDF viewers cannot render these, causing
text to appear invisible when printed.

**Fix:** Load `lmodern`, which provides T1-encoded Type 1 outlines for all CM
fonts, before any other font-related packages.

### `tex/class/sdapsclassic.dtx`
```diff
 \RequirePackage[T1]{fontenc}
+\RequirePackage{lmodern}
```

---

## 4. Handwriting OCR for Textboxes

**Problem:** The `Textbox` element detected whether something was written but
did not attempt to read the written content. The `data.text` field was never
populated during recognition.

**Approach:** After the existing bounding-box detection, crop each textbox from
the scanned image, segment individual characters using connected-component
analysis, and run each character crop through Microsoft's TrOCR handwriting
model (`microsoft/trocr-base-handwritten`).

**Key design decisions:**
- Uses the matrix coordinate transform (`matrix.transform_point`) to locate the
  textbox in pixel space — this places the crop precisely inside the box,
  already past any printed field label (e.g. "ID:").
- A 5% horizontal / 15% vertical inset is applied to the crop to eliminate any
  remaining box border lines, without needing morphological line-removal (which
  was found to destroy thin character strokes).
- Blob segmentation uses `scipy.ndimage.label` on the bilevel (threshold < 128)
  image. Size filters remove noise and border fragments.
- Each blob is passed to TrOCR as a **raw bounding box crop** (not a clean
  masked image). TrOCR needs surrounding pixel context to distinguish ambiguous
  characters — e.g. a handwritten "9" with a curved tail reads as "y" without
  context, but correctly as "9" with it.
- TrOCR is lazy-loaded on first use and cached for the duration of the process.
- The model (~350 MB) is downloaded from HuggingFace Hub on first run and
  cached in `~/.cache/huggingface/hub`.

**Dependencies added:** `transformers`, `scipy`, `numpy`, `Pillow`

**Files changed:**

### `sdaps/recognize/buddies.py`

Added at module level:
```python
import os
import tempfile

_trocr_processor = None
_trocr_model = None

def _get_trocr():
    global _trocr_processor, _trocr_model
    if _trocr_processor is None:
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel
        _trocr_processor = TrOCRProcessor.from_pretrained('microsoft/trocr-base-handwritten')
        _trocr_model = VisionEncoderDecoderModel.from_pretrained('microsoft/trocr-base-handwritten')
    return _trocr_processor, _trocr_model
```

Added inside `Textbox.recognize()`, after the existing bounding-box detection
block, to populate `self.obj.data.text`:
```python
try:
    import numpy as np
    from scipy import ndimage as _ndimage
    from PIL import Image as _PILImage

    px0, py0 = matrix.transform_point(self.obj.x, self.obj.y)
    px1, py1 = matrix.transform_point(
        self.obj.x + self.obj.width,
        self.obj.y + self.obj.height)
    px = int(min(px0, px1)); py = int(min(py0, py1))
    pw = int(abs(px1 - px0)); ph = int(abs(py1 - py0))

    if pw > 0 and ph > 0:
        # Render the 1-bit surface to a grayscale array
        rgb_surf = cairo.ImageSurface(cairo.FORMAT_RGB24, pw, ph)
        cr_ocr = cairo.Context(rgb_surf)
        cr_ocr.set_source_rgb(1, 1, 1); cr_ocr.paint()
        cr_ocr.set_source_rgba(0, 0, 0, 1)
        cr_ocr.mask_surface(surface, -px, -py)
        rgb_surf.flush()
        tmp = tempfile.mktemp(suffix='.png', prefix='sdaps-ocr-')
        rgb_surf.write_to_png(tmp)
        del cr_ocr, rgb_surf
        gray = np.array(_PILImage.open(tmp).convert('L'))
        os.unlink(tmp)

        ah, aw = gray.shape
        if ah > 0 and aw > 0:
            ix = max(3, int(aw * 0.05)); iy = max(3, int(ah * 0.15))
            inner = gray[iy:ah-iy, ix:aw-ix]
            ih, iw = inner.shape
            binary = inner < 128

            labeled, n_blobs = _ndimage.label(binary)
            min_h = max(5, int(ih * 0.25)); min_w = max(3, int(iw * 0.03))
            blobs = []
            for blob_i in range(1, n_blobs + 1):
                rows, cols = np.where(labeled == blob_i)
                y0b, y1b = rows.min(), rows.max()
                x0b, x1b = cols.min(), cols.max()
                bh = y1b - y0b + 1; bw = x1b - x0b + 1
                if (labeled == blob_i).sum() < 50: continue
                if bw > iw * 0.8: continue
                if bh < min_h: continue
                if bw < min_w: continue
                blobs.append((blob_i, x0b, y0b, x1b, y1b))

            if blobs:
                blobs.sort(key=lambda b: b[1])
                trocr_processor, trocr_model = _get_trocr()
                pad = 8
                chars = []
                for blob_i, x0b, y0b, x1b, y1b in blobs:
                    cx0 = max(0, x0b-pad); cy0 = max(0, y0b-pad)
                    cx1 = min(iw, x1b+pad); cy1 = min(ih, y1b+pad)
                    raw = inner[cy0:cy1, cx0:cx1]
                    ch, cw = raw.shape
                    crop_pil = _PILImage.fromarray(raw).resize(
                        (cw*4, ch*4), _PILImage.LANCZOS).convert('RGB')
                    try:
                        pixel_values = trocr_processor(
                            images=crop_pil, return_tensors='pt').pixel_values
                        generated_ids = trocr_model.generate(pixel_values)
                        text = trocr_processor.batch_decode(
                            generated_ids, skip_special_tokens=True)[0]
                        if text:
                            chars.append(text)
                    except Exception:
                        pass
                if chars:
                    self.obj.data.text = ''.join(chars)
except Exception as e:
    log.warn(_('OCR failed for textbox: %s') % str(e))
```

---

## 5. Grayscale Companion TIFF During Conversion (infrastructure)

**Background:** During `sdaps add --convert`, the input image is converted to a
1-bit monochrome TIFF. The original grayscale information is discarded. This
change preserves a grayscale copy alongside each monochrome TIFF, named
`N_gray.tif`, for potential use by downstream processing steps (e.g. OCR).

Note: The TrOCR OCR implementation above uses the bilevel surface rendering
for blob segmentation rather than this grayscale companion. The infrastructure
is included for completeness and future use.

### `sdaps/convert/__init__.py`
Added `gray_outfile` parameter. When provided, saves a grayscale multi-page
TIFF with LZW compression alongside the monochrome output.

### `sdaps/cmdline/add.py`
Creates a temporary grayscale file path when `--convert` is used, passes it
through to `convert_images()` and `add_image()`.

### `sdaps/add/__init__.py`
Added `gray_file` parameter to `add_image()`. When present, copies the
grayscale companion into the survey directory as `N_gray.tif`.

---

## Files NOT to include in the PR

The following are local test artifacts and should be excluded:

- `JASONtest/` — local test survey directory with scanned PDFs and generated data
- `JasonTest.txt` — local scratch file
- Any `data_N.csv` files — recognition output from test runs
