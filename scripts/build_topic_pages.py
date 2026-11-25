#!/usr/bin/env python3
"""Build the Evidence Room topic pages from the cards in index.html.

index.html is the single source of truth: every judgment card lives in its
Evidence Room grid. This script copies those cards into one static page per
topic (so each topic can rank in search on its own), then:

  * rewrites the filter-pill counts in index.html ("All (237)" etc.),
  * rewrites the "Open a topic page" link row in index.html (between the
    topic-links:start / topic-links:end comments),
  * rewrites sitemap.xml.

Run it from the repo root after adding, removing or editing any card:

    python3 scripts/build_topic_pages.py

A page whose content has not changed keeps its "updated" date, so re-running
the script is safe. Standard library only.
"""
import datetime
import html
import json
import os
import re
import sys

SITE = "https://familylawreformindia.netlify.app/"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "index.html")
SITEMAP = os.path.join(ROOT, "sitemap.xml")

# Pages that are not generated here but belong in the sitemap.
STATIC_PAGES = [("", "index.html"), ("court-vc-links.html", "court-vc-links.html")]

TOPICS = [
    {
        "slug": "498a-judgments",
        "cats": ["false-accusations"],
        "nav": "498A & False Cases",
        "title": "498A & False Case Judgments — Supreme Court and High Courts",
        "h1": "498A, Domestic Violence &amp; False Case Judgments",
        "desc": "Supreme Court and High Court judgments on misuse of Section 498A (now Section 85 BNS), "
                "vague dowry FIRs, quashing, and Domestic Violence Act limits.",
        "lead": "Rulings on misuse of Section 498A, vague dowry complaints against a husband&rsquo;s whole "
                "family, quashing of FIRs and chargesheets, and the limits of the Domestic Violence Act.",
        "body": [
            "Section 498A of the Indian Penal Code, now Sections 85 and 86 of the Bharatiya Nyaya Sanhita, "
            "punishes cruelty to a married woman by her husband or his relatives. The Supreme Court has upheld "
            "the law, but it has also warned many times that vague, general allegations against a husband&rsquo;s "
            "whole family can turn a protective law into a tool for harassment.",
            "The judgments on this page include rulings that quash FIRs and chargesheets built on omnibus "
            "allegations, decisions protecting distant and elderly relatives, arrest safeguards, the limits of the "
            "Domestic Violence Act, and cases holding that a false criminal complaint can itself amount to cruelty "
            "against the husband.",
        ],
    },
    {
        "slug": "child-custody-judgments",
        "cats": ["co-parenting", "child-rights"],
        "nav": "Child Custody",
        "title": "Child Custody & Shared Parenting Judgments in India",
        "h1": "Child Custody &amp; Shared Parenting Judgments",
        "desc": "Indian court judgments on child custody, visitation, parenting time, shared parenting and "
                "parental alienation, with links to the full judgments.",
        "lead": "Rulings on custody, visitation and parenting time, shared parenting, parental alienation, and a "
                "child&rsquo;s right to a relationship with both parents.",
        "body": [
            "In Indian custody cases the deciding test is the welfare of the child, not the rights of either "
            "parent. Courts have increasingly said that welfare usually means keeping both parents meaningfully "
            "involved: a parent &lsquo;cannot be a guest in a child&rsquo;s life&rsquo;, and acrimony between the "
            "parents is not by itself a reason to deny access.",
            "This page collects rulings on custody and visitation, shared-parenting and parenting-time guidelines, "
            "parental alienation, habeas corpus for children, relocation abroad, and enforcement of visitation "
            "orders, including contempt for breaching them.",
        ],
    },
    {
        "slug": "maintenance-judgments",
        "cats": ["maintenance"],
        "nav": "Maintenance & Alimony",
        "title": "Maintenance & Alimony Judgments — Supreme Court, High Courts",
        "h1": "Maintenance &amp; Alimony Judgments",
        "desc": "Judgments on interim maintenance, permanent alimony and Section 125 CrPC (now Section 144 BNSS) "
                "claims, including earning capacity and concealed income.",
        "lead": "Rulings on interim maintenance and permanent alimony, how the amount is fixed, and when a claim "
                "is reduced or refused because of earning capacity, desertion or concealed income.",
        "body": [
            "Maintenance claims in India arise under Section 125 of the Code of Criminal Procedure (now Section 144 "
            "of the Bharatiya Nagarik Suraksha Sanhita), Sections 24 and 25 of the Hindu Marriage Act, and the "
            "Domestic Violence Act. In Rajnesh v. Neha (2020) the Supreme Court laid down guidelines that apply "
            "across these laws, including sworn disclosure of income and assets by both sides.",
            "Maintenance is meant to secure a reasonable standard of living, not to punish. The judgments here "
            "cover how interim and permanent amounts are fixed, the weight given to a spouse&rsquo;s qualifications "
            "and earning capacity, the effect of concealing income, maintenance for husbands, and the limits on "
            "claims against in-laws.",
        ],
    },
    {
        "slug": "perjury-340-judgments",
        "cats": ["perjury-340"],
        "nav": "Perjury & Section 340",
        "title": "Perjury & Section 340 CrPC Judgments — False Affidavits",
        "h1": "Perjury &amp; Section 340 Judgments",
        "desc": "Judgments on false affidavits and perjury in family cases, and the procedure under Section 340 "
                "CrPC (now Section 379 BNSS) for prosecuting false evidence.",
        "lead": "Rulings on false affidavits and false evidence in court, and on the procedure for prosecuting "
                "them under Section 340 of the Code of Criminal Procedure (now Section 379 BNSS).",
        "body": [
            "Filing a false affidavit or giving false evidence in court is a criminal offence. Under Section 340 "
            "of the Code of Criminal Procedure, now Section 379 of the Bharatiya Nagarik Suraksha Sanhita, the "
            "court where it happened can make a written complaint to a magistrate, after a preliminary inquiry if "
            "it considers one necessary.",
            "In family cases this most often arises when a party conceals income, employment or earlier "
            "proceedings to win or resist maintenance. The judgments here cover when a false statement is serious "
            "enough to prosecute (a deliberate false assertion, not a mere contradiction), the order in which a "
            "Section 340 application must be heard, time limits for deciding it, and costs for delay.",
        ],
    },
    {
        "slug": "divorce-cruelty-judgments",
        "cats": ["judicial-reform"],
        "nav": "Divorce & Procedure",
        "title": "Divorce, Cruelty & Court Procedure Judgments — India",
        "h1": "Divorce, Cruelty &amp; Court Procedure Judgments",
        "desc": "Judgments on divorce for cruelty and desertion, irretrievable breakdown, waiving the cooling-off "
                "period, Arnesh Kumar arrest safeguards and court procedure.",
        "lead": "Rulings on divorce for cruelty and desertion, irretrievable breakdown of marriage, arrest "
                "safeguards in matrimonial cases, and how family-court cases are run.",
        "body": [
            "This page collects judgments on how family disputes are decided and run: divorce on grounds of "
            "cruelty and desertion, the Supreme Court&rsquo;s power under Article 142 to dissolve a marriage that "
            "has irretrievably broken down, and when the six-month cooling-off period for mutual-consent divorce "
            "can be waived.",
            "It also covers arrest safeguards in matrimonial cases (Arnesh Kumar and the cases enforcing it, "
            "including compensation and contempt for illegal arrests), jurisdiction, mediated settlements, evidence "
            "such as recorded calls, and directions to speed up family-court cases.",
        ],
    },
]

