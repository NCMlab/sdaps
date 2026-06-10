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

## Other barcodes (for comparison)

For a questionnaire using `sdaps_style=code128` with `print_questionnaire_id`
set (as in this project's `GAS006` questionnaire):

- **Bottom-left**: questionnaire ID barcode — only printed if
  `print_questionnaire_id` is set.
- **Bottom-center**: global/participant ID barcode — only printed if
  `\g_sdaps_global_id_tl` is set.
- **Bottom-right**: survey ID + page number — always printed, required for
  basic recognition to work at all.
