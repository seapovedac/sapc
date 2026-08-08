#!/usr/bin/env python3
"""
format_pdf_name.py

Helper to rename PDF(s) into this library's naming convention, and
optionally move them into a destination folder (created if it doesn't
exist yet).

Conventions:
  Article/Review:  [prefix.]Surname YEAR [[TAG]] [(short comment)].pdf
                    prefix is any combination of 0, 00, 000, 0000, (+)
                    e.g. "000.Hoyer 2023 (ER-phagy).pdf", "(+).Mizushima 2018.pdf"
                    TAG is one recognized document-status tag in square
                    brackets — see TAG CHOICES below. At most one tag.
  Book:             Author(s) - Title (Publisher) (YEAR).pdf
                    or Author(s) - Title (YEAR).pdf if publisher unknown
  Book chapter:     Author - Chapter Title [Book Chapter] YEAR.pdf
  Thesis:           Surname YEAR [PhD Thesis].pdf  /  Surname YEAR [MSc Thesis].pdf

SQUARE BRACKETS vs PARENTHESES
    [Tag]      — reserved for a fixed, recognized document-status tag
                 (see TAG CHOICES). Exactly one per file, machine-readable.
    (comment)  — free-text topic/keyword comment, for humans searching the
                 library. Length is controlled by --detail.

TAG CHOICES (article type; pick at most one via --tag)
    Review, Mini Review, Editorial, Perspective, News & Views, Preprint, SI
    (SI = Supplementary Information / supporting material for another PDF)

Three modes:

1) single  — rename one PDF, metadata given explicitly on the command line.

    python3 format_pdf_name.py single "/path/to/file.pdf" --type article \
        --prefix 000 --author "Hoyer" --year 2023 --comment "ER-phagy"

    python3 format_pdf_name.py single "/path/to/review.pdf" --type article \
        --author "Zaffagnini" --year 2016 --tag Review --comment "selective autophagy"

    python3 format_pdf_name.py single "/path/to/si.pdf" --type article \
        --author "Zeno" --year 2018 --tag SI

    python3 format_pdf_name.py single "/path/to/book.pdf" --type book \
        --author "Andrew R Leach" --title "Molecular Modelling: Principles and Applications" \
        --publisher "Prentice Hall" --year 2001 --dest-folder "Book"

    python3 format_pdf_name.py single "/path/to/thesis.pdf" --type thesis \
        --author "Poveda" --year 2017 --thesis-level MSc

2) batch   — point at a folder full of PDFs; the script reads each PDF's
             text/metadata, guesses author/year and the document-status
             TAG (Review / Mini Review / Editorial / Perspective /
             News & Views / Preprint / SI — see detection rules in
             guess_tag()), and proposes a new name for every file.
             Existing priority prefixes (0/00/000/0000/(+)) and any
             "(comment)" already in the filename are preserved.
             Dry-run by default — nothing is touched until --apply.
             If --dest-folder isn't given, renamed files go into
             "<scanned folder>/PDF_formatted" (created automatically)
             instead of being renamed in place; pass --dest-folder "."
             to rename in place.

    python3 format_pdf_name.py batch "/path/to/messy_folder"
    python3 format_pdf_name.py batch "/path/to/messy_folder" --recursive --apply
    python3 format_pdf_name.py batch "/path/to/messy_folder" --dest-folder "IDP/New topic" --apply

3) --dest-folder (both modes) — moves the renamed file(s) into that folder.
   The path is relative to the PDF's current location (single) or the
   scanned folder (batch) unless given as absolute; created automatically
   if it doesn't exist yet (mkdir -p style). In batch mode this defaults
   to "PDF_formatted" when omitted (see above).

4) --detail LEVEL (both modes) — how much text goes inside the "(comment)"
   parentheses: 0=none, 1=short (default), 2=medium, 3=long/very detailed.

Add --apply to actually rename/move (otherwise it only prints a preview).
"""
import argparse
import os
import re
import subprocess
import sys
from datetime import datetime

PREFIX_RE = re.compile(r'^(?P<prefix>0{1,4}(?:\(\+\))?|\(\+\))[.\s]*')
VALID_PREFIX_RE = re.compile(r'^(0{1,4}(\(\+\))?|\(\+\))$')  # anchored: the ENTIRE --prefix value, not just a leading match
COMMENT_RE = re.compile(r'\(([^)]+)\)\s*$')
TAG_RE = re.compile(r'\[([^\]]+)\]')
YEAR_RE = re.compile(r'(19|20)\d{2}')

# Sentinel values returned by guess_surname()/guess_year() when detection
# fails outright (very old scans, garbled OCR, PDFs with no usable
# metadata, etc.) — used to decide whether a rename is "uncertain".
UNKNOWN_AUTHOR = "Unknown"
UNKNOWN_YEAR = "0000"
UNCERTAIN_LOG_NAME = "format_pdf_name_uncertain.log"