MONTHS = {m: i for i, m in enumerate(
    "january february march april may june july august september october november december".split(), 1)}
MONTHS.update({"sept": 9, "sep": 9, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
               "oct": 10, "nov": 11, "dec": 12})


def parse_date(text):
    """Sort key matching parseErDate() in index.html."""
    text = text.strip()
    m = re.search(r"([a-z]+)\s+(\d{1,2}),\s*(\d{4})", text, re.I)
    if m:
        return int(m.group(3)) * 10000 + MONTHS.get(m.group(1).lower(), 0) * 100 + int(m.group(2))
    m = re.search(r"([a-z]+)\s+(\d{4})", text, re.I)
    if m:
        return int(m.group(2)) * 10000 + MONTHS.get(m.group(1).lower(), 0) * 100
    m = re.search(r"\b(\d{4})\b", text)
    return int(m.group(1)) * 10000 if m else 0


def text_of(card, cls):
    m = re.search(r'class="%s[^"]*">(.*?)</' % re.escape(cls), card, re.S)
    return html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip() if m else ""


def court_group(badge):
    if "Supreme Court" in badge:
        return "sc"
    if "High Court" in badge or re.search(r"\bHC\b", badge):
        return "hc"
    return "other"


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:60].rstrip("-") or "judgment"


def read_cards(src):
    a = src.index('<div class="er-grid">')
    b = src.index("</div><!-- end .er-grid -->")
    seg = src[a + len('<div class="er-grid">'):b]
    cards = []
    for i, raw in enumerate(re.split(r'(?=<div class="er-card reveal")', seg)[1:]):
        raw = raw.strip()
        cat = re.search(r'data-category="([^"]+)"', raw).group(1)
        href = re.search(r'<a href="([^"]+)"[^>]*class="er-read-more"', raw).group(1)
        cards.append({
            "i": i, "raw": raw, "cat": cat, "href": href,
            "name": text_of(raw, "er-case-name"),
            "date": text_of(raw, "er-year"),
            "court": text_of(raw, "er-court-badge"),
        })
    return cards


