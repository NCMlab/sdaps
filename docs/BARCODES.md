# The Bottom-Right Barcode (Survey ID + Page Number)

The bottom-right barcode is the **survey ID + page number** barcode, and it's
the one piece of identification SDAPS *requires* — everything else
(questionnaire ID, global/participant ID, the questionnaire-ID barcode on the
bottom-left) is optional.

## What's encoded

Defined in `tex/class/sdapsbase.dtx` (lines ~1558-1573):

```
<survey_id><page_number padded to 4 digits>
```

e.g. survey ID `42` + page `3` → barcode content `420003`.

The LaTeX source comments note that this barcode is printed
**unconditionally**, regardless of the chosen style settings, because it is
required for the recognition process.

## How it's read

The same barcode is decoded three different ways in
`sdaps/recognize/code128.py`:

### 1. `get_page_rotation()` (lines 33-67)

Just checks *whether a barcode exists* at the bottom-right.

- Found there → the page is right-side-up.
- Not found there → look at the top-left instead. Finding it there means the
  page was scanned upside-down (180° rotation), letting SDAPS auto-correct
  orientation before doing anything else.

### 2. `get_page_number()` (lines 70-91)

Takes the **last 4 digits** of the decoded string as the page number.

This tells SDAPS which page of the questionnaire layout
(`questionnaire.sdaps`) to use for locating checkboxes/textboxes on this
specific image. It's also used to:
- pair up duplex front/back pages
- detect missing, duplicate, or out-of-range pages
- order pages via `sdaps reorder`

### 3. `get_survey_id()` (lines 93-111)

Takes everything **except the last 4 digits** as the survey ID.

SDAPS compares this against the project's own survey ID
(`sdaps/recognize/buddies.py`, lines ~230-237) — if they don't match, the
sheet is marked invalid (`valid = 0`). This catches the case where a scan from
a different sdaps project got mixed into your scan batch.

## Summary

**One barcode = page orientation + page number + survey-of-origin check**, all
needed before SDAPS can locate any checkboxes on the page at all.

---

# The Bottom-Left Barcode (Questionnaire ID)

Unlike the bottom-right barcode, this one is **optional** — it only appears if
the survey has `print_questionnaire_id` enabled (true for this project's
`GAS006` questionnaire) *and* a questionnaire ID was actually assigned to that
sheet during `sdaps stamp`.

## What's encoded

Defined in `tex/class/sdapsbase.dtx` (lines ~1535-1554, `code128` style block):

```
<questionnaire_id>
```

This is the raw questionnaire ID as assigned during `sdaps stamp` — for
`code128` style it can be alphanumeric (any character in `defs.c128_chars`),
for `classic` style it must be an integer. A text label is printed **above**
the barcode showing `\g_sdaps_questionnaire_id_label_tl` if one was set in the
`.tex` source, otherwise the raw ID itself is shown as the label.

Where the IDs come from:
- `sdaps stamp -r N` — generates `N` new random IDs.
- `sdaps stamp -f FILE` — uses IDs read from `FILE`.
- `sdaps stamp --existing` — uses IDs already stored in the survey (added
  earlier via `sdaps ids -a FILE`).

Each assigned ID is checked by `Survey.validate_questionnaire_id()`
(`sdaps/model/survey.py`, lines ~509-525): integer-only for `classic` style,
restricted to `code128`-safe characters for `code128` style.

## How it's read

`get_questionnaire_id()` in `sdaps/recognize/code128.py` (lines 113-130) scans
a region at the **bottom-left** of the page (`x = 0` to `paper_width / 2`,
same vertical band as the other two barcodes). It returns the decoded string
**as-is** — no digit-only check, since the ID may be alphanumeric.

## How it's used in `buddies.py`

In `Sheet.recognize()` (lines ~244-265):

- Only attempted at all if `self.obj.survey.defs.print_questionnaire_id` is
  true.
- In duplex mode, only read from the back side (even page numbers); in simplex
  mode, read from whichever page isn't a dummy blank.
- `image.recognize.calculate_questionnaire_id()` calls
  `get_questionnaire_id()` and stores the result on `image.questionnaire_id`.
- `duplex_copy_image_attr()` copies the value across a front/back page pair if
  only one side could be decoded.
- `self.obj.questionnaire_id` is set to the **first non-None value** found
  across all images belonging to the sheet.
