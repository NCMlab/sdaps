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

            # Save the crop for the OCR training-data export (see section 5)
            training_dir = self.obj.sheet.survey.path('ocr_training')
            os.makedirs(training_dir, exist_ok=True)
            image_filename = os.path.join('ocr_training',
                '%i_%s.png' % (self.obj.sheet._rowid, self.obj.id_csv()))
            _PILImage.fromarray(inner).save(self.obj.sheet.survey.path(image_filename))
            self.obj.data.ocr_image = image_filename

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

## 5. OCR Training-Data Capture and Export

**Problem:** The TrOCR model (section 4) does not generalize perfectly to
every handwriting style — on a second test scan, recognition was poor enough
that a human needs to review and correct the text via `sdaps gui`. Those
corrections are valuable: paired with the image crop that was fed to the OCR
model, they form exactly the kind of (image, text) data needed to fine-tune
TrOCR on this project's handwriting in the future.

**Approach:** Every time `Textbox.recognize()` detects writing, it now saves
the same grayscale crop that is used for OCR (the `inner` array, after the
border inset, before binarization) to `<project>/ocr_training/<sheet_rowid>_
<field>.png`, and records that path on `data.ocr_image`. The OCR's guess is
still stored in `data.text` as before, and `sdaps gui` lets a human correct
it. A new export command, `sdaps export ocr-training`, then walks all
sheets and, for every textbox with both `data.ocr_image` and a non-empty
`data.text`, copies the crop into an `images/` directory and writes a
`manifest.csv` row of `(image, text, questionnaire_id, field)`. The `-f`
filter option (e.g. `-f "verified"`) can restrict the export to sheets that
have actually been reviewed by a human, so the dataset only contains
human-confirmed labels.

**Files changed:**

### `sdaps/model/data.py`
Added an `ocr_image` attribute (default `None`) to the `Textbox` data class,
holding the survey-relative path to the saved crop.

### `sdaps/recognize/buddies.py`
Inside `Textbox.recognize()`, right after computing `inner`/`ih, iw` (see the
updated snippet in section 4 above), saves `inner` as a PNG under
`ocr_training/` and sets `self.obj.data.ocr_image` to its relative path.

### `sdaps/ocrtraining.py` (new file)
```python
def export(survey, output_dir, filter=None):
    filter = clifilter.clifilter(survey, filter)

    images_dir = os.path.join(output_dir, 'images')
    os.makedirs(images_dir, exist_ok=True)

    manifest = open(os.path.join(output_dir, 'manifest.csv'), 'w', encoding='utf-8', newline='')
    writer = csv.DictWriter(manifest, ['image', 'text', 'questionnaire_id', 'field'])
    writer.writeheader()

    count = [0]

    def export_sheet():
        sheet = survey.sheet
        for qobject in survey.questionnaire.qobjects:
            if not hasattr(qobject, 'boxes'):
                continue
            for box in qobject.boxes:
                if not isinstance(box, model.questionnaire.Textbox):
                    continue
                if not box.data.ocr_image or not box.data.text:
                    continue

                src = survey.path(box.data.ocr_image)
                if not os.path.exists(src):
                    continue

                dest_name = '%s_%s.png' % (_sanitize(sheet.questionnaire_id), box.id_csv())
                shutil.copy(src, os.path.join(images_dir, dest_name))

                writer.writerow({
                    'image': os.path.join('images', dest_name),
                    'text': box.data.text,
                    'questionnaire_id': sheet.questionnaire_id,
                    'field': box.id_csv(),
                })
                count[0] += 1

    survey.iterate(export_sheet, filter)

    manifest.close()

    return count[0]
```

### `sdaps/cmdline/ocrtraining.py` (new file)
Registers `export ocr-training` as a new `export` subcommand, with `-o/--output`
(default `<project>/ocr_training_export`) and `-f/--filter` options, following
the same pattern as `export csv` / `export feather`.

### `sdaps/cmdline/__init__.py`
```diff
 from . import csvdata
 from . import feather
+from . import ocrtraining
```

**Usage:**
```
sdaps recognize JASONtest/GAS006          # captures crops + OCR guesses
sdaps gui JASONtest/GAS006                # human reviews/corrects + marks verified
sdaps export ocr-training -f "verified" JASONtest/GAS006
# -> JASONtest/GAS006/ocr_training_export/{manifest.csv, images/}
```

**Verified:** Ran the full loop on the test project — `manifest.csv` and
`images/` were produced correctly, with filenames sanitized for filesystem
safety.

---

## 6. Graceful Save on SIGTERM in `sdaps gui`

**Problem:** `sdaps gui` only writes `survey.sqlite` when the user explicitly
saves (Ctrl+S, or "Save" in the close-confirmation dialog). When the GUI is
run headlessly (e.g. served over the network via GTK's Broadway backend, with
no window-close button) and a controlling process needs to end the session,
sending SIGTERM previously just killed the process, discarding any unsaved
corrections.