def card_html(card, used_ids):
    base = slugify(card["name"])
    cid, n = base, 2
    while cid in used_ids:
        cid, n = "%s-%d" % (base, n), n + 1
    used_ids.add(cid)
    out = card["raw"].replace('<div class="er-card reveal"',
                              '<div class="er-card" id="%s" data-court="%s"' % (cid, court_group(card["court"])), 1)
    return "      " + out


CSS = """
    :root { --dark: #050810; --gold: #F59E0B; --gold-dark: #B45309; --white: #FFFFFF; --slate: #1e293b; --muted: #64748b; --body: #475569; --light-bg: #F8FAFC; --border: #E2E8F0; }
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    [hidden] { display: none !important; }
    html { scroll-behavior: smooth; }
    body { font-family: 'Inter', sans-serif; background: var(--light-bg); color: var(--slate); overflow-x: hidden; }
    .tp-inner { max-width: 1200px; margin: 0 auto; }
    .tp-header { background: var(--dark); display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 16px 48px; border-bottom: 1px solid rgba(245,158,11,0.15); }
    .tp-logo { display: flex; flex-direction: column; text-decoration: none; }
    .tp-logo-title { font-family: 'Bebas Neue', sans-serif; font-size: 28px; color: var(--gold); line-height: 1; letter-spacing: 2px; }
    .tp-logo-sub { font-size: 11px; color: rgba(255,255,255,0.55); letter-spacing: 0.4px; margin-top: 2px; }
    .tp-header-links { display: flex; align-items: center; gap: 20px; }
    .tp-header-links a { font-size: 13px; color: rgba(255,255,255,0.85); text-decoration: none; white-space: nowrap; transition: color 0.2s; }
    .tp-header-links a:hover { color: var(--gold); }
    .tp-header-links .tp-join { border: 1.5px solid var(--gold); color: var(--gold); padding: 7px 16px; border-radius: 6px; }
    .tp-hero { background: var(--dark); color: var(--white); padding: 44px 48px 56px; }
    .tp-crumbs { font-size: 12px; color: rgba(255,255,255,0.45); margin-bottom: 28px; }
    .tp-crumbs a { color: rgba(255,255,255,0.7); text-decoration: none; }
    .tp-crumbs a:hover { color: var(--gold); }
    .tp-crumbs span { margin: 0 6px; }
    .section-label { font-size: 12px; color: var(--gold); letter-spacing: 3px; text-transform: uppercase; margin-bottom: 14px; display: block; }
    .tp-h1 { font-family: 'Playfair Display', serif; font-size: 48px; font-weight: 700; line-height: 1.2; max-width: 900px; }
    .gold-underline { width: 72px; height: 3px; background: var(--gold); margin: 20px 0 24px; }
    .tp-lead { font-size: 18px; line-height: 1.7; color: rgba(255,255,255,0.8); max-width: 760px; }
    .tp-meta { margin-top: 18px; font-size: 13px; color: rgba(255,255,255,0.5); letter-spacing: 0.3px; }
    .tp-body { padding: 52px 48px 72px; }
    .tp-intro { max-width: 760px; margin-bottom: 32px; }
    .tp-intro p { font-size: 16px; line-height: 1.8; color: var(--body); margin-bottom: 14px; }
    .tp-topics { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 28px; }
    .tp-topics a { font-size: 13px; font-weight: 500; padding: 7px 14px; border-radius: 20px; border: 1.5px solid var(--border); background: #fff; color: var(--muted); text-decoration: none; transition: all 0.2s; }
    .tp-topics a:hover { border-color: var(--gold); color: var(--gold-dark); }
    .tp-topics a[aria-current="page"] { background: var(--gold); border-color: var(--gold); color: var(--dark); }
    .tp-tools { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-bottom: 14px; }
    #tp-search { flex: 1 1 280px; max-width: 420px; font: inherit; font-size: 16px; padding: 10px 14px; border: 1.5px solid var(--border); border-radius: 8px; background: #fff; color: var(--slate); }
    #tp-search:focus { outline: none; border-color: var(--gold); }
    .tp-courts { display: flex; flex-wrap: wrap; gap: 8px; }
    .tp-court { font: inherit; font-size: 12px; font-weight: 500; padding: 7px 13px; border-radius: 20px; border: 1.5px solid var(--border); background: #fff; color: var(--muted); cursor: pointer; }
    .tp-court:hover { border-color: var(--slate); }
    .tp-court[aria-pressed="true"] { background: var(--slate); border-color: var(--slate); color: #fff; }
    .tp-count { font-size: 13px; color: var(--muted); margin-bottom: 22px; }
    .tp-empty { font-size: 15px; color: var(--muted); padding: 32px 0; }
    .er-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 20px; }
    .er-card { background: white; border-radius: 12px; box-shadow: 0 2px 14px rgba(0,0,0,0.07); padding: 20px; display: flex; flex-direction: column; border-top: 4px solid transparent; transition: box-shadow 0.25s, transform 0.25s; position: relative; cursor: pointer; scroll-margin-top: 24px; }
    .er-card:hover { box-shadow: 0 10px 36px rgba(0,0,0,0.13); transform: translateY(-3px); }
    .er-card:target { outline: 2px solid var(--gold); outline-offset: 3px; }
    .er-card[data-category="co-parenting"] { border-top-color: #F59E0B; }
    .er-card[data-category="false-accusations"] { border-top-color: #EF4444; }
    .er-card[data-category="maintenance"] { border-top-color: #3B82F6; }
    .er-card[data-category="child-rights"] { border-top-color: #10B981; }
    .er-card[data-category="judicial-reform"] { border-top-color: #8B5CF6; }
    .er-card[data-category="perjury-340"] { border-top-color: #0D9488; }
    .er-card-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
    .er-cat-pill { font-size: 10px; font-weight: 600; letter-spacing: 0.5px; padding: 3px 9px; border-radius: 20px; white-space: nowrap; }
    .cat-co-parenting { background: rgba(245,158,11,0.15); color: #B45309; border: 1px solid rgba(245,158,11,0.4); }
    .cat-false-accusations { background: rgba(239,68,68,0.1); color: #B91C1C; border: 1px solid rgba(239,68,68,0.3); }
    .cat-maintenance { background: rgba(59,130,246,0.1); color: #1D4ED8; border: 1px solid rgba(59,130,246,0.3); }
    .cat-child-rights { background: rgba(16,185,129,0.1); color: #065F46; border: 1px solid rgba(16,185,129,0.3); }
    .cat-judicial-reform { background: rgba(139,92,246,0.1); color: #5B21B6; border: 1px solid rgba(139,92,246,0.3); }
    .cat-perjury-340 { background: rgba(13,148,136,0.1); color: #0F766E; border: 1px solid rgba(13,148,136,0.3); }
    .er-court-badge { font-size: 10px; font-weight: 600; color: var(--gold-dark); background: rgba(245,158,11,0.1); border: 1px solid rgba(245,158,11,0.25); padding: 3px 9px; border-radius: 20px; white-space: normal; }
    .er-case-name { font-family: 'Playfair Display', serif; font-size: 15px; font-weight: 700; color: var(--slate); line-height: 1.4; margin-bottom: 4px; overflow-wrap: anywhere; }
    .er-year { font-family: 'Bebas Neue', sans-serif; font-size: 16px; color: var(--muted); letter-spacing: 1px; margin-bottom: 10px; }
    .er-what { font-size: 13px; color: var(--body); line-height: 1.7; flex: 1; margin-bottom: 16px; }
    .er-card-bottom { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: auto; flex-wrap: wrap; }
    .er-badge { font-size: 10px; font-weight: 700; letter-spacing: 1px; padding: 3px 9px; border-radius: 20px; }
    .er-landmark { background: rgba(245,158,11,0.15); color: #B45309; border: 1px solid rgba(245,158,11,0.4); }
    .er-precedent { background: rgba(100,116,139,0.12); color: var(--muted); border: 1px solid rgba(100,116,139,0.25); }
    .er-read-more { font-size: 12px; color: var(--gold-dark); text-decoration: none; font-weight: 600; letter-spacing: 0.2px; }
    .er-read-more:hover, .er-card:hover .er-read-more { text-decoration: underline; }
    .tp-howto { margin-top: 56px; max-width: 760px; padding: 24px 28px; background: #fff; border: 1px solid var(--border); border-left: 4px solid var(--gold); border-radius: 10px; }
    .tp-howto h2 { font-family: 'Playfair Display', serif; font-size: 22px; color: var(--slate); margin-bottom: 10px; }
    .tp-howto p { font-size: 14px; line-height: 1.75; color: var(--body); margin-bottom: 10px; }
    .tp-howto p:last-child { margin-bottom: 0; }
    .er-cta-strip { background: var(--dark); padding: 72px 48px; text-align: center; }
    .er-cta-headline { font-family: 'Bebas Neue', sans-serif; font-size: 60px; color: var(--white); letter-spacing: 2px; margin-bottom: 16px; font-weight: 400; }
    .er-cta-sub { font-size: 18px; color: #94a3b8; line-height: 1.7; margin-bottom: 32px; }
    .er-cta-btns { display: flex; gap: 16px; justify-content: center; flex-wrap: wrap; margin-bottom: 26px; }
    .btn-primary, .btn-outline { font-size: 15px; font-weight: 600; padding: 15px 30px; border-radius: 8px; text-decoration: none; display: inline-block; letter-spacing: 0.4px; transition: all 0.25s; }
    .btn-primary { background: var(--gold); color: var(--dark); border: 2px solid var(--gold); }
    .btn-primary:hover { background: #FCD34D; border-color: #FCD34D; }
    .btn-outline { background: transparent; color: var(--gold); border: 2px solid var(--gold); }
    .btn-outline:hover { background: rgba(245,158,11,0.1); }
    .er-cta-foot { font-size: 14px; color: #94a3b8; }
    .gold-link { color: var(--gold); text-decoration: none; border-bottom: 1px solid rgba(245,158,11,0.4); }
    footer { background: var(--dark); padding: 48px 48px 32px; border-top: 1px solid rgba(245,158,11,0.1); }
    .tp-footer-inner { max-width: 1200px; margin: 0 auto 32px; display: grid; grid-template-columns: 1.3fr 1fr 1fr; gap: 48px; }
    .footer-logo-title { font-family: 'Bebas Neue', sans-serif; font-size: 30px; color: var(--gold); letter-spacing: 2px; margin-bottom: 8px; }
    .tp-foot-text { font-size: 13px; color: #94a3b8; line-height: 1.7; margin-bottom: 10px; }
    .footer-nav-title { font-size: 11px; font-weight: 600; color: rgba(255,255,255,0.45); letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 16px; }
    footer ul { list-style: none; display: flex; flex-direction: column; gap: 10px; }
    footer ul a { font-size: 14px; color: rgba(255,255,255,0.65); text-decoration: none; }
    footer ul a:hover { color: var(--gold); }
    .footer-bottom { max-width: 1200px; margin: 0 auto; padding-top: 20px; border-top: 1px solid rgba(255,255,255,0.06); text-align: center; font-size: 13px; color: rgba(255,255,255,0.35); }
    @media (max-width: 1100px) { .er-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
    @media (max-width: 900px) {
      .tp-header, .tp-hero, .tp-body, .er-cta-strip, footer { padding-left: 20px; padding-right: 20px; }
      .er-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
      .tp-h1 { font-size: 36px; }
      .tp-lead { font-size: 16px; }
      .tp-footer-inner { grid-template-columns: 1fr; gap: 28px; }
      .er-cta-headline { font-size: 44px; }
    }
    @media (max-width: 600px) {
      .er-grid { grid-template-columns: 1fr; }
      .tp-h1 { font-size: 30px; }
      .tp-header-links { gap: 14px; }
      .tp-header-links .tp-join { display: none; }
      .tp-hero { padding-top: 32px; padding-bottom: 40px; }
      .tp-body { padding-top: 36px; }
      .tp-topics { flex-wrap: nowrap; overflow-x: auto; margin-left: -20px; margin-right: -20px; padding: 0 20px 4px; scrollbar-width: none; }
      .tp-topics a { flex: 0 0 auto; }
      #tp-search { max-width: none; }
      .er-cta-headline { font-size: 38px; }
      .er-cta-sub { font-size: 16px; }
    }
"""