- As with the other barcodes, if different pages of the same sheet decode
  *different* questionnaire IDs, SDAPS prints the "Got different IDs on
  different pages" warning and recommends running `sdaps reorder`.

## What it's used for

- **`sdaps export csv` / `export feather`**: included as the `questionnaire_id`
  column in every exported row.
- **`sdaps import csv`**: rows are matched back to sheets by
  `questionnaire_id` — this is the mechanism for merging manually-corrected
  data or externally entered data back into the project.
- **`sdaps gui`**: `Survey.goto_questionnaire_id()`
  (`sdaps/model/survey.py`, lines ~472-494) lets you jump straight to the sheet
  for a given printed ID — handy for "I need to look at questionnaire #42"
  during data entry/QA.
- **`sdaps reorder`**: uses the questionnaire ID (read during a
  `recognize --identify` pass) to figure out which scanned pages belong
  together when sheets were scanned out of order.

## Summary

**Identifies which individual printed questionnaire a sheet came from.**
Optional — only present if you choose to print per-questionnaire IDs (e.g. to
support re-importing corrected data, or to track which physical copy was given
to which respondent).

---

# The Bottom-Center Barcode (Global ID)

Also **optional** — only printed if `\g_sdaps_global_id_tl` is non-empty.

## What's encoded

Defined in `tex/class/sdapsbase.dtx` (lines ~1575-1594, `code128` style block):

```
<global_id>
```

Unlike the questionnaire ID (one per printed sheet), the global ID is a
**single value for the entire survey** — set once, stored as
`survey.global_id`, and persisted in the project's `info` file under
`[sdaps] global_id = ...` (`sdaps/model/survey.py`, lines ~253-255 load it,
lines ~359-362 save it). Every sheet stamped after the global ID is set gets
the same value baked into this barcode. As with the other code128 barcodes, a
text label is printed above it: `\g_sdaps_global_id_label_tl` if set,
otherwise the raw global ID itself.

## How it's read

`get_global_id()` in `sdaps/recognize/code128.py` (lines 132-148) scans a
region at the **bottom-center** of the page (`x = paper_width / 4` to
`3 * paper_width / 4`). Returns the decoded string as-is.

## How it's used in `buddies.py`

In `Sheet.recognize()` (lines ~267-292):

- Reading it is **unconditional** (no `defs` flag check) — if the survey
  doesn't use a global ID, the barcode simply isn't there and
  `get_global_id()` returns `None`, which is fine.
- In duplex mode, only read from the back side (even page numbers); duplex-
  copied across the front/back pair like the other IDs.
- `self.obj.global_id = self.obj.images[0].global_id`.
- Same cross-page consistency check as the other two IDs: a mismatch between
  pages of one sheet triggers the "different IDs on different pages" /
  `sdaps reorder` warning.

## What it's used for

- **`sdaps export csv` / `export feather`**: included as the `global_id`
  column in every exported row.
- Because it's the *same* value on every sheet of a given survey/printing run,
  it's mainly useful for **distinguishing batches** when data from multiple
  separate printings or sites is later merged together (e.g. each site or
  print run gets its own global ID, and after combining exports you can still
  tell which batch a row came from).
- Set/changed via the survey's `info` file (`global_id` key under `[sdaps]`)
  and takes effect for sheets stamped from that point on — per the
  `Survey.global_id` docstring, "It is used during the 'stamp' step."

## Summary

**A single, survey-wide identifier baked into every stamped questionnaire.**
Useful for tagging which printing/distribution batch a scanned sheet came
from when merging data across multiple runs of the same study.

---

# All Three Barcodes at a Glance

| Position | Content | Required? | Identifies |
|---|---|---|---|
| Bottom-right | survey ID + page number | **Always** | which page, and that the scan belongs to this survey |
| Bottom-left | questionnaire ID | Optional (`print_questionnaire_id`) | which individual printed sheet |
| Bottom-center | global ID | Optional (`\g_sdaps_global_id_tl` set) | which survey/printing batch (same value on every sheet) |

---

*This document was generated on 2026-06-10 by Claude (Anthropic), specifically
the model "Claude Sonnet 4.6" (model ID `claude-sonnet-4-6`), running in
Claude Code (Anthropic's CLI for Claude). Content was produced by reading the
sdaps source code (`sdaps/recognize/code128.py`, `sdaps/recognize/buddies.py`,
`sdaps/model/survey.py`, `tex/class/sdapsbase.dtx`) and should be verified
against the code if it is later modified.*
