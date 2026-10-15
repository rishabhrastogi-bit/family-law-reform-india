#!/usr/bin/env python3
"""
Weekly refresh of data/india-district-courts.json — the all-India part of the
Court VC Link Finder (court-vc-links.html).

WHAT THIS DOES
For every district court already in the directory, visits that court's own
official website (*.dcourts.gov.in) and finds the newest video-conferencing
(VC) links file it has published:
  1. its Documents page, for a VC-links document category (e.g. "vc-links"),
     and the newest PDF in that category;
  2. the site's own search ("video conferencing", "vc link", "webex"), for
     individual VC-link documents posted under other categories.
Rules, request forms, helpdesk notices, nodal-officer lists, Lok Adalat
one-offs and similar non-link documents are filtered out by title.

Court names and states are NOT re-derived here — they were reviewed by hand
when the directory was built and are kept as-is. Delhi is handled separately
(scripts/fetch_vc_links.py parses the Delhi PDFs judge-by-judge).

BEING A GOOD CITIZEN TOWARDS COURT SERVERS
Only 4 courts are checked at a time, requests to a court are made one after
another with a pause between them, and every request identifies itself. A
full run is roughly 6 small page requests per court, once a week.

SAFETY — NEVER MAKE THE DIRECTORY WORSE
  - A court whose site can't be reached this week keeps its previous entry.
  - A newer VC file is never replaced by an older one.
  - If more than MAX_FAIL_RATIO of courts can't be reached (e.g. the runner's
    network is being blocked), nothing is written and the run exits non-zero.
  - The file is only rewritten when something actually changed.

New court websites are not added automatically (their state needs a human
check); any found via certificate-transparency logs are listed in the report.

Usage: python3 scripts/fetch_india_court_vc.py [--limit N] [--no-discovery]
"""

import argparse
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html import unescape

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
DATA_PATH = os.path.join(DATA_DIR, "india-district-courts.json")
REPORT_PATH = os.environ.get("REPORT_PATH", os.path.join(DATA_DIR, "..", "india-vc-refresh-report.md"))

WORKERS = 4
PAUSE_SECONDS = (1.0, 2.5)        # random pause between requests to the same court
TIMEOUT_SECONDS = 45
MAX_FAIL_RATIO = 0.30
USER_AGENT = ("Mozilla/5.0 (compatible; FLRN-VC-Directory/1.0; weekly check of published VC links; "
              "+https://github.com/rishabhrastogi-bit/family-law-reform-india)")

# Same upload-path date convention as the Delhi script: uploads/YYYY/MM/YYYYMMDDnn.pdf
FILENAME_DATE_RE = re.compile(r"/uploads/(\d{4})/(\d{2})/\1\2(\d{2})\d+\.pdf$", re.I)
PAGE_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
PDF_HREF_RE = re.compile(r'href="([^"]+\.pdf)"', re.I)

# Document categories worth following, and ones that are about VC but aren't link lists.
VC_CATEGORY_RE = re.compile(r"(^|[-_])(vc|video|conferenc|webex|virtual|e-?court-?room|online-hearing|hybrid)|vc-?link|videoconf", re.I)
CATEGORY_DROP_RE = re.compile(r"vwdc|rule|nodal|circular|coordinator|remand|availability|aij", re.I)

# A document title must look like a VC link list...
TITLE_VC_RE = re.compile(r"(\bvc\b|v\.c\.|video\s*-?\s*conferenc|webex|zoom|cisco|jitsi|teams|virtual\s+(court|hearing))", re.I)
TITLE_LINK_RE = re.compile(r"link|meeting\s*id|meeting\s*no|id[’']?s\b|static|webex|zoom|google meet|nic meet|virtual courts? of", re.I)
# ...and not be one of these.
TITLE_DROP_RE = re.compile(
    r"rules?\b|regulation|gallery|remand|coordinator|cordinator|\brpc\b|training|tender|guidelines|\bsop\b|"
    r"standard operating|vulnerable|vwdc|helpdesk|request|\bform\b|proforma|nodal|circular|order no|admin order|"
    r"manual|gazette|lok adalat|camp court|apaar|tgfsl|witness|recording|implementation|notification|mandatory|"
    r"availability|compliance|minutes|contact details for getting|bluejeans application in add|"
    r"extension of judicial custody|important notice|party or witness", re.I)

SEARCH_QUERIES = ["video+conferencing", "vc+link", "webex"]


def fetch(url):
    """GET via curl (more tolerant of these servers' TLS setups than urllib). Returns (status, body)."""
    try:
        r = subprocess.run(
            ["curl", "-s", "-L", "--max-time", str(TIMEOUT_SECONDS), "-A", USER_AGENT, "-w", "\n%{http_code}", url],
            capture_output=True, timeout=TIMEOUT_SECONDS + 15,
        )
    except subprocess.TimeoutExpired:
        return "000", ""
    out = r.stdout.decode("utf-8", "ignore")
    body, _, code = out.rpartition("\n")
    return code.strip(), body


def pdf_date(url, nearby_html=""):
    m = FILENAME_DATE_RE.search(url)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = PAGE_DATE_RE.search(nearby_html[-120:])
    if m:
        d, mo, y = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return None


def latest_pdf_on_page(html):
    best = None
    for m in PDF_HREF_RE.finditer(html):
        url = m.group(1)
        date = pdf_date(url, html[max(0, m.start() - 400):m.start()])
        if date and (best is None or (date, url) > best):
            best = (date, url)
    return best


