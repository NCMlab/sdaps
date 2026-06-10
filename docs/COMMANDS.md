# SDAPS Command Reference

`sdaps` is organized as a single command with subcommands:
`sdaps <command> [options] <project> [args...]`

Most commands take the project directory as their first positional argument
(the directory created by `sdaps setup tex`). Run `sdaps <command> -h` for the
full option list of any command.

This reference groups commands by where they fit in the typical workflow:

```
setup tex  ─────────────────────────────────────────────────┐
                                                              │
ids / stamp / cover  ──► (print & distribute) ──► (collect) │
                                                              │
add / convert  ──► reorder ──► recognize ──► annotate/gui    │
                                                              │
export csv / export feather / report tex / report reportlab │
                                                              │
info, reset  (housekeeping, usable at any stage) ────────────┘
```

---

## 1. Project Setup

### `sdaps setup tex <project> <questionnaire.tex> [additional_questions]`

Creates a new survey project from a LaTeX questionnaire. The `.tex` file must
use the SDAPS LaTeX class, which defines the metadata (title, paper size,
checkbox/textbox layout, etc.).

**Key options:**
- `-a/--add FILE` — additional files referenced by the `.tex` document (images,
  included `.tex` snippets, etc.) that should be copied into the project
  directory. Repeatable.
- `-e/--engine` — the LaTeX engine to compile with (default from `defs.py`,
  normally `pdflatex`).
- `additional_questions` — an optional second `.tex` file containing extra
  questions not part of the main printed questionnaire (e.g. office-use-only
  fields).

**What it does:** Compiles the `.tex` file, creates the project directory
(`<project>/`), and stores `questionnaire.pdf`, `questionnaire.sdaps` (the
parsed questionnaire structure), `survey.sqlite` (the database), and copies of
all the LaTeX class files needed to recompile later.

**Example:**
```
sdaps setup tex GAS006 questionnaire.tex
```

---

## 2. Preparing Questionnaires for Distribution

### `sdaps ids <project>`

Manage the pool of questionnaire IDs (only relevant if your questionnaire uses
ID-based barcodes/identification).

- With no options: writes all currently stored IDs to `ids_%i` (auto-numbered)
  or to `-o FILE` (use `-o -` for stdout).
- `-a/--add FILE` — read IDs (one per line) from `FILE` (or `-` for stdin) and
  add them to the survey's internal ID list. These IDs can then be used by
  `stamp --existing`.

### `sdaps stamp <project>`

Generates the actual printable PDF — adds corner marks, barcodes, and
questionnaire IDs to the questionnaire layout. **This is the file you print
and hand out.**

**Key options:**
- `-r/--random N` — generate `N` questionnaires with new random IDs.
- `-f/--file FILE` — generate questionnaires using IDs read from `FILE`.
- `--existing` — generate one questionnaire for every ID already stored in the
  survey (e.g. previously added with `sdaps ids -a`).
- `-o/--output` — output filename (default: `stamped_%i.pdf`, where `%i` is an
  auto-incremented number).

**Example:**
```
sdaps stamp GAS006 -r 30          # 30 questionnaires with random IDs
```

### `sdaps cover <project>`

Creates a cover/title page listing the survey metadata (title and any custom
`info` keys — see `sdaps info` below). Useful as a separate handout or
introduction sheet.

**Key options:**
- `-o/--output` — output filename (default: `cover_%i.pdf`).

---

## 3. Bringing Scanned Data into the Project

### `sdaps add <project> <images...>`

Registers scanned page images as "sheets" in the project so `recognize` can
process them.

**Input requirement (without `--convert`):** multipage 300dpi monochrome (1bpp)
TIFF files.

**Key options:**
- `--convert` — run the input files (any image format, including PDFs)
  through the conversion pipeline first (see `sdaps convert` below), then add
  the result. Requires OpenCV.
- `--3d-transform` — after `--convert`, attempt a perspective ("3D")
  transformation based on the corner marks. Useful for photos taken at an
  angle rather than flatbed scans.
- `--duplex` — the input contains a duplex scan of a simplex (single-sided)
  questionnaire (i.e. blank backs are included). Default assumes simplex
  scanning, and inserts dummy blank pages automatically unless this is set.
