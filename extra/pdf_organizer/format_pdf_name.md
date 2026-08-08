# format_pdf_name.py

Renames (and optionally moves) PDFs into this library's naming convention.

```
python3 format_pdf_name.py                # prints the menu below
python3 format_pdf_name.py single -h       # full help for single mode
python3 format_pdf_name.py batch -h        # full help for batch mode
```

## Naming conventions applied

| Type    | Pattern |
|---------|---------|
| Article/Review | `[prefix.]Surname YEAR [[TAG]] [(comment)].pdf` |
| Book | `Author(s) - Title (Publisher) (YEAR).pdf` (or without publisher if unknown) |
| Book chapter | `Author - Chapter Title [Book Chapter] YEAR.pdf` |
| Thesis | `Surname YEAR [PhD Thesis].pdf` / `Surname YEAR [MSc Thesis].pdf` |

`prefix` is any combination of `0`, `00`, `000`, `0000`, `(+)` (e.g. `000.`, `(+).`, `000(+).`) — used in this library to mark priority/importance and "already read". `--prefix` only accepts exactly that vocabulary — it is **not** a place to put a document-status label. `--prefix Review` (meaning "this is a review") is a common mix-up; it's rejected with an error pointing you to `--tag Review` instead, rather than silently producing a nonsensical name like `review.Surname YEAR.pdf`.

### `[Square brackets]` vs `(parentheses)`

The two are not interchangeable — each holds a different kind of information:

- **`[Square brackets]`** — exactly one recognized **document-status tag**, machine-readable, drawn from a fixed list:

  | Tag | Meaning |
  |-----|---------|
  | `[Review]` | Review article |
  | `[Mini Review]` | Short/mini review |
  | `[Editorial]` | Editorial |
  | `[Perspective]` | Perspective piece |
  | `[News & Views]` | News & Views commentary |
  | `[Preprint]` | Preprint (bioRxiv, medRxiv, etc.) |
  | `[SI]` | Supplementary Information / supporting material for another PDF |
  | `[Book Chapter]` | Book chapter (used with `--type chapter`) |
  | `[PhD Thesis]` / `[MSc Thesis]` | Thesis level (used with `--type thesis`) |

- **`(parentheses)`** — a short, free-text **topic/keyword comment** for humans searching the library (e.g. `(ER-phagy)`, `(Atg8 lipidation)`). Length is controlled by `--detail` (see below).

  Example: `Zeno 2018 [SI].pdf`, `Hoyer 2023 [Review] (ER-phagy).pdf`, `Farnung 2022 [Preprint] (ATG3 LIR motif).pdf`.

By default the tag is **auto-detected** for both `single` and `batch` (see detection rules below) — in the common case you don't need to pass `--tag` at all. Three ways to control it explicitly:

| Want | `single` | `batch` |
|------|----------|---------|
| Auto-detect (default) | omit `--tag` | omit `--no-tag` |
| Force a specific tag | `--tag Review` | *(no per-file override — fix that one file afterwards with `single`)* |
| Force NO tag, skip detection | `--tag None` | `--no-tag` |

The detection itself checks, in order: (1) an existing recognized `[Tag]` already in the filename, (2) filename hints like a trailing `SI`/`(SI)`/`supplementary` token, (3) whether the PDF's own first lines read like an SI/Supplementary cover page (an article that merely *mentions* "see Supporting Information" in its body text — very common boilerplate — does **not** count), then (4) Editorial/Perspective/News & Views/Mini Review/Review/Preprint keywords near the top of the first page. It's still a heuristic — always check the `(auto-detected: ...)` line or the batch dry-run preview.

## Modes

### `single` — one file

Every flag is optional — `--type` defaults to `article` (the common case), and anything else you leave out — `--author`, `--year`, `--tag`, `--title`, `--prefix`, `--comment` — is auto-detected from the PDF's metadata/first page (same detection engine as `batch`). Pass a flag explicitly whenever you already know the value or want to override the guess. The console always tells you when it filled in author/year, e.g. `(auto-detected: author='Hoyer', year='2023')` — check that line before adding `--apply`.

