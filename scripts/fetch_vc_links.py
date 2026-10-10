#!/usr/bin/env python3
"""
Check Delhi District Courts' 12 VC-links PDFs for updates and refresh
data/delhi-court-vc-links.csv for any district whose PDF changed.

WHAT THIS DOES
For each of the 12 district court complexes, fetches the court's own
"VC Links" document-listing page, finds the current PDF, and compares it
against data/vc-links-manifest.json (what we last saw). For any district
whose PDF is new, downloads it and re-parses the judge/designation/email/
VC-link table with pdfplumber, then replaces just that district's rows in
data/delhi-court-vc-links.csv. Districts that didn't change are left alone.

WHY MANIFEST + PDF-FILENAME DATES, NOT THE PAGE'S OWN "updated on" LABEL
The on-page date label has been observed to lag behind the actual file
(e.g. North district's page said 14/07/2026 while the PDF itself, per its
own filename, was uploaded 2026-08-08). The filename encodes the true
upload date (uploads/YYYY/MM/YYYYMMDDnn.pdf), so that's what's compared.

BEST-EFFORT PARSING - PR REVIEW IS STILL REQUIRED
These are 12 independently-run district sites and their PDF table layouts
genuinely differ: some have a separate "Designation" column, some merge
name and designation into a single cell (comma- or newline-separated),
column counts range from 7 to 9. This script handles the common shapes it
has been tested against, but if a district's parse looks low-confidence
(too few rows, no recognizable header, or no plausible VC-link URLs found)
it is deliberately left untouched and flagged in the PR body instead of
overwriting good data with a bad parse. Always spot-check the diff for any
district that changed before merging.

REMOVABILITY
This script and its companion workflow (.github/workflows/fetch-vc-links.yml)
follow the same pattern as scripts/fetch_ecourts_judgments.py: fully
optional, always produces a reviewable PR, never auto-merges.
  - To pause: disable the workflow from the Actions tab.
  - To remove permanently: delete this file, the workflow file, and
    data/vc-links-manifest.json. data/delhi-court-vc-links.csv itself is
    just a data file and stays usable either way.
"""

import csv
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request

try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = ssl.create_default_context()

try:
    import pdfplumber
except ImportError:
    sys.exit("pdfplumber is required: pip install pdfplumber")

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
CSV_PATH = os.path.join(DATA_DIR, "delhi-court-vc-links.csv")
MANIFEST_PATH = os.path.join(DATA_DIR, "vc-links-manifest.json")
REPORT_PATH = os.path.join(DATA_DIR, "..", "vc-links-update-report.md")

CSV_HEADER = [
    "Judge Name", "Designation", "District/Complex", "Email",
    "VC Link", "PDF Last Updated", "Source Page (official)",
]

# district label -> official "VC links" listing page(s) on that district's own site
DISTRICT_SOURCES = {
    "Central - Tis Hazari": "https://centraldelhi.dcourts.gov.in/document-category/central-district-vc-links/",
    "Central - Rouse Avenue": "https://centraldelhi.dcourts.gov.in/document-category/rouse-avenue-district-court-vc-links/",
    "West": "https://westdelhi.dcourts.gov.in/document-category/vc-links/",
    "East - Karkardooma": "https://eastdelhi.dcourts.gov.in/document-category/vc-links/",
    "North East - Karkardooma": "https://northeast.dcourts.gov.in/document-category/vc-links/",
    "Shahdara - Karkardooma": "https://shahdara.dcourts.gov.in/document-category/vc-links/",
    "New Delhi - Patiala House": "https://newdelhi.dcourts.gov.in/document-category/vc-links/",
    "North West - Rohini": "https://rohini.dcourts.gov.in/document-category/vc-links/",
    "North - Rohini": "https://northdelhi.dcourts.gov.in/document-category/vc-links/",
    "South West - Dwarka": "https://southwestdelhi.dcourts.gov.in/document-category/vc-links/",
    "South East - Saket": "https://southeastdelhi.dcourts.gov.in/document-category/vc-links/",
    "South - Saket": "https://southdelhi.dcourts.gov.in/document-category/vc-links/",
}