- `--force` — add the images even if the page count doesn't match a multiple
  of the expected page count per questionnaire. Only use if you understand the
  consequences (pages may be misaligned with sheets).
- `--copy` / `--no-copy` — copy image files into the project directory
  (default), or just reference them by relative path. `--no-copy` is
  incompatible with `--convert`.

**Example:**
```
sdaps add --convert GAS006 "Scan_2026-06-09.pdf"
```

This converts the PDF to monochrome TIFF (saving `N.tif` and a grayscale
companion `N_gray.tif` per page in the project directory) and registers each
page as part of a "sheet".

### `sdaps convert -o OUTPUT.tif <project> <images...>`

Standalone conversion tool — converts arbitrary image files (e.g. JPEG scans,
PDFs, photos) to the multipage monochrome TIFF format `add` expects, without
adding them to the project. Useful if you want to inspect or tweak the
converted file before running `add`.

**Key options:**
- `--3d-transform` — perspective-correct using detected corner marks.
- `-o/--output` (required) — output TIFF path.

### `sdaps reorder <project>`

Reorders pages within sheets according to the recognized questionnaire ID.
Use this when pages were scanned/added out of order across multiple
questionnaires.

**Workflow:**
1. `sdaps add` all scanned files.
2. `sdaps recognize --identify <project>` — recognizes just enough (corner
   marks, questionnaire ID/page number) to know what each page is, without
   doing full checkbox recognition.
3. `sdaps reorder <project>` — reshuffles pages into the correct order/sheets
   based on the IDs found in step 2.
4. `sdaps recognize <project>` — run full recognition.

---

## 4. Recognition

### `sdaps recognize <project>`

The core OMR (optical mark recognition) step. Iterates over all sheets,
locates corner marks, reads barcodes/questionnaire IDs, determines checkbox
states, and (with the OCR extension in this fork) reads handwritten text from
textboxes into `data.text`.

**Key options:**
- `--identify` — only do the lightweight identification pass (corner marks +
  ID/page number), skipping checkbox/textbox recognition. Used before
  `reorder` (see above).
- `-r/--rerun` — reprocess **all** sheets, including ones already marked
  `recognized` or `verified`. Without this flag, sheets that were already
  recognized (or manually verified in the GUI) are skipped — useful for
  incrementally processing newly added scans.

**Example:**
```
sdaps recognize GAS006          # process newly added sheets only
sdaps recognize -r GAS006        # reprocess everything (e.g. after a code change)
```

### `sdaps annotate <project>`

Debug utility. Produces an annotated copy of each scanned page with overlays
showing what SDAPS detected: corner marks, checkbox bounding boxes, detected
fill state, textbox regions, etc. Useful for diagnosing why a particular sheet
was recognized incorrectly.

### `sdaps boxgallery <project>`

Debug utility for tuning the checkbox-recognition heuristics in `defs.py`.
Generates PDFs that group all detected checkboxes by their measured "coverage"
(how filled-in they appear) for each heuristic, sorted so you can visually find
the threshold between "checked" and "unchecked".

**Key options:**
- `--debugrecognition` — reruns part of recognition to also pull internal
  debug images (slower, but shows more detail).

### `sdaps gui <project>`

Launches a graphical interface (GTK) for manually reviewing and correcting
recognized data — both checkbox states and OCR'd text. Run `recognize` first.
Marking a sheet as reviewed in the GUI sets its `verified` flag, which causes
later `sdaps recognize` runs (without `-r`) to skip it.

**Key options:**
- `-f/--filter` — show only a filtered subset of sheets (same filter syntax as
  used by `export`/`report`).

---

## 5. Exporting Results

### `sdaps export csv <project>`

Exports all recognized data to a CSV file: one row per sheet, with columns for
`questionnaire_id`, `global_id`, status flags (`empty`, `valid`, `recognized`,
`review`, `verified`), and one column per checkbox/textbox question.

**Key options:**
- `-o/--output` — output filename (default: `data_%i.csv`; use `-` for
  stdout).
