# generate_index.py

Recursively scans a PDF library and (re)builds a spreadsheet-style index of every PDF in it.

```bash
python3 generate_index.py                    # index the folder this script lives in
python3 generate_index.py /path/to/library    # index a specific folder
python3 generate_index.py -h                  # help
```

## What it produces

Two files, written into the scanned folder:

- **`library_index.csv`** — plain-text index, one row per PDF.
- **`library_index.xlsx`** — same data, with the **`Folder`** column color-coded by topic: each top-level folder gets its own color, reused consistently throughout the sheet (e.g. every `Force field/Martini` row gets the same color as every other `Force field/...` row, since they share the topic `Force field`), drawn from a fixed non-pastel-washed-out palette. Column widths are pre-sized and the header row is frozen.

Columns (both files): `Authors | Year | Title | Document Type | Folder | Relative Path`

There's no separate "topic" column — the top-level folder already *is* the topic (a file in `IDP/Membrane curvature/Zeno 2018.pdf` has topic `IDP`), so a dedicated column would just duplicate what `Folder` already shows. The topic is used only internally, to pick each row's `Folder` cell color.

Rows are sorted alphabetically by first author.

## How it works on arbitrary folder structures

The scanner (`os.walk`) recurses through **any** folder composition — it doesn't assume a fixed depth or layout:

- PDFs directly in the library root, or nested 5+ subfolders deep, are all found.
- **Folder** is the full relative path to the file's containing directory (e.g. `IDP/Membrane curvature`) — its color comes from just the first path component (the topic), so subfolder detail is preserved in the text while the coloring still groups by top-level topic.
- A PDF sitting directly in the library root gets `Folder = (root)` and topic `Root` for coloring purposes.
- Folder names with spaces, accents, or other Unicode characters work fine.
- Empty folders are simply skipped (nothing to index) — they don't cause errors.

So if you reorganize the library into a different structure later (new folders, deeper nesting, fewer/more subfolders), this script keeps working without modification — it never hard-codes folder names.

## Where Author/Year/Type/Topic come from

**Note:** this script reads only **filenames and folder names** — it does not open or parse PDF content (that's what `format_pdf_name.py`'s `batch` mode does, before you run this). So the index quality depends on filenames already following the library convention:

- **Authors / Year** — parsed from the leading `Surname YEAR` pattern (or the `Author(s) - Title (...) (YEAR)` book pattern). If no such pattern is found, it falls back to whatever text precedes the first `(` and any 19xx/20xx year found anywhere in the name.
- **Document Type** — inferred from the top-level folder (`Book`, `Thesis`, `Tutorial`, ...) and from a `[Tag]` or keyword in the filename, checked in this priority order:

  1. `Book` folder → `Book` or `Book chapter`
  2. `Thesis` folder, or a `[PhD Thesis]`/`[MSc Thesis]` tag → `PhD Thesis` / `MSc Thesis` / `Thesis`
  3. `Tutorial` folder, or "tutorial" in the name → `Tutorial`
  4. "manual" / "protocol" in the name → `Manual` / `Protocol`
  5. `[Book Chapter]` tag → `Book chapter`
  6. Document-status tag, most specific first: `Supplementary Information` (`[SI]`, trailing `SI`, "supplementary"/"supporting") → `Editorial` → `Perspective` → `News & Views` → `Mini Review` → `Review` → `Preprint`
  7. Otherwise → `Research article`

  Both the canonical `[Bracket]` tag form (written by `format_pdf_name.py`) and legacy forms already present in this library (e.g. `(SI)`, `(PhD thesis)`, bare `SI` suffix) are recognized, so older filenames are classified correctly without needing to be renamed first.
- **Folder color (topic)** — the top-level folder name, used only to color the `Folder` cell in the `.xlsx` (see above).

See `format_pdf_name.md` for the full tag vocabulary and the `[brackets]` vs `(parentheses)` convention — both scripts use the same priority order so they never disagree on a given file.

## Typical workflow

```bash
# 1. First, make sure filenames follow the convention (see format_pdf_name.py)
python3 format_pdf_name.py batch "/path/to/library/SomeMessyFolder" --recursive --apply

# 2. Then (re)build the index
python3 generate_index.py "/path/to/library"
```

Safe to re-run anytime — it only reads PDF filenames and (re)writes the two index files. It never renames, moves, or deletes any PDF.

## Requirements

`openpyxl` for the `.xlsx` output (`pip install openpyxl`). CSV generation has no extra dependency.