# nearby-text patterns that mean "this PDF link isn't a VC-links list"
# (e.g. South district's page also lists an unrelated coordinator-appointment order)
NON_VC_LINK_HINTS = re.compile(r"appointment|coordinator|order regarding", re.I)

PDF_HREF_RE = re.compile(r'href="([^"]+\.pdf)"', re.I)
FILENAME_DATE_RE = re.compile(r"/uploads/(\d{4})/(\d{2})/\1\2(\d{2})\d+\.pdf$")
PAGE_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")

HEADER_KEYWORDS = {
    "name": ("judicial officer", "judicialofficer"),
    "designation": ("designation",),
    "email": ("email", "e-mail", "mail id"),
    "url": ("url", "hyperlink", "video conferencing link"),
}

MIN_CONFIDENT_ROWS = 8


def fetch(url, binary=False, retries=2):
    # These are 12 independently-run government sites; transient timeouts and
    # 5xx responses are routine, not exceptional (mirrors fetch_ecourts_judgments.py).
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    last_err = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=45, context=_SSL_CONTEXT) as resp:
                data = resp.read()
            return data if binary else data.decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
    raise last_err


def find_latest_pdf(listing_html):
    """Return (pdf_url, iso_date) for the most recent VC-links PDF on a listing page."""
    candidates = []
    for m in PDF_HREF_RE.finditer(listing_html):
        url = m.group(1)
        window_start = max(0, m.start() - 400)
        nearby = listing_html[window_start:m.start()]
        if NON_VC_LINK_HINTS.search(nearby):
            continue
        date_m = FILENAME_DATE_RE.search(url)
        if date_m:
            y, mo, d = date_m.group(1), date_m.group(2), date_m.group(3)
            iso = f"{y}-{mo}-{d}"
        else:
            page_date_m = PAGE_DATE_RE.search(nearby[-120:])
            if page_date_m:
                d, mo, y = page_date_m.groups()
                iso = f"{y}-{int(mo):02d}-{int(d):02d}"
            else:
                iso = "0000-00-00"
        candidates.append((iso, url))
    if not candidates:
        return None, None
    candidates.sort()
    return candidates[-1][1], candidates[-1][0]


def normalize_cell(cell):
    if cell is None:
        return ""
    return re.sub(r"\s+", " ", cell).strip()


def match_header(headers):
    """Given a row of header cells, return column index map or None if not a header row."""
    norm = [normalize_cell(h).lower().replace(" ", "") for h in headers]
    found = {}
    for key, keywords in HEADER_KEYWORDS.items():
        for i, cell in enumerate(norm):
            if any(kw.replace(" ", "") in cell for kw in keywords):
                found.setdefault(key, i)
                break
    # need at least name + url to be usable; designation/email are optional
    # (some districts merge name+designation into one cell - handled below)
    if "name" in found and "url" in found:
        return found
    return None


def split_name_designation(text):
    """Best-effort split when a district merges Name and Designation into one cell."""
    text = text.strip()
    if "," in text:
        name, _, rest = text.partition(",")
        return name.strip(), rest.strip()
    if "\n" in text:
        name, _, rest = text.partition("\n")
        return name.strip(), normalize_cell(rest)
    return text, ""


def parse_pdf_rows(pdf_bytes, district, source_page, pdf_date):
    import io
    rows_out = []
    colmap = None
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                if not table:
                    continue
                for row in table:
                    if colmap is None:
                        maybe = match_header(row)
                        if maybe:
                            colmap = maybe
                        continue
                    cells = [normalize_cell(c) for c in row]
                    if len(cells) <= max(colmap.values()):
                        continue
                    name_cell = cells[colmap["name"]]
                    # URLs can wrap across a line inside their cell; normalize_cell's
                    # whitespace-collapse turns that wrap into a stray space mid-URL,
                    # which would truncate the match below - strip raw newlines instead.
                    raw_url_cell = (row[colmap["url"]] or "").replace("\n", "").replace(" ", "")
                    if not name_cell or "http" not in raw_url_cell:
                        continue
                    designation = cells[colmap["designation"]] if "designation" in colmap else ""
                    if not designation:
                        name_cell, designation = split_name_designation(name_cell)
                    email = cells[colmap["email"]] if "email" in colmap else ""
                    url_match = re.search(r"https?://\S+", raw_url_cell)
                    if not url_match:
                        continue
                    rows_out.append({
                        "Judge Name": name_cell,
                        "Designation": designation,
                        "District/Complex": district,
                        "Email": email,
                        "VC Link": url_match.group(0),
                        "PDF Last Updated": pdf_date,
                        "Source Page (official)": source_page,
                    })
    return rows_out