JS = """
(function () {
  var grid = document.getElementById('tp-grid');
  if (!grid) return;
  var cards = Array.prototype.slice.call(grid.querySelectorAll('.er-card'));
  var search = document.getElementById('tp-search');
  var buttons = Array.prototype.slice.call(document.querySelectorAll('.tp-court'));
  var countEl = document.getElementById('tp-count');
  var empty = document.getElementById('tp-empty');
  var court = 'all', total = cards.length;
  cards.forEach(function (c) {
    c._text = c.textContent.toLowerCase().replace(/\\s+/g, ' ');
    c.addEventListener('click', function (e) {
      var link = c.querySelector('.er-read-more');
      if (link && !e.target.closest('a')) window.open(link.href, '_blank', 'noopener,noreferrer');
    });
  });
  function apply() {
    var words = search.value.toLowerCase().trim().split(/\\s+/).filter(Boolean), shown = 0;
    cards.forEach(function (c) {
      var ok = (court === 'all' || c.getAttribute('data-court') === court) &&
        words.every(function (w) { return c._text.indexOf(w) !== -1; });
      c.hidden = !ok;
      if (ok) shown++;
    });
    countEl.textContent = shown === total ? 'Showing all ' + total + ' judgments, newest first.'
      : 'Showing ' + shown + ' of ' + total + ' judgments, newest first.';
    empty.hidden = shown > 0;
  }
  search.addEventListener('input', apply);
  buttons.forEach(function (b) {
    b.addEventListener('click', function () {
      buttons.forEach(function (x) { x.setAttribute('aria-pressed', 'false'); });
      b.setAttribute('aria-pressed', 'true');
      court = b.getAttribute('data-court');
      apply();
    });
  });
})();
"""