- `-d/--delimiter` — CSV delimiter (default `,`).
- `-f/--filter` — only export a filtered subset of sheets.
- `--images` — also export an image crop of each freeform/textbox field (saved
  alongside the CSV in an `img/` subdirectory).
- `--question-images` — export an image of each *question* (including all its
  checkboxes), not just textboxes.
- `--quality` — include a numeric recognition-quality/confidence value for
  each checkbox column.

### `sdaps import csv <project> <file>`

Imports/updates data from a previously exported CSV file. **Limited**: rows
are matched to sheets by `questionnaire_id`, so this only works for projects
that print a questionnaire ID on each sheet, and is mainly intended for
re-importing manually corrected data or merging external data entry.

### `sdaps export feather <project>`

Exports the same data as `export csv`, but as an Apache Feather file (binary
columnar format) using pandas — convenient for direct loading into a pandas
DataFrame for analysis. Requires `pandas` and `pyarrow`.

**Key options:**
- `-o/--output` — output filename (default: `data_%i.feather`).
- `-f/--filter` — only export a filtered subset of sheets.

---

## 6. Reports

Both report commands accept a `-f/--filter` option to restrict the report to a
subset of sheets (e.g. `-f "1_1==1"` to report only on respondents who checked
a particular box — see the SDAPS filter syntax docs for details).

### `sdaps report tex <project>`

Generates a statistical PDF report using LaTeX (siunitx, TikZ, etc.) — bar
charts of checkbox distributions, and (unless suppressed) images of freeform
text answers.

**Key options:**
- `--suppress-images` — omit original scan images of freeform fields (privacy).
- `--suppress-substitutions` — don't replace suppressed images with
  placeholder text.
- `--create-tex` — output the generated `.tex` source instead of compiling to
  PDF (useful for customizing the report template).
- `-p/--paper` — paper size (default: locale-dependent).
- `-o/--output` — output filename (default: `report_%i.pdf`).

### `sdaps report reportlab <project>`

Equivalent statistical report generated with the Python `reportlab` library
instead of LaTeX (no LaTeX toolchain required).

**Key options:**
- `-s/--short` — short format, omitting freeform text fields.
- `-l/--long` — detailed format (default).
- `--all-filters` — instead of one report, generate a separate filtered report
  for *every* checkbox (cross-tabulation style).
- `--suppress-images` / `--suppress-substitutions` — same as above.
- `-p/--paper`, `-o/--output` — same as above.

---

## 7. Project Management

### `sdaps info <project> [key] [value]`

View or edit survey metadata (printed on cover pages and reports).

- No arguments: lists all defined metadata keys (always includes `title`).
- `key` only: prints the value of that key.
- `key value`: sets the key to the given value.
- `key -d/--delete`: deletes the key.

**Example:**
```
sdaps info GAS006 title "GAS Study - Site Montreal"
sdaps info GAS006 site Montreal
sdaps info GAS006                 # list all keys
```

### `sdaps reset <project>`

**Destructive.** Discards all collected/recognized data (sheets, recognized
answers, OCR text) and returns the project to its freshly-`setup` state — the
questionnaire definition, LaTeX sources, and metadata are kept, but everything
related to scanned sheets is removed. Useful when re-testing the recognition
pipeline from scratch.

```
sdaps reset GAS006
```

---

## Typical End-to-End Workflow

```
sdaps setup tex GAS006 questionnaire.tex
sdaps info GAS006 site Montreal
sdaps stamp GAS006 -r 50                     # 50 printable questionnaires

# ... print, distribute, collect, scan ...

sdaps add --convert GAS006 scans.pdf
sdaps recognize GAS006
sdaps gui GAS006                             # spot-check / correct
sdaps export csv GAS006
sdaps report tex GAS006
```

---

*This document was generated on 2026-06-10 by Claude (Anthropic), specifically
the model "Claude Sonnet 4.6" (model ID `claude-sonnet-4-6`), running in
Claude Code (Anthropic's CLI for Claude). Content was produced by reading the
sdaps command-line source (`sdaps/cmdline/*.py`) and should be verified
against `sdaps <command> -h` if it is later modified.*