Key flags: `--type {article,book,chapter,thesis}` (required), `--prefix`, `--author`, `--year`, `--tag`, `--comment`, `--detail`, `--title`, `--publisher`, `--thesis-level {PhD,MSc}`, `--dest-folder`, `--apply`.

#### Examples, simplest to most detailed

**1. Simplest possible call** — just point at the file; `--type` defaults to `article` and everything else is guessed:

```bash
python3 format_pdf_name.py single "/path/to/file.pdf"
```
```
(auto-detected: author='Hoyer', year='2023')
Old: /path/to/file.pdf
New: /path/to/Hoyer 2023.pdf
(dry-run)
```
Still a dry-run — nothing renamed yet. If the guess looks right, re-run with `--apply`:
```bash
python3 format_pdf_name.py single "/path/to/file.pdf" --apply
```

**2. Override just one guessed field** — say the tag was mis-detected, or you want to add a topic comment the metadata can't give you:

```bash
python3 format_pdf_name.py single "/path/to/file.pdf" --type article \
    --tag Review --comment "ER-phagy" --apply
```
Author and year are still auto-detected here; only `--tag`/`--comment` are pinned.

**3. Fully explicit** — skip auto-detection entirely by supplying everything (useful for scanned/garbled PDFs with no usable metadata):

```bash
python3 format_pdf_name.py single "/path/to/file.pdf" \
    --type article --prefix 000 --author "Hoyer" --year 2023 \
    --tag Review --comment "ER-phagy" --apply
```
→ `000.Hoyer 2023 [Review] (ER-phagy).pdf`

**4. Supplementary Information for another paper already in the library:**

```bash
python3 format_pdf_name.py single "/path/to/si.pdf" \
    --type article --author "Zeno" --year 2018 --tag SI --apply
```
→ `Zeno 2018 [SI].pdf`

**5. Move it into place at the same time** — auto-detect the name, but also file it into a topic folder (created if it doesn't exist):

```bash
python3 format_pdf_name.py single "/path/to/file.pdf" --type article \
    --tag Review --comment "ER-phagy" --dest-folder "Autophagy/ER-phagy" --apply
```

**6. A book** (auto-detected title/author from PDF metadata often works, but books are worth checking manually since titles can be messy):

```bash
python3 format_pdf_name.py single "/path/to/book.pdf" \
    --type book --author "Andrew R Leach" \
    --title "Molecular Modelling: Principles and Applications" \
    --publisher "Prentice Hall" --year 2001 \
    --dest-folder "Book" --apply
```
→ `Book/Andrew R Leach - Molecular Modelling: Principles and Applications (Prentice Hall) (2001).pdf`

**7. A book chapter:**

```bash
python3 format_pdf_name.py single "/path/to/chapter.pdf" --type chapter \
    --author "Alessandri" --title "Martini 3 for beginners" --year 2023 --apply
```
→ `Alessandri - Martini 3 for beginners [Book Chapter] 2023.pdf`

**8. A thesis, letting author/year auto-detect, only specifying the level:**

```bash
python3 format_pdf_name.py single "/path/to/thesis.pdf" --type thesis --thesis-level MSc --apply
```

### `batch` — a whole folder, auto-detected

Points at a folder of PDFs; for each file the script reads the PDF's metadata and first-page text to guess:
- **Author** — from the PDF's `Author` metadata field (first author's surname), falling back to scanning the first page for a byline-looking line.
- **Year** — from the first page text, falling back to the PDF's creation date.
- **Tag** — one of `SI`, `Editorial`, `Perspective`, `News & Views`, `Mini Review`, `Review`, `Preprint`, checked in that priority order (first match wins). Filename hints are checked before PDF content: a trailing `SI`/`_si_`/`supplementary` token, or an existing recognized `[Tag]` already in the name, take priority over content sniffing. This mirrors the priority used by `generate_index.py` so both scripts agree on the same file.
- Any priority **prefix** (`0`/`00`/`000`/`0000`/`(+)`) already in the filename is preserved.
- **Comment** — reuses whatever `(comment)` is already in the filename; if there isn't one, falls back to the PDF's own `Title` metadata. Either way, `--detail` trims the result to the requested length (see below).

There's no per-file override in `batch` mode — it's meant for bulk cleanup of a whole folder at once. If one particular file's guess is wrong, fix that file afterwards with `single` (which does support overrides).

