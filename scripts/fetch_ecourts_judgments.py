#!/usr/bin/env python3
"""
Fetch candidate judgments from the eCourtsIndia API for FLRN's Evidence Room.

WHAT THIS DOES
Runs a handful of topic-scoped searches against the free eCourtsIndia
/api/partner/search endpoint (child custody, 498A/DV Act, maintenance,
child rights), skips anything already on the site, and writes a markdown
report of candidates for a human to review. It never calls a paid endpoint
and never edits index.html.

REMOVABILITY
This script and its companion workflow (.github/workflows/fetch-judgments.yml)
are fully optional and isolated from the live site:
  - They only ever produce ecourts-candidates.md on a throwaway branch/PR.
  - index.html is read-only here (only to build the dedupe list) and is
    never written to.
  - To stop using this automation permanently: delete this file, delete the
    workflow file, and remove the ECOURTS_API_TOKEN secret from
    Settings -> Secrets and variables -> Actions. Nothing else changes.
    Every card already on the site — whether drafted with this tool's help
    or written by hand — is plain static HTML with zero runtime dependency
    on this API or this script.
  - To pause without deleting anything: disable the workflow from the
    Actions tab (Actions -> Fetch eCourtsIndia Judgment Candidates -> ... ->
    Disable workflow). Re-enable any time.

MANUAL VERIFICATION STILL REQUIRED
This produces leads, not citations. Every entry in the report still needs
the same independent verification (IndianKanoon / official source) applied
to every other judgment on this site before it goes into index.html.
"""

import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    # certifi isn't strictly required — most platforms (including GitHub's
    # runners) have a working system CA bundle without it.
    _SSL_CONTEXT = ssl.create_default_context()

API_BASE = "https://webapi.ecourtsindia.com/api/partner"
TOKEN = os.environ.get("ECOURTS_API_TOKEN")
if not TOKEN:
    sys.exit("ECOURTS_API_TOKEN environment variable is required")

LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS", "45"))
INDEX_HTML_PATH = os.environ.get("INDEX_HTML_PATH", "index.html")
REPORT_PATH = os.environ.get("REPORT_PATH", "ecourts-candidates.md")

# Supreme Court only for now. Extend with High Court codes (via
# /api/partner/court-structure) once this has been reviewed against a few
# real runs — starting narrow keeps false positives and API usage low.
COURT_CODES = ["SCIN01"]

# Plain phrase+keyword queries per Evidence Room category — several simple
# queries per category, not one big boolean expression. Testing against the
# live API showed complex "AND (... OR ... OR ...)" grouping degrades badly
# (e.g. a "maintenance" AND-group matched infrastructure/service-division
# cases, not spousal maintenance), while short phrase+keyword combinations
# return exactly the right cases — plain "Section 125 maintenance wife"
# surfaced real maintenance judgments; "child custody guardian" surfaced
# cases already on this site by name. Multiple simple queries per category
# are run and merged/deduped rather than one combined query.
#
# Deliberately excludes "judicial-reform" — that category is more about a
# judgment's procedural significance than a keyword, and is a poor fit for
# automated discovery.
CATEGORY_QUERIES = {
    "co-parenting": [
        '"child custody" guardian',
        '"Guardians and Wards Act"',
        '"parental alienation"',
        '"visitation rights"',
    ],
    "false-accusations": [
        '"498A" cruelty',
        '"Domestic Violence Act"',
        'dowry harassment quashed',
        'bigamy "second marriage"',
    ],
    "maintenance": [
        '"Section 125" maintenance wife',
        '"Hindu Marriage Act" alimony',
        'maintenance husband desertion',
    ],
    "child-rights": [
        '"welfare of the child" custody',
        '"parental alienation syndrome"',
    ],
}


def api_get(path, params):
    qs = urllib.parse.urlencode(params, safe='":()')
    url = f"{API_BASE}{path}?{qs}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/json",
            # eCourtsIndia's WAF blocks the default Python-urllib User-Agent
            # even on authenticated, documented endpoints — send a plain
            # descriptive one instead.
            "User-Agent": "FLRN-EvidenceRoom-Research/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30, context=_SSL_CONTEXT) as resp:
        return json.loads(resp.read())