def check_court(court):
    """Return (ok, findings) for one court. findings: {'vc_page', 'candidates': [(date, url, title)]}."""
    site = court["site"].rstrip("/")
    pause = lambda: time.sleep(random.uniform(*PAUSE_SECONDS))

    code, docs_html = fetch(f"{site}/documents/")
    if code != "200":
        return False, None
    findings = {"vc_page": None, "candidates": []}

    for slug in sorted(set(re.findall(r"/document-category/([a-z0-9-]+)", docs_html))):
        if CATEGORY_DROP_RE.search(slug) or not VC_CATEGORY_RE.search(slug):
            continue
        page_url = f"{site}/document-category/{slug}/"
        pause()
        code, page = fetch(page_url)
        if code != "200":
            continue
        findings["vc_page"] = findings["vc_page"] or page_url
        latest = latest_pdf_on_page(page)
        if latest:
            findings["candidates"].append((latest[0], latest[1], None))

    for q in SEARCH_QUERIES:
        pause()
        code, page = fetch(f"{site}/?s={q}")
        if code != "200":
            continue
        for m in re.finditer(r'<a[^>]*href="(https://[^"]+\.pdf)"[^>]*>(.*?)</a>', page, re.S | re.I):
            title = unescape(re.sub(r"<[^>]+>|\s+", " ", m.group(2))).strip()
            if (TITLE_VC_RE.search(title) and TITLE_LINK_RE.search(title) and not TITLE_DROP_RE.search(title)):
                date = pdf_date(m.group(1))
                if date:
                    findings["candidates"].append((date, m.group(1), title))
    return True, findings


def discover_new_hosts(known_hosts):
    """Court sites present in certificate-transparency logs but not yet in the directory (report only)."""
    code, body = fetch("https://crt.sh/?q=%25.dcourts.gov.in&output=json")
    if code != "200":
        return None
    try:
        entries = json.loads(body)
    except ValueError:
        return None
    hosts = set()
    for e in entries:
        for n in e.get("name_value", "").split("\n"):
            n = n.strip().lower().lstrip("*.")
            if re.fullmatch(r"[a-z0-9-]+\.dcourts\.gov\.in", n):
                hosts.add(n)
    return sorted(hosts - known_hosts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="only check the first N courts (testing)")
    ap.add_argument("--no-discovery", action="store_true", help="skip the crt.sh new-court check")
    args = ap.parse_args()

    with open(DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    courts = data["courts"]
    targets = [c for c in courts if c["state"] != "Delhi"]
    if args.limit:
        targets = targets[:args.limit]

    results = {}
    lock = threading.Lock()
    done = [0]

    def work(c):
        ok, findings = check_court(c)
        with lock:
            results[c["site"]] = (ok, findings)
            done[0] += 1
            if done[0] % 50 == 0:
                print(f"  checked {done[0]}/{len(targets)}", file=sys.stderr)

    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(work, targets))

    failed = [c for c in targets if not results[c["site"]][0]]
    fail_ratio = len(failed) / max(1, len(targets))
    if fail_ratio > MAX_FAIL_RATIO:
        msg = (f"Aborting without changes: {len(failed)} of {len(targets)} court sites "
               f"({fail_ratio:.0%}) could not be reached — likely a network block on this runner.")
        print(msg)
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            f.write("# India court VC refresh\n\n" + msg + "\n")
        return 1

    newer, new_files = [], []
    for c in targets:
        ok, findings = results[c["site"]]
        if not ok:
            continue  # keep last week's entry as-is
        if findings["vc_page"] and not c.get("vc_page"):
            c["vc_page"] = findings["vc_page"]
        if findings["candidates"]:
            date, url, title = max(findings["candidates"], key=lambda t: (t[0], t[1]))
            old = c.get("vc_file_date") or ""
            if date > old:
                (newer if c.get("vc_file") else new_files).append((c["court"], c["state"], old, date))
                c["vc_file"], c["vc_file_date"], c["vc_file_title"] = url, date, title

    changed = bool(newer or new_files)
    today = datetime.now(timezone.utc).date().isoformat()
    if changed or not args.limit:
        data["checked"] = today

    report = [f"# India court VC refresh — {today}\n\n",
              f"Checked {len(targets)} courts; {len(failed)} unreachable this week (previous entries kept).\n\n"]
    if newer:
        report.append(f"## Newer VC files ({len(newer)})\n")
        report += [f"- {n} ({s}): {o} → {d}\n" for n, s, o, d in sorted(newer, key=lambda t: (t[1], t[0]))]
    if new_files:
        report.append(f"\n## Courts with a VC file for the first time ({len(new_files)})\n")
        report += [f"- {n} ({s}): {d}\n" for n, s, o, d in sorted(new_files, key=lambda t: (t[1], t[0]))]
    if failed:
        report.append(f"\n## Unreachable this week ({len(failed)})\n")
        report += [f"- {c['court']} ({c['state']}) — {c['site']}\n" for c in failed[:100]]
    if not args.no_discovery:
        known = {c["site"].replace("https://", "").strip("/") for c in courts}
        new_hosts = discover_new_hosts(known)
        if new_hosts:
            report.append(f"\n## Court websites not yet in the directory ({len(new_hosts)}) — add by hand with their state\n")
            report += [f"- https://{h}/\n" for h in new_hosts]

    if changed or (not args.limit and data["checked"] == today):
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
            f.write("\n")
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("".join(report))
    print("".join(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
