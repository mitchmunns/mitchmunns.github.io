"""Read Mitch's Google Scholar profile and save the publication list to
publications.json, which the home page shows.

Google Scholar has no public data feed, so this reads the profile page.
If Scholar blocks the read or the page looks wrong, the old file is kept.
Only standard-library Python is used, so nothing needs installing.
"""
import html
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

USER = "hJHejacAAAAJ"
PROFILE = f"https://scholar.google.com/citations?user={USER}&hl=en"
PAGE = PROFILE + "&cstart=0&pagesize=100&sortby=pubdate"
OUT = Path(__file__).resolve().parent.parent / "publications.json"

# Only journal articles are shown. Scholar does not label item types, so the
# venue is checked: proceedings, meetings and posters are left out, and so is
# a one-page item such as "Journal of Vision 23 (9), 5184-5184", which is a
# conference abstract printed in a journal.
NOT_JOURNAL = re.compile(
    r"proceedings|annual meeting|conference|congress|symposium|workshop|"
    r"abstract|poster|meeting|psyarxiv|arxiv|biorxiv|preprint|thesis|dissertation",
    re.I)
ONE_PAGE = re.compile(r"\b(\d+)-\1\b")
# Fix a wrong call by putting a few words of the title here.
ALWAYS_SHOW = [
    "development of a broad spatial activities questionnaire",  # CogSci 2022 full paper
]
NEVER_SHOW = []


def text(fragment):
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def fetch():
    req = urllib.request.Request(PAGE, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


def parse(page):
    pubs = []
    for row in re.findall(r'<tr class="gsc_a_tr">(.*?)</tr>', page, re.S):
        title = re.search(r'<a href="([^"]*)" class="gsc_a_at">(.*?)</a>', row, re.S)
        grays = re.findall(r'<div class="gs_gray">(.*?)</div>', row, re.S)
        cites = re.search(r'class="gsc_a_ac[^"]*">(\d*)</a>', row)
        year = re.search(r'<span class="gsc_a_h[^"]*">(\d{4})?</span>', row)
        if not title:
            continue
        venue = re.sub(r'<span class="gs_oph">.*?</span>', "", grays[1], flags=re.S) if len(grays) > 1 else ""
        pubs.append({
            "title": text(title.group(2)),
            "authors": text(grays[0]) if grays else "",
            "venue": text(venue).rstrip(", "),
            "year": int(year.group(1)) if year and year.group(1) else None,
            "cited_by": int(cites.group(1)) if cites and cites.group(1) else 0,
            "url": "https://scholar.google.com" + html.unescape(title.group(1)),
        })
    return pubs


def is_journal_article(pub):
    title = pub["title"].lower()
    if any(t.lower() in title for t in ALWAYS_SHOW):
        return True
    if any(t.lower() in title for t in NEVER_SHOW):
        return False
    venue = pub["venue"]
    return bool(venue) and not NOT_JOURNAL.search(venue) and not ONE_PAGE.search(venue)


def main():
    try:
        page = fetch()
    except Exception as e:  # blocked, timed out, offline
        print(f"::warning::Could not read Google Scholar ({e}); keeping the old list.")
        return
    if "gsc_prf_in" not in page:
        print("::warning::Google Scholar did not return the profile page "
              "(probably a robot check); keeping the old list.")
        return
    found = parse(page)
    if not found:
        print("::warning::No publications found on the page; keeping the old list.")
        return
    pubs = [p for p in found if is_journal_article(p)]
    for p in found:
        if p not in pubs:
            print(f"Left out (not a journal article): {p['title']} | {p['venue']}")

    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    if old.get("publications") == pubs:
        print(f"No change ({len(pubs)} publications).")
        return
    OUT.write_text(json.dumps({
        "profile": PROFILE,
        "updated": date.today().isoformat(),
        "publications": pubs,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved {len(pubs)} journal articles.")


if __name__ == "__main__":
    sys.exit(main())