# Generic words that sometimes get mis-picked as an author surname by the
# byline-scanning fallback (e.g. from a paper's own title/subtitle, not an
# actual author list) — rejected so the caller falls back to UNKNOWN_AUTHOR
# instead of silently accepting an obviously-wrong "name".
NON_NAME_WORDS = {
    "unknown", "article", "review", "preprint", "journal", "university", "department",
    "abstract", "introduction", "results", "methods", "discussion", "references",
    "supporting", "information", "author", "authors", "untitled", "simulation",
    "simulations", "molecular", "biology", "chemistry", "physics", "science",
    "research", "letter", "letters", "report", "reports", "study", "studies",
    "analysis", "conclusion", "conclusions", "summary", "overview", "materials",
    "editorial", "perspective", "chapter", "supplementary", "appendix", "figure",
    "figures", "table", "tables", "data", "method", "model", "models", "theory",
}


def is_uncertain(author, year):
    return author == UNKNOWN_AUTHOR or year == UNKNOWN_YEAR


def log_uncertain(log_dir, entries):
    """Append (status, old_path, new_path_or_None) rows to a tracking log
    in log_dir, so uncertain/forced renames can be found again later.
    Returns the log file path."""
    log_path = os.path.join(log_dir, UNCERTAIN_LOG_NAME)
    ts = datetime.now().isoformat(timespec="seconds")
    with open(log_path, "a", encoding="utf-8") as f:
        for status, old, new in entries:
            line = f"{ts} | {status} | {old}"
            if new:
                line += f" -> {new}"
            f.write(line + "\n")
    return log_path

# Recognized document-status tags for --type article. Order matters for
# batch auto-detection: earlier entries win when more than one keyword
# matches (e.g. a paper can mention "review" while actually being an
# Editorial about reviews — Editorial should win).
TAG_CHOICES = ["SI", "Editorial", "Perspective", "News & Views", "Mini Review", "Review", "Preprint"]

# --detail controls how much text is allowed inside the parenthetical
# comment: 0 = no comment at all, 1 (default) = a single meaningful
# keyword, 2 = several meaningful keywords, 3 = long / very detailed
# (full text, unchanged, just capped at a sane length). Values are max
# keyword counts for levels 1-2; level 3 keeps the original phrasing.
DETAIL_WORD_LIMITS = {0: 0, 1: 1, 2: 4, 3: None}
# When the comment is a "Keywords: X; Y; Z"-style list (semicolon-
# separated), select whole phrases instead — "Molecular dynamics" is one
# keyword, not two words to independently truncate.
DETAIL_PHRASE_LIMITS = {0: 0, 1: 1, 2: 2, 3: None}
DETAIL_CHAR_CAP = {0: 0, 1: 20, 2: 60, 3: 140}

# Common function words filtered out of the (comment) at --detail 1/2 so
# the result reads as meaningful keywords ("LAMMPS flexible simulation
# tool") instead of an arbitrary word-count slice that can land on a bare
# article/preposition ("LAMMPS - a flexible"). Deliberately NOT applied at
# level 3, which keeps the original, naturally-phrased text.
STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "for", "to", "and", "or", "with", "using", "via",
    "from", "as", "is", "are", "was", "were", "be", "been", "being", "that", "which", "by",
    "at", "into", "onto", "under", "over", "per", "its", "their", "our", "this", "these",
    "those", "not", "no", "but", "if", "then", "than", "so", "such", "also", "between",
    "among", "within", "without", "across", "toward", "towards", "about", "after", "before",
    "during", "through", "can", "could", "may", "might", "will", "would", "shall", "should",
}


def _tokenize_words(text):
    """Split into words, dropping standalone punctuation tokens (e.g. a
    lone "-" or ":" from "LAMMPS - a flexible..." that would otherwise eat
    a word slot without contributing anything readable)."""
    return [w for w in text.split() if re.search(r'[A-Za-z0-9]', w)]


def _keyword_words(words):
    """Words with stopwords and stray trailing punctuation removed, order
    preserved. Falls back to the original words if filtering would leave
    nothing (e.g. a comment that's ALL stopwords/punctuation)."""
    kept = [w.strip(",.;:") for w in words if w.strip(",.;:()[]").lower() not in STOPWORDS]
    return kept or words


def apply_detail_level(comment, level):
    """Trim a parenthetical comment down to the requested detail level."""
    comment = (comment or "").strip()
    if not comment or level == 0:
        return ""

    cap = DETAIL_CHAR_CAP[level]

    if ';' in comment:
        # Already a curated "Keywords: X; Y; Z" list — treat each phrase
        # as one unit rather than word-splitting inside it.
        phrases = [p.strip(" .") for p in comment.split(';') if p.strip(" .")]
        if level == 3:
            text = "; ".join(phrases)
        else:
            limit = DETAIL_PHRASE_LIMITS[level]
            text = "; ".join(phrases[:limit])
    else:
        words = _tokenize_words(comment)
        if level == 3:
            # Keep the natural, full phrasing — just a sanity length cap.
            text = " ".join(words)
        else:
            limit = DETAIL_WORD_LIMITS[level]
            text = " ".join(_keyword_words(words)[:limit])

    if len(text) > cap:
        text = text[:cap].rstrip()
    return text