**Fix:** Register a SIGTERM handler, alongside the existing SIGINT handler,
that calls `survey.save()` before quitting the main loop — mirroring the
"Save" response of the existing close-confirmation dialog
(`MainWindow.quit_application` / `save_project`).

### `sdaps/gui/__init__.py`
```diff
     try:
         # Exit the mainloop if Ctrl+C is pressed in the terminal.
         GLib.unix_signal_add_full(GLib.PRIORITY_HIGH, signal.SIGINT, lambda *args : Gtk.main_quit(), None)
+
+        # SIGTERM is used by external process managers (e.g. a web-based
+        # review dashboard running the GUI under Broadway) to request a
+        # graceful shutdown. Save before quitting, since there is no
+        # window-close dialog to do so in that scenario.
+        def _save_and_quit(*args):
+            provider.survey.save()
+            Gtk.main_quit()
+            return False
+        GLib.unix_signal_add_full(GLib.PRIORITY_HIGH, signal.SIGTERM, _save_and_quit, None)
     except AttributeError:
         # Whatever, it is only to enable Ctrl+C anyways
         pass
```

---

## 7. Grayscale Companion TIFF During Conversion (infrastructure)

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

## 8. Accurate Crop Region for Textbox OCR (Bounding Box Fix)

**Problem:** On real scans (tested with the `gas-en` project), the crop fed to
TrOCR was taken from the *static printed box* (`self.obj.x/y/width/height`),
which is often considerably larger than the area actually written in. As a
result, large portions of the handwritten text fell outside the crop and were
never seen by the OCR model.

**Fix:** Crop from the *detected handwriting bounding box*
(`self.obj.data.x/y/width/height`), which was already computed a few lines
earlier from the connected-component scan plus `scan_padding` +
`extra_padding` clearance. Combined with this tighter, more accurate crop, the
border-removal inset no longer needs to chew up 5%/15% of the image — a fixed
2px inset is enough to drop rendering edge artifacts, since any leftover
border-line sliver is filtered out by the existing oversized-blob check.

### `sdaps/recognize/buddies.py`
```diff
-                px0, py0 = matrix.transform_point(self.obj.x, self.obj.y)
+                # Crop to the detected handwriting bounding box (just computed
+                # above), not the static printed box. The printed box is often
+                # much larger than what was actually written, while the
+                # detected bbox already includes scan_padding + extra_padding
+                # clearance from the outline, so it avoids both cutting off
+                # handwriting and including the border lines.
+                px0, py0 = matrix.transform_point(self.obj.data.x, self.obj.data.y)
                 px1, py1 = matrix.transform_point(
-                    self.obj.x + self.obj.width,
-                    self.obj.y + self.obj.height)
+                    self.obj.data.x + self.obj.data.width,
+                    self.obj.data.y + self.obj.data.height)
                 px = int(min(px0, px1))
                 py = int(min(py0, py1))
                 pw = int(abs(px1 - px0))
@@ ...
                     ah, aw = gray.shape
                     if ah > 0 and aw > 0:
-                        # Strip box borders: inset ~5% horizontally, ~15% vertically.
-                        # The matrix coordinates place us inside the box already,
-                        # so this inset fully removes any remaining border lines.
-                        ix = max(3, int(aw * 0.05))
-                        iy = max(3, int(ah * 0.15))
+                        # The crop is already the detected handwriting bbox
+                        # (plus scan/extra padding), so only a tiny inset is
+                        # needed to drop rendering edge artifacts. Any thin
+                        # border-line sliver that remains is filtered out
+                        # below as an oversized blob.
+                        ix = min(2, aw // 2)
+                        iy = min(2, ah // 2)
                         inner = gray[iy:ah - iy, ix:aw - ix]
                         ih, iw = inner.shape
```

**Verified:** Re-ran recognition on the `gas-en` test project. Before this
change, the saved `ocr_training/*.png` crops for the `worker_id`/`week`
textboxes visibly cut off parts of the handwritten digits; after the change,
the full handwriting is contained in the crop and recognition accuracy
improved (though not yet perfect — see follow-up note below).

**Follow-up (not implemented):** Since `worker_id` and `week` are always
numeric, constraining TrOCR/decoding to digits only could further improve
accuracy. This was discussed but explicitly deferred by the project owner for
now.

---

## 9. Editable Questionnaire ID in `sdaps gui`

**Problem:** The barcode stamped in the corner of each questionnaire (via
`sdaps stamp`) encodes the questionnaire ID, but barcode recognition
occasionally fails on a scanned sheet and `sheet.questionnaire_id` is left as
`None`. The review GUI displayed this value as a read-only label
(`<b>Questionnaire ID: </b>None`), so a human reviewer had no way to correct
it — there was no path to fix a sheet with a missed barcode short of editing
the database directly.