#### Default destination: `PDF_formatted`

If you don't pass `--dest-folder`, renamed files are **not** left in place — they're moved into a new `PDF_formatted` subfolder created inside the scanned folder (e.g. scanning `/path/to/messy_folder` writes into `/path/to/messy_folder/PDF_formatted/`). This keeps the original, still-messy files clearly separated from the renamed ones so you can compare before cleaning up. Even with `--recursive` pulling PDFs from several subfolders, they all land in that one `PDF_formatted` folder — not one per subfolder.

To rename in place instead (no move), pass `--dest-folder "."` explicitly. To file everything into a specific library folder instead, pass `--dest-folder "path/to/folder"` as usual.

#### Examples, simplest to most detailed

**1. Simplest possible call — just preview what would happen** (no flags beyond the folder; always starts as a dry-run):

```bash
python3 format_pdf_name.py batch "/path/to/messy_folder"
```
```
No --dest-folder given: renamed files will be placed in /path/to/messy_folder/PDF_formatted

Found 12 PDF(s). Mode: DRY-RUN

Old: /path/to/messy_folder/1-s2.0-S0092867410013103-main.pdf
New: /path/to/messy_folder/PDF_formatted/Hurley 2010 [Review].pdf
(dry-run)
...
Nothing was changed — re-run with --apply once the proposed names look right.
```
*(illustrative — the actual guesses depend entirely on each PDF's own metadata/text)*

**2. Same folder, now including subfolders, still just previewing:**

```bash
python3 format_pdf_name.py batch "/path/to/messy_folder" --recursive
```

**3. Happy with the preview — commit it** (creates `/path/to/messy_folder/PDF_formatted/` and moves the renamed copies there):

```bash
python3 format_pdf_name.py batch "/path/to/messy_folder" --recursive --apply
```

**4. Skip tag auto-detection entirely** — every file gets `Surname YEAR (comment).pdf`, no `[Tag]` at all, even if some look like reviews/SI/preprints:

```bash
python3 format_pdf_name.py batch "/path/to/messy_folder" --recursive --no-tag --apply
```

**5. Rename in place instead** — skip the `PDF_formatted` default, no move at all:

```bash
python3 format_pdf_name.py batch "/path/to/messy_folder" --recursive --dest-folder "." --apply
```

**6. Control comment verbosity while renaming in bulk** (e.g. keep existing topic comments short across the whole folder):

```bash
python3 format_pdf_name.py batch "/path/to/messy_folder" --recursive --detail 2 --apply
```

**7. Rename *and* relocate an entire folder's contents straight into the library** — e.g. a scratch folder of newly-downloaded PDFs, filed directly into a topic subfolder (created automatically if it doesn't exist yet) instead of the `PDF_formatted` default:

```bash
python3 format_pdf_name.py batch "/path/to/Downloads/new_papers" --recursive \
    --dest-folder "IDP/New topic" --apply
```

**8. Full bulk-cleanup pipeline** — reformat a messy folder into the library, then rebuild the index:

```bash
python3 format_pdf_name.py batch "/path/to/Downloads/new_papers" --recursive \
    --detail 1 --dest-folder "Autophagy/Selective" --apply
python3 generate_index.py "/home/alejandro/Dropbox/Academia/Papers"
```

This is a **best-effort heuristic** — always check the dry-run preview before adding `--apply`. PDF metadata sometimes lists a corresponding author instead of the first author, or omits the year.

## `--dest-folder` (both modes)

Moves the renamed file(s) into that folder. Created automatically (`mkdir -p` style) if it doesn't exist yet — safe to point at a brand-new subfolder.

- **`single` mode**: interpreted relative to the PDF's current location unless given as an absolute path. Omit it to rename in place (no move) — that's `single`'s default.
- **`batch` mode**: interpreted relative to the scanned folder unless given as an absolute path. **Omitting it does NOT mean "rename in place"** — it defaults to `<scanned folder>/PDF_formatted`, so renamed files stay separated from anything not yet processed. Pass `--dest-folder "."` to rename in place instead.

## `--detail {0,1,2,3}` (both modes, default `1`)