def build_article_name(prefix, author, year, tag, comment, detail=1):
    comment = apply_detail_level(comment, detail)
    name = ""
    if prefix:
        name += f"{prefix}."
    name += f"{author} {year}"
    if tag:
        name += f" [{tag}]"
    if comment:
        name += f" ({comment})"
    return name + ".pdf"


def build_book_name(author, title, publisher, year):
    if publisher:
        return f"{author} - {title} ({publisher}) ({year}).pdf"
    return f"{author} - {title} ({year}).pdf"


def build_chapter_name(author, title, year):
    return f"{author} - {title} [Book Chapter] {year}.pdf"


def build_thesis_name(author, year, level):
    return f"{author} {year} [{level} Thesis].pdf"


def ensure_dest_folder(pdf_path, dest_folder):
    """Resolve dest_folder (relative to the PDF's current dir unless absolute)
    and create it if missing. Returns the absolute destination directory."""
    if os.path.isabs(dest_folder):
        target = dest_folder
    else:
        target = os.path.join(os.path.dirname(os.path.abspath(pdf_path)), dest_folder)
    os.makedirs(target, exist_ok=True)
    return target


def finalize(old_path, new_name, dest_folder, apply_changes):
    old_dir = os.path.dirname(os.path.abspath(old_path))
    target_dir = ensure_dest_folder(old_path, dest_folder) if dest_folder else old_dir
    new_path = os.path.join(target_dir, new_name)

    print(f"Old: {old_path}")
    print(f"New: {new_path}")

    if not apply_changes:
        print("(dry-run)\n")
        return

    if os.path.exists(new_path) and os.path.abspath(new_path) != os.path.abspath(old_path):
        print(f"SKIPPED — target already exists: {new_path}\n")
        return

    os.makedirs(target_dir, exist_ok=True)
    os.rename(old_path, new_path)
    print(f"Done -> {new_path}\n")


# --------------------------------------------------------------------------
# single mode — any of author/year/tag/title/prefix/comment you don't pass
# explicitly is auto-detected from the PDF itself (same engine as batch).
# --------------------------------------------------------------------------

def cmd_single(args):
    if not os.path.isfile(args.path):
        sys.exit(f"File not found: {args.path}")

    if args.prefix and not VALID_PREFIX_RE.match(args.prefix):
        hint = ""
        tag_match = next((t for t in TAG_CHOICES if t.lower() == args.prefix.lower()), None)
        if tag_match or args.prefix.lower() in {"review", "si", "preprint"}:
            hint = f" Looks like you meant --tag {tag_match or args.prefix.capitalize()} (a document-status tag), not --prefix."
        sys.exit(
            f"Invalid --prefix {args.prefix!r} — --prefix is ONLY for the priority marker "
            f"(0, 00, 000, 0000, (+), or a combo like 000(+)), not free text.{hint}"
        )

    stem = os.path.basename(args.path)[:-4]
    info = pdf_info(args.path)
    text = pdf_first_page_text(args.path)

    prefix = args.prefix
    if not prefix:
        prefix_m = PREFIX_RE.match(stem)
        prefix = prefix_m.group('prefix') if prefix_m else ''

    year = args.year or guess_year(info, text)

    if args.type in ("article", "thesis"):
        author = args.author or guess_surname(info.get("Author", ""), text, args.author_position)
    else:  # book, chapter — keep the full author list, not just a surname
        author = args.author or info.get("Author", "").strip() or guess_surname("", text, args.author_position)

    if args.type == "article":
        if args.tag == "None":
            tag = ""
        elif args.tag:
            tag = args.tag
        else:
            tag = guess_tag(stem, text)
        comment = args.comment
        if not comment:
            comment_m = COMMENT_RE.search(stem)
            existing_comment = comment_m.group(1) if comment_m else ''
            comment = guess_comment(existing_comment, info, text)
        new_name = build_article_name(prefix, author, year, tag, comment, args.detail)
    elif args.type == "book":
        title = args.title or info.get("Title", "").strip()
        if not title:
            sys.exit("Could not auto-detect a title from the PDF metadata — pass --title explicitly")
        new_name = build_book_name(author, title, args.publisher, year)
    elif args.type == "chapter":
        title = args.title or info.get("Title", "").strip()
        if not title:
            sys.exit("Could not auto-detect a title from the PDF metadata — pass --title explicitly")
        new_name = build_chapter_name(author, title, year)
    else:  # thesis
        new_name = build_thesis_name(author, year, args.thesis_level)

    if not (args.author and args.year):
        print(f"(auto-detected: author={author!r}, year={year!r})")

    # Uncertain = a field we had to auto-detect (not one you passed
    # explicitly) came back as the "couldn't figure it out" sentinel —
    # typical for very old scans, garbled OCR, or PDFs with no metadata.
    uncertain = (not args.author and author == UNKNOWN_AUTHOR) or (not args.year and year == UNKNOWN_YEAR)
    log_dir = os.path.dirname(os.path.abspath(args.path)) or "."

    if uncertain and not args.force:
        print("NOT renamed — author/year could not be confidently auto-detected "
              "(common for very old articles, scans, or PDFs with no metadata).")
        print("Pass --author/--year explicitly, or --force to rename anyway (results may be wrong).\n")
        log_path = log_uncertain(log_dir, [("single: NOT renamed (uncertain detection)", args.path, None)])
        print(f"Logged to: {log_path}")
        return

    if uncertain and args.force:
        print("WARNING: proceeding with --force despite uncertain author/year detection — "
              "this filename may be WRONG. Double-check it afterwards.\n")
        log_uncertain(log_dir, [("single: FORCED despite uncertain detection (--force)", args.path, new_name)])

    finalize(args.path, new_name, args.dest_folder, args.apply)


