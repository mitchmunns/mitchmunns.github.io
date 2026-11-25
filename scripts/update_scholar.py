"""Read Mitch's Google Scholar profile and save the publication list to
publications.json, which the home page shows.

- The list of papers comes from the Scholar profile page.
- Full author lists and DOI links come from OpenAlex and Crossref (Scholar
  blocks automated reads of single-paper pages). Each paper is looked up
  once; after that the saved details are reused, so few requests are made.
- The short summary under each paper comes from summaries.json, which is
  written by hand (it is never overwritten here).

If Scholar blocks the read or the page looks wrong, the old file is kept.
Only standard-library Python is used, so nothing needs installing.
"""
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

USER = "hJHejacAAAAJ"
PROFILE = f"https://scholar.google.com/citations?user={USER}&hl=en"
PAGE = PROFILE + "&cstart=0&pagesize=100&sortby=pubdate"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "publications.json"
SUMMARIES = ROOT / "summaries.json"
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
API_UA = "personal-site-publications (GitHub Actions)"

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


def norm(title):
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def text(fragment):
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def get(url, ua, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
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
            "authors": [dotted(a.strip()) for a in text(grays[0]).split(",") if a.strip()] if grays else [],
            "venue": text(venue).rstrip(", "),
            "year": int(year.group(1)) if year and year.group(1) else None,
            "cited_by": int(cites.group(1)) if cites and cites.group(1) else 0,
            "scholar_url": "https://scholar.google.com" + html.unescape(title.group(1)),
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


def initials(given):
    # "Chuanxiuyue (Carol)" -> "C."; nicknames in brackets are skipped.
    parts = re.split(r"[\s.]+", given.strip())
    return " ".join(p[0] + "." for p in parts if p and p[0].isalpha())


def dotted(name):
    """Scholar writes "ME Munns"; show it as "M. E. Munns" like the rest."""
    m = re.match(r"^([A-Z]{1,4}) (.+)$", name)
    return (" ".join(c + "." for c in m.group(1)) + " " + m.group(2)) if m else name


def look_up(pub):
    """Find the DOI (OpenAlex, by title) and the full author list (Crossref)."""
    q = urllib.parse.quote(re.sub(r"[:,?;]", " ", pub["title"]))
    found = json.loads(get(f"https://api.openalex.org/works?search={q}&per_page=5", API_UA))
    doi = None
    for work in found.get("results", []):
        if norm(work.get("title") or "") == norm(pub["title"]) and work.get("doi"):
            doi = work["doi"].replace("https://doi.org/", "")
            break
    if not doi:
        return None, None
    time.sleep(1)
    msg = json.loads(get(f"https://api.crossref.org/works/{urllib.parse.quote(doi)}", API_UA))["message"]
    authors = []
    for a in msg.get("author", []):
        if a.get("family"):
            authors.append((initials(a.get("given", "")) + " " + a["family"]).strip())
        elif a.get("name"):
            authors.append(a["name"])
    return doi, authors or None


def main():
    try:
        page = get(PAGE, BROWSER_UA)
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
    known = {norm(p["title"]): p for p in old.get("publications", []) if "doi" in p}
    summaries = json.loads(SUMMARIES.read_text(encoding="utf-8")) if SUMMARIES.exists() else {}
    summaries = {norm(k): v for k, v in summaries.items()}

    for p in pubs:
        before = known.get(norm(p["title"]))
        if before:
            p["doi"], full = before["doi"], before.get("full_authors")
        else:
            try:
                p["doi"], full = look_up(p)
            except Exception as e:
                print(f"Could not look up details for {p['title']}: {e}")
                p["doi"], full = None, None
            time.sleep(1)
        p["full_authors"] = full
        if full:
            p["authors"] = full
        p["url"] = f"https://doi.org/{p['doi']}" if p["doi"] else p["scholar_url"]
        p["summary"] = summaries.get(norm(p["title"]), "")
        if not p["summary"]:
            print(f"No summary yet in summaries.json: {p['title']}")

    if old.get("publications") == pubs:
        print(f"No change ({len(pubs)} publications).")
        return
    OUT.write_text(json.dumps({
        "profile": PROFILE,
        "updated": date.today().isoformat(),
        "publications": pubs,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved {len(pubs)} publications.")


if __name__ == "__main__":
    sys.exit(main())