HOWTO = (
    "<p><strong>Official Court Copy</strong> opens the judgment PDF from the Supreme Court&rsquo;s own website. "
    "<strong>Full Judgment</strong> opens the complete judgment text (Indian Kanoon, or a PDF copy of the order). "
    "<strong>Read Report</strong> opens a news or legal-blog summary where no full text is linked yet.</p>"
    "<p>To rely on a judgment in court, cite it by its case number or citation; the court&rsquo;s registry can "
    "issue a certified copy. Check that it has not been overturned or modified on appeal. The one-line summaries "
    "on this page are for information only and are not legal advice.</p>"
)


def fmt_date(iso):
    d = datetime.date.fromisoformat(iso)
    return "%d %s %d" % (d.day, d.strftime("%B"), d.year)


def plain(s):
    return html.unescape(s)


def render(topic, cards, topics_meta, updated):
    url = SITE + topic["slug"] + ".html"
    used = set()
    n = len(cards)
    groups = {"sc": 0, "hc": 0, "other": 0}
    for c in cards:
        groups[court_group(c["court"])] += 1
    meta_bits = ["%d judgments" % n]
    if groups["sc"]:
        meta_bits.append("%d from the Supreme Court" % groups["sc"])
    meta_bits.append("updated %s" % fmt_date(updated))

    court_buttons = ['<button type="button" class="tp-court" data-court="all" aria-pressed="true">All courts</button>']
    for key, label in (("sc", "Supreme Court"), ("hc", "High Courts"), ("other", "Other courts")):
        if groups[key]:
            court_buttons.append('<button type="button" class="tp-court" data-court="%s" aria-pressed="false">'
                                 '%s (%d)</button>' % (key, label, groups[key]))

    topic_links = []
    for t in topics_meta:
        cur = ' aria-current="page"' if t["slug"] == topic["slug"] else ""
        topic_links.append('<a href="%s.html"%s>%s (%d)</a>' % (t["slug"], cur, html.escape(t["nav"]), t["count"]))
    footer_topics = "".join('<li><a href="%s.html">%s</a></li>' % (t["slug"], html.escape(t["nav"]))
                            for t in topics_meta)

    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "CollectionPage",
                "@id": url + "#page",
                "url": url,
                "name": plain(topic["h1"]),
                "description": topic["desc"],
                "inLanguage": "en-IN",
                "dateModified": updated,
                "isPartOf": {"@id": SITE + "#website"},
                "publisher": {"@id": SITE + "#organization"},
                "breadcrumb": {"@id": url + "#breadcrumb"},
            },
            {
                "@type": "BreadcrumbList",
                "@id": url + "#breadcrumb",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE},
                    {"@type": "ListItem", "position": 2, "name": topic["nav"], "item": url},
                ],
            },
        ],
    }
    ld_json = json.dumps(ld, ensure_ascii=False, indent=2).replace("</", "<\\/")

    e = lambda s: html.escape(s, quote=True)
    body_paras = "\n".join("      <p>%s</p>" % p for p in topic["body"])
    cards_html = "\n\n".join(card_html(c, used) for c in cards)

    return f"""<!DOCTYPE html>
<!-- Generated by scripts/build_topic_pages.py from the Evidence Room cards in index.html. Edit the cards there, not here. -->
<html lang="en-IN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{e(topic["title"])}</title>
  <meta name="description" content="{e(topic["desc"])}">
  <meta name="robots" content="index, follow, max-image-preview:large">
  <meta name="theme-color" content="#050810">
  <link rel="canonical" href="{url}">
  <meta property="og:type" content="website">
  <meta property="og:url" content="{url}">
  <meta property="og:site_name" content="Family Law Reform Network India">
  <meta property="og:locale" content="en_IN">
  <meta property="og:title" content="{e(topic["title"])}">
  <meta property="og:description" content="{e(topic["desc"])}">
  <meta property="og:image" content="{SITE}og-image.jpg">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="Family Law Reform Network India: petitions, advocates and court VC links">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{e(topic["title"])}">
  <meta name="twitter:description" content="{e(topic["desc"])}">
  <meta name="twitter:image" content="{SITE}og-image.jpg">
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⚖️</text></svg>">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Playfair+Display:wght@700&family=Inter:wght@400;500;600;700&display=swap">
  <script type="application/ld+json">
{ld_json}
  </script>
  <style>{CSS}  </style>
</head>
<body>

<header class="tp-header">
  <a class="tp-logo" href="./">
    <span class="tp-logo-title">FLRN</span>
    <span class="tp-logo-sub">Family Law Reform<br>Network India</span>
  </a>
  <nav class="tp-header-links" aria-label="Site">
    <a href="./#evidence-room">Evidence Room</a>
    <a href="court-vc-links.html">Court VC Links</a>
    <a href="./#join" class="tp-join">Join Network</a>
  </nav>
</header>

<main>
  <section class="tp-hero">
    <div class="tp-inner">
      <nav class="tp-crumbs" aria-label="Breadcrumb"><a href="./">Home</a><span>&rsaquo;</span><a href="./#evidence-room">Evidence Room</a><span>&rsaquo;</span>{html.escape(topic["nav"])}</nav>
      <span class="section-label">The Evidence Room</span>
      <h1 class="tp-h1">{topic["h1"]}</h1>
      <div class="gold-underline"></div>
      <p class="tp-lead">{topic["lead"]}</p>
      <p class="tp-meta">{" &middot; ".join(meta_bits)}</p>
    </div>
  </section>

  <section class="tp-body">
    <div class="tp-inner">
      <div class="tp-intro">
{body_paras}
      </div>

      <nav class="tp-topics" aria-label="Judgment topics">{"".join(topic_links)}</nav>

      <div class="tp-tools">
        <input type="search" id="tp-search" placeholder="Search by case name, court or keyword" aria-label="Search these judgments">
        <div class="tp-courts" role="group" aria-label="Filter by court">{"".join(court_buttons)}</div>
      </div>
      <p class="tp-count" id="tp-count" aria-live="polite">Showing all {n} judgments, newest first.</p>

      <div class="er-grid" id="tp-grid">

{cards_html}

      </div>
      <p class="tp-empty" id="tp-empty" hidden>No judgments match that search. Try fewer words, or choose &ldquo;All courts&rdquo;.</p>

      <div class="tp-howto">
        <h2>Using these judgments</h2>
        {HOWTO}
      </div>
    </div>
  </section>

  <section class="er-cta-strip">
    <h2 class="er-cta-headline">THE LAW IS ALREADY SPEAKING.</h2>
    <p class="er-cta-sub">These courts ruled in our favour.<br>Now we need laws that don&rsquo;t require a father to fight for years to reach them.</p>
    <div class="er-cta-btns">
      <a href="https://www.change.org/p/every-child-deserves-both-parents-protect-fathers-access-and-shared-parenting-in-india" target="_blank" rel="noopener noreferrer" class="btn-primary">Sign the Petition</a>
      <a href="./#join" class="btn-outline">Join the Movement</a>
    </div>
    <p class="er-cta-foot">Know a relevant judgment not listed here?
      <a href="mailto:contact@equalfamilyreform.in?subject=Evidence%20Room%20Submission" class="gold-link">Submit a Case &rarr;</a>
    </p>
  </section>
</main>

<footer>
  <div class="tp-footer-inner">
    <div>
      <div class="footer-logo-title">FLRN</div>
      <p class="tp-foot-text">Family Law Reform Network India is an independent civil-society initiative, not affiliated with any political party.</p>
      <p class="tp-foot-text">Judgment summaries are for information only and are not legal advice.</p>
    </div>
    <nav aria-label="Judgments by topic">
      <div class="footer-nav-title">Judgments by topic</div>
      <ul>{footer_topics}</ul>
    </nav>
    <nav aria-label="More from FLRN">
      <div class="footer-nav-title">More from FLRN</div>
      <ul><li><a href="./">Home</a></li><li><a href="./#evidence-room">All judgments</a></li><li><a href="./#petitions">Petitions</a></li><li><a href="./#coalition">Coalition</a></li><li><a href="court-vc-links.html">Court VC Links</a></li><li><a href="./#join">Join Network</a></li></ul>
    </nav>
  </div>
  <div class="footer-bottom">&copy; 2026 Family Law Reform Network India (FLRN).</div>
</footer>

<script>{JS}</script>
</body>
</html>
"""