# --------------------------------------------------------------------------
# batch mode — auto-detect author/year/tag from PDF content
# --------------------------------------------------------------------------

def pdf_first_page_text(path):
    try:
        out = subprocess.run(["pdftotext", "-l", "1", path, "-"], capture_output=True, text=True, timeout=30)
        return out.stdout or ""
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def pdf_info(path):
    try:
        out = subprocess.run(["pdfinfo", path], capture_output=True, text=True, timeout=30)
        info = {}
        for line in out.stdout.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                info[k.strip()] = v.strip()
        return info
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {}


def _all_caps_word(word):
    """True for tokens like 'HESS' or 'J.' — an all-uppercase name/initial,
    as opposed to 'A' from a title fragment (too short to be reliable) or
    a lowercase/mixed-case word."""
    return bool(re.fullmatch(r"[A-Z][A-Z'\-]*\.?", word)) and len(word.strip(".'-")) > 1


# Splits an author-list string into individual author names. Real-world
# metadata/bylines use ALL of these as separators depending on the source
# (';' is common in PDF Author metadata, ',' in plain bylines, 'and'/'&'
# before the final name) — using only some of them was the root cause of
# a real bug: a metadata field like "Gerhards; Hungerland; ...; Solov'yov"
# wasn't split at all (no ',', ' and ', or ' & ' present), so the whole
# blob was treated as one "name" and its very last word got returned —
# which happened to be the LAST author's surname, not the first.
AUTHOR_SEP_RE = re.compile(r';|,|\band\b|&', re.IGNORECASE)


def _split_authors(text):
    parts = [p.strip() for p in AUTHOR_SEP_RE.split(text)]
    return [p for p in parts if p and not p.isdigit()]


def guess_surname(pdfinfo_author, first_page_text, position="first"):
    """position: 'first' (default) or 'last' — which author in a
    multi-author list/byline to take the surname from."""
    if pdfinfo_author:
        authors = _split_authors(pdfinfo_author)
        if authors:
            chosen = authors[0] if position == "first" else authors[-1]
            parts = chosen.split()
            if parts:
                candidate = parts[-1].strip(",.")
                if candidate.lower() not in NON_NAME_WORDS:
                    return candidate

    lines = first_page_text.splitlines()[:20]

    # 1) ALL-CAPS byline, e.g. "BERK HESS,1 HENK BEKKER, 2 ..." — very
    # common in older papers, and a much stronger signal than a generic
    # Title-Case two-word match (which can false-positive on the paper's
    # own title/subtitle instead of the real author list).
    for line in lines:
        line = line.strip()
        if not line or len(line) > 200:
            continue
        chunks = _split_authors(re.sub(r'\d+', ' ', line))
        candidates = []
        for chunk in chunks:
            words = chunk.split()
            if len(words) >= 2 and all(_all_caps_word(w) for w in words):
                candidates.append(words[-1].strip(".'-"))
        if candidates:
            candidate = candidates[0] if position == "first" else candidates[-1]
            if candidate.lower() not in NON_NAME_WORDS and len(candidate) > 1:
                return candidate.capitalize()

    # 2) mixed-case "Firstname Lastname" byline fallback — split the line
    # into per-author chunks first (so a long multi-author byline is
    # handled correctly), then pick from whichever chunks actually look
    # like a name.
    for line in lines:
        line = line.strip()
        if not line or len(line) > 300:
            continue
        chunks = _split_authors(line)
        candidates = []
        for chunk in chunks:
            if re.match(r'^[A-Z][a-zà-ÿ]+(?:\s[A-Z]\.?)*\s[A-Z][a-zà-ÿ]+', chunk):
                parts = chunk.split()
                candidates.append(parts[-1].strip(",."))
        if candidates:
            candidate = candidates[0] if position == "first" else candidates[-1]
            if candidate.lower() not in NON_NAME_WORDS:
                return candidate

    return UNKNOWN_AUTHOR