Controls how much text is allowed inside the `(comment)` parentheses:

| Level | Meaning | Example |
|-------|---------|---------|
| `0` | No parentheses at all | `Hoyer 2023.pdf` |
| `1` *(default)* | A single meaningful keyword | `Hess 1996 (constraints).pdf` |
| `2` | Several meaningful keywords | `Hess 1996 (constraints; molecular dynamics).pdf` |
| `3` | Long / very detailed (full text, unchanged, up to a 140-char sanity cap) | `Hess 1996 (constraints; molecular dynamics; Langevin dynamics; SHAKE).pdf` |

Where the untrimmed comment text comes from, in priority order:
1. `--comment` if you passed it explicitly (`single` only).
2. The `(comment)` already in the file's current name, if any.
3. The paper's own **`Keywords:`** line on the first page, if it has one — this is the best source, since it's already a hand-picked list of topic terms by the authors themselves (handles `Keywords: X; Y; Z`, `Keywords: X, Y, Z`, and one-keyword-per-line layouts).
4. Otherwise, the PDF's `Title` metadata (e.g. a paper with no existing comment/keywords and rich metadata will get its full title as the comment) — this is what makes `--detail 3` useful even on a freshly-downloaded, generically-named file like `123.pdf` or `main.pdf`.
5. If none of the above yield anything (no metadata, no keywords, or a placeholder title like a LaTeX build artifact), no comment is added regardless of `--detail`.

**How levels 1–2 pick "meaningful" words**, so they never end up as an arbitrary word-count slice (like the old `LAMMPS - a flexible` cut mid-phrase):
- If the source is a `Keywords:`-style phrase list, whole keyword phrases are selected (`constraints`, `molecular dynamics`, ...) — never split apart mid-phrase.
- Otherwise (e.g. falling back to `Title` metadata), common English function words (articles, prepositions, conjunctions — "a", "the", "for", "and", ...) are filtered out first, so what's left is real content words like `LAMMPS flexible simulation tool` instead of `LAMMPS - a flexible`.
- Level `3` never filters anything — it keeps the original, naturally-phrased text (just capped at 140 characters) since the point there is a full description, not a keyword list.

## Uncertain detection & `--force`

Some PDFs simply can't be auto-detected confidently — very old scans, garbled OCR, or files with no usable metadata at all. When that happens (auto-detected author is `Unknown` and/or year is `0000`), the script treats it as **uncertain** and, by default, **refuses to rename that file**:

```bash
python3 format_pdf_name.py single old_scan.pdf
```
```
(auto-detected: author='Unknown', year='0000')
NOT renamed — author/year could not be confidently auto-detected (common for very old
articles, scans, or PDFs with no metadata).
Pass --author/--year explicitly, or --force to rename anyway (results may be wrong).

Logged to: /path/to/format_pdf_name_uncertain.log
```

Only a field you *didn't* pass yourself counts as uncertain — if you give `--author`/`--year` explicitly, that field is never second-guessed. This only ever fires in article/thesis/book/chapter flows where author/year are actually used.

**Author detection, in priority order:** (1) the PDF's own `Author` metadata; (2) an ALL-CAPS byline like `BERK HESS,1 HENK BEKKER,...` — common in older papers; (3) a mixed-case `Firstname Lastname` byline. All three reject a small blocklist of generic non-name words (`Simulations`, `Article`, `Review`, `University`, ...) that can otherwise get mistaken for a surname when they appear near the top of the page (e.g. picked from the paper's own title/subtitle rather than its actual author list) — a rejected candidate falls through to the next method instead of being accepted as a wrong "name", and if nothing passes, the file is correctly reported as `Unknown`/uncertain rather than silently getting a plausible-looking-but-wrong author. This is still a heuristic over free-form PDF text, though — some byline formats (e.g. institutional-repository cover pages listing `Surname, Firstname; Surname, Firstname; ...`) aren't recognized yet and can still produce a wrong-but-not-obviously-so guess. Always check the `(auto-detected: ...)` line / dry-run preview, especially for older or unusually-formatted PDFs.