def load_manifest():
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_manifest(manifest):
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")


def load_csv_rows():
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def sort_key(row):
    name = row["Judge Name"]
    is_placeholder = name.startswith("(")
    stripped = re.sub(r"^(Sh\.?|Shri|Sh|Ms\.?|Mr\.?|Dr\.?)\s+", "", name, flags=re.I)
    return (is_placeholder, stripped.strip().lower())


def save_csv_rows(rows):
    rows.sort(key=sort_key)
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        writer.writeheader()
        writer.writerows(rows)


def main():
    manifest = load_manifest()
    all_rows = load_csv_rows()
    updated, unchanged, needs_review, errored = [], [], [], []

    for district, listing_url in DISTRICT_SOURCES.items():
        try:
            html = fetch(listing_url)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            errored.append((district, f"couldn't fetch listing page: {e}"))
            continue

        pdf_url, pdf_date = find_latest_pdf(html)
        if not pdf_url:
            errored.append((district, "no VC-links PDF found on listing page"))
            continue

        last_known = manifest.get(district, {}).get("pdf_url")
        if pdf_url == last_known:
            unchanged.append(district)
            continue

        try:
            pdf_bytes = fetch(pdf_url, binary=True)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            errored.append((district, f"couldn't download PDF: {e}"))
            continue

        try:
            new_rows = parse_pdf_rows(pdf_bytes, district, listing_url.rstrip("/"), pdf_date)
        except Exception as e:  # pdfplumber/parse errors shouldn't kill the whole run
            errored.append((district, f"parse error: {e}"))
            continue

        previous_count = sum(1 for r in all_rows if r["District/Complex"] == district)
        # A parse that finds meaningfully fewer judges than we already had for this
        # district (not just "under some fixed floor") is the real regression signal -
        # a district can legitimately have anywhere from ~20 to ~100 courts.
        confidence_floor = max(MIN_CONFIDENT_ROWS, round(previous_count * 0.7))
        if len(new_rows) < confidence_floor:
            needs_review.append((district, pdf_url, len(new_rows), previous_count))
            continue

        all_rows = [r for r in all_rows if r["District/Complex"] != district]
        all_rows.extend(new_rows)
        manifest[district] = {"pdf_url": pdf_url, "pdf_date": pdf_date}
        updated.append((district, pdf_date, len(new_rows)))

    if updated:
        save_csv_rows(all_rows)
        save_manifest(manifest)

    report = ["# VC links update check\n"]
    if updated:
        report.append("## Updated districts\n")
        for d, date, n in updated:
            report.append(f"- **{d}** — new PDF dated {date}, {n} rows re-parsed. Spot-check against the source PDF before merging.\n")
    else:
        report.append("No district PDFs changed since the last check.\n")
    if needs_review:
        report.append("\n## Needs manual attention (not auto-updated)\n")
        for d, url, n, prev in needs_review:
            report.append(f"- **{d}** — new PDF detected but parse extracted only {n} rows (had {prev} before, expected close to that). PDF: {url}\n")
    if errored:
        report.append("\n## Errors\n")
        for d, msg in errored:
            report.append(f"- **{d}** — {msg}\n")
    report.append(f"\n_{len(unchanged)} of {len(DISTRICT_SOURCES)} districts unchanged._\n")

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("".join(report))

    print("".join(report))
    return 0 if not errored else 1


if __name__ == "__main__":
    sys.exit(main())