KEYWORDS_SECTION_RE = re.compile(
    r'key\s*-?\s*words?\s*[:\-]\s*(.+?)(?:\n\s*\n|\Z)', re.IGNORECASE | re.DOTALL,
)


def extract_keywords_section(first_page_text):
    """Many papers list their own author-curated keywords on the first
    page — a much better comment source than blindly slicing the title,
    since it's already a hand-picked list of topic terms. Formatting
    varies: "Keywords: X; Y; Z" on one line, "Keywords: X, Y, Z", or one
    keyword per line — so phrase boundaries (\\n / ; / ,) are found FIRST,
    before any whitespace collapsing, or the one-per-line style would be
    silently merged into unsplittable mush."""
    m = KEYWORDS_SECTION_RE.search(first_page_text[:3000])
    if not m:
        return ""
    raw_parts = re.split(r'[\n;]|,(?!\s*\d)', m.group(1))
    phrases = []
    for p in raw_parts:
        p = re.sub(r'\s+', ' ', p).strip(' .')
        if p:
            phrases.append(p)
    if not phrases:
        return ""
    joined = "; ".join(phrases)
    # Keywords sections are normally short; if this ran on into body text
    # (no blank line found before end-of-search-window), don't use it.
    if len(joined) > 200:
        return ""
    return joined


def guess_comment(existing_comment, pdfinfo_map, first_page_text=""):
    """Fill in a topic comment when the filename doesn't already have one.
    Priority: the paper's own "Keywords:" line (best — author-curated),
    then its Title metadata. --detail then trims the result down."""
    if existing_comment:
        return existing_comment

    keywords = extract_keywords_section(first_page_text) if first_page_text else ""
    if keywords:
        return keywords

    title = pdfinfo_map.get("Title", "").strip()
    # Skip obviously useless/placeholder titles (LaTeX build artifacts,
    # generic scanner output, journal boilerplate re-typed as "Title")
    if not title or re.match(r'^(untitled|microsoft word|.*\.(dvi|docx?|tex))$', title, re.IGNORECASE):
        return ""
    return title


def guess_year(pdfinfo_map, first_page_text):
    m = YEAR_RE.search(first_page_text[:2000])
    if m:
        return m.group(0)
    creation = pdfinfo_map.get("CreationDate", "")
    m = YEAR_RE.search(creation)
    if m:
        return m.group(0)
    return "0000"


def guess_tag(stem, first_page_text):
    """Best-effort detection of a single document-status tag.

    Checked in priority order (TAG_CHOICES) so a more specific label
    (e.g. Editorial) wins over a loosely-matching generic one (Review).
    Filename hints (e.g. a trailing "SI"/"_si_" token, or an existing
    "[Tag]" already in the name) are checked first since they're the
    most reliable signal; PDF content is the fallback.
    """
    # 1) an existing bracket tag in the current filename, if it's one we recognize
    m = TAG_RE.search(stem)
    if m and m.group(1) in TAG_CHOICES:
        return m.group(1)

    # 2) filename hints for supplementary information — "SI" as its own
    # token, bounded by spaces/underscores/hyphens/dots/parentheses (so it
    # catches both "... SI.pdf" and "... (SI).pdf" without matching "SI"
    # inside an unrelated word)
    if re.search(r'(^|[ _\-.(])si([ _\-.)]|$)', stem, re.IGNORECASE) or re.search(r'supp?(orting|lementary)', stem, re.IGNORECASE):
        return "SI"

    # 3) SI as the document's OWN title, e.g. a standalone SI PDF usually
    # opens with "Supporting Information" / "Supplementary Materials for..."
    # as its first line. This must NOT match a normal article that merely
    # *mentions* "the Supporting Information files" in its own body text
    # (a very common boilerplate line in Data Availability statements) —
    # so it only looks at the first couple of non-empty lines, and never
    # fires if the page identifies itself as a full article/review.
    top_lines = [l.strip() for l in first_page_text.splitlines() if l.strip()][:3]
    top_block = "\n".join(top_lines)
    looks_like_full_article = re.search(
        r'\b(research article|review article|original article|received:|accepted:)\b',
        first_page_text[:600], re.IGNORECASE,
    )
    if not looks_like_full_article and re.search(
        r'^(supporting information|supplementary (information|material|materials|appendix|data|methods|figures?|tables?|notes?))\b',
        top_block, re.IGNORECASE,
    ):
        return "SI"

    head = first_page_text[:1500]

    if re.search(r'\beditorial\b', head, re.IGNORECASE):
        return "Editorial"
    if re.search(r'\bperspective\b', head, re.IGNORECASE):
        return "Perspective"
    if re.search(r'news\s*&?\s*views', head, re.IGNORECASE):
        return "News & Views"
    if re.search(r'\bmini[\s-]?review\b', head, re.IGNORECASE):
        return "Mini Review"
    if re.search(r'\breview\b', head, re.IGNORECASE):
        return "Review"
    if re.search(r'biorxiv|medrxiv|this version posted|preprint', head, re.IGNORECASE):
        return "Preprint"
    return ""