**`--author-position {first,last}`** (default `first`, both modes) — for a multi-author paper, which author's surname to use. Any author-list source (`Author` metadata, ALL-CAPS byline, mixed-case byline) is split on `;`, `,`, `and`, and `&` — all four, since real PDFs use different separators depending on where the list came from — then either the first or last entry is used. Ignored if you pass `--author` yourself (`single` only).

```bash
python3 format_pdf_name.py single paper.pdf --tag Review                      # first author (default)
python3 format_pdf_name.py single paper.pdf --tag Review --author-position last  # last (e.g. senior/corresponding author)
```

This fixed a real bug, not just added an option: a metadata field like `"Gerhards; Hungerland; ...; Solov'yov"` (11 authors, semicolon-separated) wasn't being split at all before this fix — with no `,`/` and `/` & ` present, the whole string was treated as one blob and its very last word was returned, silently producing the *last* author's surname while claiming to use the first. `--author-position` now makes that choice explicit instead of it being an accident of which separator a given PDF happens to use.

*Known limitation:* `--author-position last` is fully reliable when the author list comes from PDF metadata, but less so for an old-style ALL-CAPS byline that wraps across multiple lines with middle initials (e.g. `"BERK HESS,1 HENK BEKKER, 2 HERMAN J. C. BERENDSEN,1"` on one line, `"JOHANNES G. E. M. FRAAIJE 1"` on the next) — detection only looks within a single line, so `last` can return a middle author instead of the true last one in that specific case. `first` (the default) is not affected.

**To fix it properly:** pass `--author`/`--year` yourself (`single`) — the safest option, since you're providing the real values instead of the placeholder ones.

**To force a rename anyway** (accepting the guess might be wrong, e.g. `Unknown 0000`): add `--force`. This always prints a warning banner first, and appends an entry to the tracking log either way:

```bash
python3 format_pdf_name.py single old_scan.pdf --force --apply
```

### In `batch` mode

`batch` has no per-file override, so uncertain files are handled in bulk:

- **Without `--force`** (default): every uncertain file is **skipped** (left completely untouched) and listed at the end.
- **With `--force`**: a warning banner is printed up front ("some filenames below may be WRONG"), uncertain files are renamed anyway, and the final summary separately calls out how many were renamed confidently vs. forced-despite-uncertain ("HIGH RISK — please verify") vs. skipped.

```bash
python3 format_pdf_name.py batch "/path/to/old_papers" --recursive
```
```
...
============================================================
Summary: 8 file(s) would be renamed confidently, 3 skipped (uncertain detection, --force not used), 0 would be renamed despite uncertain detection (--force).

3 file(s) left untouched (uncertain author/year, no --force):
  /path/to/old_papers/scan_1987.pdf
  /path/to/old_papers/no_metadata.pdf
  /path/to/old_papers/garbled_ocr.pdf

Uncertain-detection log: /path/to/old_papers/format_pdf_name_uncertain.log
```

Re-run the same command with `--force --apply` once you've decided the risk is acceptable (or fix the 3 flagged files individually with `single --author ... --year ...` instead, which is always safer).

### `format_pdf_name_uncertain.log`

Every skipped-due-to-uncertainty or forced-despite-uncertainty file — in **both** `single` and `batch` — is appended (never overwritten) to `format_pdf_name_uncertain.log`, written into the folder being processed (the scanned folder for `batch`, the file's own folder for `single`). Each line records a timestamp, what happened, and the file path(s), so you can always find and re-check these files later:

```
2026-08-06T15:26:16 | single: NOT renamed (uncertain detection) | /path/scan.pdf
2026-08-06T15:26:24 | batch: FORCED despite uncertain (--force) | /path/old.pdf -> /path/PDF_formatted/Unknown 0000.pdf
```

## Safety

- **Dry-run by default.** Nothing is renamed or moved until you pass `--apply`.
- Never overwrites an existing file — if the target name is already taken, that file is skipped and reported (this also protects against two different uncertain files both landing on the same `Unknown 0000.pdf` name under `--force`).
- Never deletes anything.
- Files with uncertain author/year detection are never silently renamed — see **Uncertain detection & `--force`** above.

## Requirements

`pdftotext` and `pdfinfo` (part of `poppler-utils`) must be on `PATH` for `batch` mode's auto-detection. `single` mode has no external dependency.