def existing_case_names(html_path):
    """Every case name already on the site, so we never suggest a duplicate."""
    if not os.path.exists(html_path):
        return []
    with open(html_path, encoding="utf-8") as f:
        html = f.read()
    names = re.findall(r'<div class="er-case-name">(.*?)</div>', html, re.S)
    cleaned = []
    for n in names:
        n = re.sub(r"<[^>]+>", "", n)
        n = re.sub(r"&[a-z]+;", " ", n)
        cleaned.append(n.lower().strip())
    return cleaned


def looks_like_duplicate(petitioner, respondent, known_names):
    p, r = petitioner.lower()[:12], respondent.lower()[:12]
    return any(p in name and r in name for name in known_names)


def search_category(category, queries):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).date().isoformat()
    results = []
    seen_cnrs = set()
    for query in queries:
        for court_code in COURT_CODES:
            params = {
                "CourtCodes": court_code,
                "Query": query,
                "HasJudgments": "true",
                "SortBy": "decisionDate",
                "SortOrder": "desc",
                "PageSize": 20,
            }
            try:
                data = api_get("/search", params)
            except urllib.error.HTTPError as e:
                print(f"  warning: search failed for {category}/{query!r}/{court_code}: {e}", file=sys.stderr)
                continue
            for hit in data.get("data", {}).get("results", []):
                if hit["cnr"] in seen_cnrs:
                    continue
                decision_date = hit.get("decisionDate") or hit.get("registrationDate")
                if decision_date and decision_date < cutoff:
                    continue
                seen_cnrs.add(hit["cnr"])
                results.append(hit)
    return results


def main():
    known_names = existing_case_names(INDEX_HTML_PATH)

    sections = []
    total_candidates = 0

    for category, queries in CATEGORY_QUERIES.items():
        hits = search_category(category, queries)  # already deduped by CNR
        entries = []

        for hit in hits:
            cnr = hit["cnr"]
            petitioners = ", ".join(hit.get("petitioners") or ["Unknown"])
            respondents = ", ".join(hit.get("respondents") or ["Unknown"])

            if looks_like_duplicate(petitioners, respondents, known_names):
                continue

            total_candidates += 1
            keywords = hit.get("aiKeywords") or []
            lines = [
                f"### {petitioners} v. {respondents}",
                f"- CNR: `{cnr}`",
                f"- Court: {hit.get('courtName') or hit.get('courtCode')}",
                f"- Decided: {hit.get('decisionDate') or 'unknown'}",
                f"- Case type: {hit.get('caseType')}",
            ]
            if keywords:
                lines.append(f"- AI summary keyword: {keywords[0]}")
            lines.append(f"- eCourtsIndia record: https://ecourtsindia.com/case/{cnr}")
            lines.append("")
            entries.append("\n".join(lines))

        sections.append((category, len(hits), entries))

    header = [
        "# eCourtsIndia — Candidate Judgments For Review",
        "",
        f"Generated {datetime.now(timezone.utc).isoformat()}Z. Lookback window: {LOOKBACK_DAYS} days.",
        "",
        f"**{total_candidates} new candidates** across {len(CATEGORY_QUERIES)} categories, "
        "after skipping anything already on the site.",
        "",
        "This is a research aid, not a publish pipeline — nothing here has been added to "
        "index.html. Verify each citation independently (IndianKanoon / official source) "
        "before adding a card, same standard as every other judgment on this site.",
        "",
    ]

    body = []
    for category, raw_count, entries in sections:
        body.append(f"## {category} ({raw_count} raw hits, {len(entries)} new)")
        body.append("")
        if entries:
            body.extend(entries)
        else:
            body.append("_No new candidates this run._")
            body.append("")

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(header + body))

    print(f"Wrote {REPORT_PATH} with {total_candidates} candidates")


if __name__ == "__main__":
    main()