def analyze_pdf_fields(path, no_tag=False, author_position="first"):
    """Compute every field format_pdf_name would use for this PDF, plus
    whether author/year detection was uncertain (couldn't be determined)."""
    stem = os.path.basename(path)[:-4]
    prefix_m = PREFIX_RE.match(stem)
    prefix = prefix_m.group('prefix') if prefix_m else ''
    comment_m = COMMENT_RE.search(stem)
    existing_comment = comment_m.group(1) if comment_m else ''

    info = pdf_info(path)
    text = pdf_first_page_text(path)
    author = guess_surname(info.get("Author", ""), text, author_position)
    year = guess_year(info, text)
    tag = "" if no_tag else guess_tag(stem, text)
    comment = guess_comment(existing_comment, info, text)

    return {
        "prefix": prefix, "author": author, "year": year, "tag": tag, "comment": comment,
        "uncertain": is_uncertain(author, year),
    }


# Default destination subfolder for batch mode when --dest-folder isn't
# given: renamed files land in <scanned folder>/PDF_formatted instead of
# being renamed in place. Pass --dest-folder "." to keep the old
# rename-in-place behavior instead.
DEFAULT_BATCH_DEST_FOLDER = "PDF_formatted"


def cmd_batch(args):
    if not os.path.isdir(args.folder):
        sys.exit(f"Folder not found: {args.folder}")

    if args.recursive:
        pdf_paths = []
        for dirpath, _, filenames in os.walk(args.folder):
            for fn in filenames:
                if fn.lower().endswith(".pdf"):
                    pdf_paths.append(os.path.join(dirpath, fn))
    else:
        pdf_paths = [os.path.join(args.folder, fn) for fn in os.listdir(args.folder) if fn.lower().endswith(".pdf")]

    if not pdf_paths:
        print("No PDFs found.")
        return

    if args.dest_folder:
        dest_folder = args.dest_folder
    else:
        # Resolve to a single absolute folder up front so every file (even
        # from different subfolders under --recursive) lands in the same
        # place, instead of getting one "PDF_formatted" per subfolder.
        dest_folder = os.path.join(os.path.abspath(args.folder), DEFAULT_BATCH_DEST_FOLDER)
        print(f"No --dest-folder given: renamed files will be placed in {dest_folder}\n")

    if args.force:
        print("WARNING: --force is enabled. Some author/year assignments could not be confidently\n"
              "auto-detected (common for very old articles, scans, or PDFs with no metadata) and\n"
              "will be applied anyway — some filenames below may be WRONG. Review them afterwards.\n")

    print(f"Found {len(pdf_paths)} PDF(s). Mode: {'APPLY' if args.apply else 'DRY-RUN'}\n")

    renamed = []       # (old, new) confidently renamed
    skipped = []       # old paths not renamed due to uncertain detection
    risky_forced = []  # (old, new) renamed anyway via --force despite uncertain detection

    for path in sorted(pdf_paths):
        fields = analyze_pdf_fields(path, args.no_tag, args.author_position)
        new_name = build_article_name(fields["prefix"], fields["author"], fields["year"],
                                       fields["tag"], fields["comment"], args.detail)

        if fields["uncertain"] and not args.force:
            print(f"Old: {path}")
            print("SKIPPED — author/year could not be confidently auto-detected. "
                  "Use --force to rename anyway, or fix this file individually with `single`.\n")
            skipped.append(path)
            continue

        target_dir = ensure_dest_folder(path, dest_folder) if dest_folder else os.path.dirname(os.path.abspath(path))
        new_path = os.path.join(target_dir, new_name)
        if fields["uncertain"] and args.force:
            risky_forced.append((path, new_path))
        else:
            renamed.append((path, new_path))

        finalize(path, new_name, dest_folder, args.apply)

    verb = "renamed" if args.apply else "would be renamed"
    print("=" * 60)
    print(f"Summary: {len(renamed)} file(s) {verb} confidently, "
          f"{len(skipped)} skipped (uncertain detection, --force not used), "
          f"{len(risky_forced)} {verb} despite uncertain detection (--force).")

    if risky_forced:
        print(f"\n{len(risky_forced)} file(s) {verb} with a HIGH RISK of a wrong name — please verify:")
        for old, new in risky_forced:
            print(f"  {old} -> {new}")

    if skipped:
        print(f"\n{len(skipped)} file(s) left untouched (uncertain author/year, no --force):")
        for old in skipped:
            print(f"  {old}")

    log_entries = [("batch: SKIPPED (uncertain, no --force)", p, None) for p in skipped]
    log_entries += [("batch: FORCED despite uncertain (--force)", old, new) for old, new in risky_forced]
    if log_entries:
        log_path = log_uncertain(os.path.abspath(args.folder), log_entries)
        print(f"\nUncertain-detection log: {log_path}")

    if not args.apply:
        print("\nNothing was changed — re-run with --apply once the proposed names look right.")