**Fix:** Replace the read-only `Gtk.Label` with an editable
`Gtk.ComboBoxText.new_with_entry()`. The dropdown is pre-populated with
`survey.questionnaire_ids` (the IDs stamped onto the questionnaires via
`sdaps stamp`) for quick selection, but a reviewer can also type any value
directly into the entry — in particular, replacing `None`/empty with the
correct ID read off the paper sheet. Edits are written back to
`sheet.questionnaire_id` immediately (assigning to this attribute marks the
sheet dirty via the existing `Sheet.__setattr__`/`_save_attrs` machinery, the
same as the existing `valid`/`verified` checkboxes), so they are picked up by
the normal save path (including the SIGTERM-triggered save from section 6).

### `sdaps/gui/widget_buddies.py`

`create_widget`: build an editable combo instead of a static label.
```diff
-        self.qid = Gtk.Label()
-        self.qid.set_markup(_('<b>Questionnaire ID: </b>') + markup_escape_text(str(self.obj.survey.sheet.questionnaire_id)))
-        self.qid.props.xalign = 0.0
+        qid_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
+
+        qid_label = Gtk.Label()
+        qid_label.set_markup(_('<b>Questionnaire ID: </b>'))
+        qid_label.props.xalign = 0.0
+
+        # Editable, so that a questionnaire ID that could not be recognized
+        # (shown as "None") can be entered by hand. The dropdown is
+        # pre-filled with the IDs that were stamped onto the questionnaires,
+        # but any value can also be typed in directly.
+        self.qid_combo = Gtk.ComboBoxText.new_with_entry()
+        for qid in self.obj.survey.questionnaire_ids:
+            self.qid_combo.append_text(str(qid))
+        self.qid_entry = self.qid_combo.get_child()
+        self.qid_entry.connect('changed', self.qid_entry_changed_cb)
+
+        qid_box.pack_start(qid_label, False, True, 0)
+        qid_box.pack_start(self.qid_combo, True, True, 6)

         indent.add(vbox)

-        vbox.add(self.qid)
+        vbox.add(qid_box)
```

`sync_state`: update the entry text instead of the label markup, guarding
against feedback loops while typing.
```diff
-        self.qid.set_markup(_('<b>Questionnaire ID: </b>') + markup_escape_text(str(self.obj.survey.sheet.questionnaire_id)))
+        # Only update the text if it changed (or else recursion hits and the
+        # cursor/focus would jump around while typing)
+        qid = self.obj.survey.sheet.questionnaire_id
+        qid_text = '' if qid is None else str(qid)
+        if self.qid_entry.get_text() != qid_text:
+            self.qid_entry.set_text(qid_text)
```

New callback, alongside the existing `toggled_valid_cb`/`toggled_verified_cb`:
```diff
+    def qid_entry_changed_cb(self, widget):
+        text = widget.get_text()
+        self.obj.survey.sheet.questionnaire_id = text if text else None
```

**Verified:** Ran `sdaps gui` (via Broadway) on the `gas-en` test project,
which had one sheet where barcode recognition returned `None`. The field was
editable, pre-filled with the stamped IDs as dropdown suggestions, and typing
the correct ID and saving persisted it to `survey.sqlite`.

---

## Files NOT to include in the PR

The following are local test artifacts and should be excluded:

- `JASONtest/` — local test survey directory with scanned PDFs and generated data
- `JasonTest.txt` — local scratch file
- Any `data_N.csv` files — recognition output from test runs
- Any project's `ocr_training/` and `ocr_training_export/` directories —
  generated by recognition/export, contain scanned handwriting images

---

*This document was generated on 2026-06-09 by Claude (Anthropic), specifically
the model "Claude Sonnet 4.6" (model ID `claude-sonnet-4-6`), running in
Claude Code (Anthropic's CLI for Claude). It was produced by comparing this
working tree against the upstream sdaps repository (release 1.9.13) and
should be reviewed for accuracy before submitting the pull request.*

*Updated on 2026-06-10 (also by Claude Sonnet 4.6 / Claude Code) to add
section 5, "OCR Training-Data Capture and Export".*

*Updated on 2026-06-10 (also by Claude Sonnet 4.6 / Claude Code) to add
section 6, "Graceful Save on SIGTERM in `sdaps gui`", and renumber the former
section 6 ("Grayscale Companion TIFF During Conversion") to section 7.*

*Updated on 2026-06-12 (also by Claude Sonnet 4.6 / Claude Code) to add
section 8, "Accurate Crop Region for Textbox OCR (Bounding Box Fix)", and
section 9, "Editable Questionnaire ID in `sdaps gui`".*