def existing_updated(path):
    try:
        old = open(path, encoding="utf-8").read()
    except FileNotFoundError:
        return None, None
    m = re.search(r'"dateModified": "(\d{4}-\d{2}-\d{2})"', old)
    return old, (m.group(1) if m else None)


def update_index(src, cards, topics_meta):
    counts = {}
    for c in cards:
        counts[c["cat"]] = counts.get(c["cat"], 0) + 1
    counts["all"] = len(cards)

    def pill(m):
        return m.group(1) + str(counts.get(m.group(2), 0)) + m.group(4)
    src, n_pills = re.subn(
        r'(<button class="er-pill[^"]*" data-category="([a-z0-9-]+)">[^<]*<span[^>]*>\()(\d+)(\)</span></button>)',
        pill, src)
    if n_pills == 0:
        sys.exit("index.html: no Evidence Room filter pills found")

    start = "<!-- topic-links:start (generated by scripts/build_topic_pages.py) -->"
    end = "<!-- topic-links:end -->"
    if start not in src or end not in src:
        sys.exit("index.html is missing the topic-links markers")
    links = "".join('<a href="%s.html">%s (%d)</a>' % (t["slug"], html.escape(t["nav"]), t["count"])
                    for t in topics_meta)
    block = ('%s\n    <nav class="er-topic-links reveal" aria-label="Judgments by topic">'
             '<span class="er-topic-label">Open a topic page:</span>%s</nav>\n    %s' % (start, links, end))
    a = src.index(start)
    b = src.index(end) + len(end)
    return src[:a] + block + src[b:], counts