MENU = """
format_pdf_name.py — rename/move PDF(s) into the library's naming convention

Two modes:

  single   Rename ONE PDF. --type is the only required flag — author, year,
           tag, title, prefix and comment are all auto-detected from the
           PDF if you don't pass them explicitly. Pass any of them to
           override the guess.

  batch    Point at a FOLDER of PDFs. The script reads each file's text/
           metadata to guess author, year, and a document-status TAG
           (Review, Mini Review, Editorial, Perspective, News & Views,
           Preprint, or SI), then proposes a new name for every PDF in
           the folder. Nothing is touched until you re-run with --apply
           (dry-run by default). Renamed files go into a new
           "PDF_formatted" subfolder by default — pass --dest-folder "."
           to rename in place instead.

Both modes accept --dest-folder to move the renamed file(s) into a
folder — existing or not; it is created automatically if missing.
(batch mode defaults to "<scanned folder>/PDF_formatted" when omitted.)

Both modes accept --detail {0,1,2,3} (default 1) to control how much
text goes inside the "(comment)" parentheses:
  0 = no parentheses at all   2 = medium detail
  1 = short (default)         3 = long / very detailed

[Square brackets] are reserved for one recognized document-status TAG
(Review, Mini Review, Editorial, Perspective, News & Views, Preprint,
SI, Book Chapter, PhD Thesis, MSc Thesis, ...). (Parentheses) are for
free-text topic comments. See --tag in `single -h` for the full list.

Quick examples:
  python3 format_pdf_name.py single "/path/file.pdf" --type article \\
      --author Hoyer --year 2023 --tag Review --comment "ER-phagy"

  python3 format_pdf_name.py single "/path/si.pdf" --type article \\
      --author Zeno --year 2018 --tag SI

  python3 format_pdf_name.py batch "/path/to/messy_folder" --recursive
  python3 format_pdf_name.py batch "/path/to/messy_folder" --recursive \\
      --dest-folder "IDP/New topic" --apply

Full details for either mode:
  python3 format_pdf_name.py single -h
  python3 format_pdf_name.py batch -h
"""


def main():
    p = argparse.ArgumentParser(
        prog="format_pdf_name.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="mode")

    ps = sub.add_parser(
        "single",
        help="Rename ONE PDF with explicitly given metadata (author/year/type/tag/...)",
        description=(
            "Rename a single PDF using metadata you supply on the command line.\n\n"
            "Naming conventions applied per --type:\n"
            "  article  [prefix.]Surname YEAR [[TAG]] [(comment)].pdf\n"
            "  book     Author(s) - Title (Publisher) (YEAR).pdf\n"
            "  chapter  Author - Chapter Title [Book Chapter] YEAR.pdf\n"
            "  thesis   Surname YEAR [PhD Thesis].pdf  /  Surname YEAR [MSc Thesis].pdf\n\n"
            "[Square brackets] hold one recognized document-status TAG (see --tag).\n"
            "(Parentheses) hold a free-text topic comment (see --comment/--detail).\n\n"
            "--author, --year, --tag, --comment, --title and --prefix are all OPTIONAL:\n"
            "anything you don't pass is auto-detected from the PDF's metadata/text\n"
            "(for --prefix/--comment, from the file's current name), the same engine\n"
            "batch mode uses. Pass a flag explicitly whenever you want to override the\n"
            "guess or already know the value.\n\n"
            "Dry-run by default: prints the Old -> New preview only. Add --apply to\n"
            "actually rename (and, with --dest-folder, move) the file."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ps.add_argument("path", help="Path to the PDF to rename")
    ps.add_argument("--type", default="article", choices=["article", "book", "chapter", "thesis"],
                     help="Document type — determines which naming template is used. Default: article "
                          "(the most common case in this library).")
    ps.add_argument("--prefix", default="",
                     help="Priority prefix to prepend: 0, 00, 000, 0000, (+), or a combo like 000(+) (article only). "
                          "Default: reused from the file's current name if it already has one.")
    ps.add_argument("--author", default="",
                     help="Surname (article/thesis) or full author list (book/chapter). "
                          "Default: auto-detected from the PDF's metadata/first page.")
    ps.add_argument("--author-position", default="first", choices=["first", "last"],
                     help="When auto-detecting from a multi-author list, use the FIRST author's "
                          "surname (default) or the LAST author's (e.g. to pick the senior/corresponding "
                          "author instead). Ignored if --author is given explicitly.")
    ps.add_argument("--year", default="",
                     help="Publication year, e.g. 2023. Default: auto-detected from the PDF.")
    ps.add_argument("--tag", default="", choices=[""] + TAG_CHOICES + ["None"],
                     help="Document-status tag shown in [brackets] (article only). One of: "
                          + ", ".join(TAG_CHOICES) + ". SI = Supplementary Information. "
                          "Default: auto-detected from the PDF's content. "
                          "Pass --tag None to force NO tag and skip auto-detection entirely.")
    ps.add_argument("--comment", default="",
                     help="Short parenthetical comment/topic keywords (article only). "
                          "Default: reused from the file's current name if it already has one.")
    ps.add_argument("--detail", type=int, default=1, choices=[0, 1, 2, 3],
                     help="How much of --comment ends up in the (parentheses): "
                          "0=no parentheses at all, 1=short/few words (default), "
                          "2=medium, 3=long/very detailed. Article only.")
    ps.add_argument("--title", default="",
                     help="Book/chapter title. Default: auto-detected from the PDF's Title metadata "
                          "(falls back to requiring --title if metadata has none).")
    ps.add_argument("--publisher", default="", help="Book publisher; omitted from the name if not given")
    ps.add_argument("--thesis-level", default="PhD", choices=["PhD", "MSc"], help="Thesis level (thesis only)")
    ps.add_argument("--dest-folder", default="",
                     help="Move the renamed file into this folder, relative to the PDF's current location "
                          "unless given as an absolute path. Created automatically if it doesn't exist.")
    ps.add_argument("--force", action="store_true",
                     help="If author/year couldn't be confidently auto-detected (and you didn't pass "
                          "--author/--year yourself), rename anyway instead of refusing. Prints a warning "
                          "first and logs the file to " + UNCERTAIN_LOG_NAME + " for later review.")
    ps.add_argument("--apply", action="store_true", help="Actually rename/move. Without this flag: preview only.")
    ps.set_defaults(func=cmd_single)

    pb = sub.add_parser(
        "batch",
        help="Auto-detect author/year/tag and reformat EVERY PDF in a folder",
        description=(
            "Scan a folder of PDFs and propose a standardized article-style name for\n"
            "each one: [prefix.]Surname YEAR [[TAG]] [(comment)].pdf\n\n"
            "Author is guessed from the PDF's Author metadata (falls back to scanning\n"
            "the first page for a byline). Year is guessed from the first page text,\n"
            "falling back to the PDF's creation date. The TAG is guessed in this\n"
            "priority order: SI > Editorial > Perspective > News & Views > Mini Review\n"
            "> Review > Preprint (first match wins; filename hints like a trailing 'SI'\n"
            "or an existing recognized '[Tag]' are checked before PDF content). Any\n"
            "existing priority prefix (0/00/000/0000/(+)) and any existing\n"
            "'(comment)' in the current filename are preserved.\n\n"
            "If --dest-folder is not given, renamed files are moved into\n"
            "'<scanned folder>/PDF_formatted' (created automatically) rather than\n"
            "renamed in place — this keeps originals-vs-renamed easy to tell apart.\n"
            "Pass --dest-folder '.' to rename in place instead.\n\n"
            "This is a heuristic, best-effort guess — ALWAYS review the dry-run output\n"
            "before adding --apply, since PDF metadata can list a corresponding author\n"
            "instead of the first author, or omit a year entirely."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    pb.add_argument("folder", help="Folder containing PDFs to reformat")
    pb.add_argument("--recursive", action="store_true", help="Also process PDFs in subfolders")
    pb.add_argument("--detail", type=int, default=1, choices=[0, 1, 2, 3],
                     help="How much of each file's existing (comment) is kept: "
                          "0=drop parentheses entirely, 1=short/few words (default), "
                          "2=medium, 3=long/very detailed.")
    pb.add_argument("--no-tag", action="store_true",
                     help="Never guess a [Tag] — leave every file's tag blank. "
                          "By default, tags (Review/SI/Preprint/...) are auto-detected.")
    pb.add_argument("--author-position", default="first", choices=["first", "last"],
                     help="When auto-detecting from a multi-author list, use each file's FIRST "
                          "author's surname (default) or its LAST author's. Applies to every file "
                          "in this batch run (no per-file override — fix an individual file "
                          "afterwards with `single --author ...` if needed).")
    pb.add_argument("--dest-folder", default="",
                     help="Move all renamed files into this folder, relative to the scanned folder "
                          "unless given as an absolute path. Created automatically if missing. "
                          "Default when omitted: '<scanned folder>/PDF_formatted'. "
                          "Pass '.' to rename in place instead (no move).")
    pb.add_argument("--force", action="store_true",
                     help="Rename files even when author/year couldn't be confidently auto-detected "
                          "(by default those are skipped and listed at the end, untouched). Prints a "
                          "warning banner up front and logs every forced/skipped file to " +
                          UNCERTAIN_LOG_NAME + " for later review.")
    pb.add_argument("--apply", action="store_true", help="Actually rename/move. Without this flag: preview only.")
    pb.set_defaults(func=cmd_batch)

    args = p.parse_args()

    if args.mode is None:
        print(MENU)
        return

    args.func(args)


if __name__ == "__main__":
    main()