def write_sitemap(entries):
    rows = "".join("  <url>\n    <loc>%s</loc>\n    <lastmod>%s</lastmod>\n  </url>\n" % (loc, mod)
                   for loc, mod in entries)
    out = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n%s</urlset>\n' % rows
    with open(SITEMAP, "w", encoding="utf-8") as f:
        f.write(out)


def main():
    today = datetime.date.today().isoformat()
    src = open(INDEX, encoding="utf-8").read()
    cards = read_cards(src)

    covered = {c for t in TOPICS for c in t["cats"]}
    stray = {c["cat"] for c in cards} - covered
    if stray:
        sys.exit("Cards in categories not assigned to any topic page: %s" % ", ".join(sorted(stray)))

    # Two cards with the same link are the same judgment filed twice (sometimes in two
    # categories); a topic page shows it once, preferring the card titled "X v. Y".
    def is_case_title(c):
        return bool(re.search(r"\sv\.?\s", c["name"]))

    pages = []
    for t in TOPICS:
        by_href = {}
        for cat in t["cats"]:
            for c in cards:
                if c["cat"] != cat:
                    continue
                prev = by_href.get(c["href"])
                if prev is None or (is_case_title(c) and not is_case_title(prev)):
                    by_href[c["href"]] = c
        picked = sorted(by_href.values(), key=lambda c: (-parse_date(c["date"]), c["i"]))
        pages.append((t, picked))
    topics_meta = [{"slug": t["slug"], "nav": t["nav"], "count": len(p)} for t, p in pages]

    old_map = {}
    try:
        for loc, mod in re.findall(r"<loc>(.*?)</loc>\s*<lastmod>(.*?)</lastmod>", open(SITEMAP, encoding="utf-8").read()):
            old_map[loc] = mod
    except FileNotFoundError:
        pass

    changed = []
    sitemap = []
    for t, picked in pages:
        path = os.path.join(ROOT, t["slug"] + ".html")
        old, old_date = existing_updated(path)
        if old is not None and old_date and render(t, picked, topics_meta, old_date) == old:
            date = old_date
        else:
            date = today
            with open(path, "w", encoding="utf-8") as f:
                f.write(render(t, picked, topics_meta, date))
            changed.append(t["slug"] + ".html")
        sitemap.append((SITE + t["slug"] + ".html", date))
        print("%-32s %3d cards  updated %s" % (t["slug"] + ".html", len(picked), date))

    new_src, counts = update_index(src, cards, topics_meta)
    if new_src != src:
        with open(INDEX, "w", encoding="utf-8") as f:
            f.write(new_src)
        changed.append("index.html")
    print("index.html pill counts:", ", ".join("%s %d" % kv for kv in sorted(counts.items())))

    head = []
    for path_part, fname in STATIC_PAGES:
        loc = SITE + path_part
        mod = today if (fname == "index.html" and changed) else old_map.get(loc, today)
        head.append((loc, mod))
    write_sitemap(head + sitemap)
    print("changed:", ", ".join(changed) if changed else "nothing")


if __name__ == "__main__":
    main()
