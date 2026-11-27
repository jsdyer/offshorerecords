"""Refresh OECD Global Forum jurisdiction-level exchange-on-request assessments."""
import argparse
import csv
from datetime import date, datetime, timezone
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
import unicodedata
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
LANDING = "https://www.oecd.org/en/networks/global-forum-tax-transparency/resources/exchange-of-information-on-request-ratings.html"
PUBLICATIONS = "https://api.crossref.org/works"
SERIES_FILTER = "issn:2219-469X"
RATINGS = {"Compliant", "Largely Compliant", "Partially Compliant", "Non-Compliant"}
PHASES = {
    "Phase 1 only*": "Phase 1 only. Pandemic-related travel restrictions delayed the practical assessment.",
    "Phase 1 only**": "Phase 1 only. Limited exchange experience; practical assessment pending.",
    "Phase 1 only***": "Phase 1 only. The necessary legal and regulatory framework was not in place."
}
LABEL = re.compile(r"^:([a-z]{2}):\s*(.+?)(?:\s*\((Round 2|Round 2 suppl\.|Round 2 in-depth|fast-track|suppl\.)\))?$")
REPORT_TITLE = re.compile(r"^Global Forum on Transparency and Exchange of Information for Tax Purposes(?: Peer Reviews)?:\s*(.+?)\s+(\d{4})\b(.*)$", re.I)
# The two deposited series titles split the jurisdictions across two records.
# The OECD publication landing pages and PDF covers verify these report subjects.
CORRECTED_REPORT_TITLES = {"10.1787/997a7b23-en": "Spain", "10.1787/5a837e0a-en": "Turks and Caicos Islands"}
REPORT_NAMES = {
    "congo republic of the": "congo", "china": "peoples republic of china",
    "bahamas": "the bahamas", "micronesia": "federated states of micronesia",
    "naoero": "nauru", "netherlands": "the netherlands", "philippines": "the philippines",
    "north macedonia": "republic of north macedonia",
    "russia": "russian federation", "the gambia": "gambia",
    "slovakia": "slovak republic", "czechia": "czech republic",
    "hong kong": "hong kong china", "macao china": "macau china"
}


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.iframes = []
        self.redirects = []
        self.text = []
        self.silent = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style"):
            self.silent += 1
        if tag == "iframe" and "exchange of information on request" in a.get("title", "").lower():
            self.iframes.append(a.get("src", ""))
        if tag == "meta" and a.get("http-equiv", "").lower() == "refresh":
            self.redirects.append(a.get("content", ""))

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.silent:
            self.silent -= 1

    def handle_data(self, data):
        if not self.silent:
            self.text.append(data)

    @classmethod
    def parse(cls, data):
        p = cls()
        p.feed(data.decode("utf-8-sig"))
        p.close()
        return p


def fetch(url):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; CoolCode public reference research; +https://coolcode.ca/)"})
    with urlopen(request, timeout=40) as r:
        if urlsplit(r.geturl()).netloc != urlsplit(url).netloc:
            raise ValueError("Unexpected source redirect host")
        data = r.read(7_000_001)
    if not data or len(data) > 7_000_000:
        raise ValueError("Unexpected source size")
    return data


def chart_data(get):
    landing = Page.parse(get(LANDING + "?lang=en"))
    if len(landing.iframes) != 1:
        raise ValueError("Expected one EOIR chart on the OECD ratings page")
    chart = landing.iframes[0]
    if not re.fullmatch(r"https://datawrapper\.dwcdn\.net/[A-Za-z0-9]+/", chart):
        raise ValueError("Unexpected chart publisher or ID")
    redirect = Page.parse(get(chart))
    if len(redirect.redirects) != 1:
        raise ValueError("Expected a versioned publisher chart redirect")
    match = re.fullmatch(r"\s*\d+\s*;\s*url\s*=\s*([^\s]+)\s*", redirect.redirects[0], re.I)
    if not match or not re.fullmatch(re.escape(chart) + r"[1-9][0-9]*/", match[1]):
        raise ValueError("Chart redirect does not belong to the OECD embed")
    version = match[1]
    text = " ".join(" ".join(Page.parse(get(version)).text).split())
    stamp = re.search(r"Last update:\s*(\d{1,2} [A-Za-z]+ \d{4})", text, re.I)
    if not stamp or "exchange of information on request" not in text.lower():
        raise ValueError("Missing exchange-on-request chart date or title")
    updated = datetime.strptime(stamp[1], "%d %B %Y").date().isoformat()
    data_url = urljoin(version, "data.csv")
    return version, updated, get(data_url), data_url


def namekey(s):
    s = unicodedata.normalize("NFKD", s.casefold().replace("’", "'")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.replace("'", "")).strip()


def publications(get):
    rows, offset = [], 0
    while True:
        query = urlencode({"filter": SERIES_FILTER, "rows": 1000, "offset": offset,
                           "select": "DOI,title,published"})
        response = json.loads(get(PUBLICATIONS + "?" + query))["message"]
        items = response["items"]
        if not items:
            raise ValueError("Incomplete OECD report-series metadata")
        rows.extend(items)
        offset += len(items)
        if offset >= response["total-results"]:
            if offset != response["total-results"] or len({r["DOI"] for r in rows}) != offset:
                raise ValueError("Inconsistent OECD report-series pagination")
            break
    found = {}
    for row in rows:
        title = (row.get("title") or [""])[0]
        m = REPORT_TITLE.match(title)
        doi = row["DOI"].lower()
        if not m or not re.fullmatch(r"10\.1787/[a-z0-9]+-en", doi):
            continue
        name, year, suffix = m[1], int(m[2]), m[3].casefold()
        name = CORRECTED_REPORT_TITLES.get(doi, name)
        parts = row.get("published", {}).get("date-parts", [[]])[0]
        if not parts or parts[0] != year:
            continue
        review_type = ("fast-track" if "fast-track" in suffix else "supplementary" if "supplement" in suffix
                       else "in-depth" if "in-depth" in suffix else "regular")
        phase = "phase 1" in suffix
        review_round = 2 if "second round" in suffix or "round 2" in suffix else None
        item = {"url": "https://doi.org/" + doi, "published_on": date(*parts).isoformat() if len(parts) == 3 else None,
                "round": review_round, "phase_1": phase}
        found.setdefault((namekey(name), year, review_type), []).append(item)
    return found


def parse_rows(raw, version_url, reports, codes):
    source = csv.reader(io.StringIO(raw.decode("utf-8-sig")))
    header = next(source)
    if header[:2] != ["Jurisdiction", "Year of publication"] or len(header) != 13 or "overall" not in header[2].lower():
        raise ValueError("Unexpected OECD assessment table columns")
    groups = {}
    for fields in source:
        if len(fields) != len(header):
            raise ValueError("Incomplete OECD assessment row")
        label, published, result = (s.strip() for s in fields[:3])
        m = LABEL.fullmatch(label)
        if not m or (m[2].endswith(")") and m[3] is None and m[2] != "Congo (Republic of the)"):
            raise ValueError(f"Unrecognized jurisdiction/review label: {label}")
        alpha2, name, stage = m[1].upper(), m[2].strip(), m[3] or ""
        if alpha2 not in codes:
            raise ValueError("Unmapped OECD jurisdiction code: " + alpha2)
        year = None if published == "n/a" else int(published)
        if (result == "Not yet reviewed") != (year is None):
            raise ValueError("Unexpected publication year for " + label)
        rating = None
        provisional = result.startswith("Provisionally ")
        if result in RATINGS or (provisional and result.removeprefix("Provisionally ") in RATINGS):
            rating = result
            status = ("Provisional fast-track rating" if provisional else "Supplementary peer review"
                      if "suppl." in stage else "In-depth peer review" if "in-depth" in stage else "Full peer review")
        elif result in PHASES:
            status = PHASES[result]
        elif result == "Not yet reviewed":
            status = result
        else:
            raise ValueError("Unrecognized OECD assessment: " + result)
        round_num = 2 if stage.startswith("Round 2") else 1 if year and year <= 2016 else None
        kind = ("fast-track" if stage == "fast-track" else "supplementary" if "suppl." in stage
                else "in-depth" if "in-depth" in stage else "regular")
        key = namekey(name)
        matches = reports.get((key, year, kind), []) or reports.get((REPORT_NAMES.get(key), year, kind), [])
        matches = [r for r in matches if not (r["phase_1"] and result not in PHASES)
                   and (round_num != 1 or r["round"] != 2)]
        report = matches[0] if len(matches) == 1 else {}
        review = {"rating": rating, "round": round_num or report.get("round"), "review_year": year,
                  "status": status, "source_outcome": result, "published_on": report.get("published_on"),
                  "url": report.get("url", version_url)}
        group = groups.setdefault(alpha2, {"jurisdiction": name, "iso3": codes[alpha2], "reviews": []})
        if group["jurisdiction"] != name:
            raise ValueError("Multiple jurisdiction names share " + alpha2)
        group["reviews"].append(review)
    if not groups:
        raise ValueError("OECD assessment table is empty")
    result = []
    for g in groups.values():
        rows = g["reviews"]
        if len(rows) > 1 and any(r["review_year"] is None for r in rows):
            raise ValueError("Unreviewed status conflicts with earlier review for " + g["jurisdiction"])
        # For same-year reassessments, retain the publisher's sequence.
        rows.sort(key=lambda r: r["review_year"] or 0)
        result.append({**g, **rows[-1]})
    return sorted(result, key=lambda x: x["jurisdiction"].casefold())


def build(get, codes, checked_at):
    version, updated, data, data_url = chart_data(get)
    rows = parse_rows(data, version, publications(get), codes)
    if updated > checked_at or any(x["review_year"] and x["review_year"] > int(updated[:4]) for x in rows):
        raise ValueError("Source date falls after the reference edition")
    return {
        "source": {
            "name": "OECD Global Forum on Transparency and Exchange of Information for Tax Purposes",
            "url": LANDING, "edition_url": version, "data_url": data_url, "updated_at": updated, "checked_at": checked_at,
            "scope": "Jurisdiction-level peer reviews of how tax authorities provide information on request. Each jurisdiction shows its latest listed assessment and the publisher’s review history. Years identify report publication. A Phase 1 assessment covers the legal framework and carries no overall rating. Monitoring updates are separate from rated peer reviews.",
            "report_dates": "Exact dates and report links come from unambiguous matches to OECD Publishing’s registered DOIs in the Global Forum series. Other entries link to the edition of the official ratings table.",
            "report_index_url": PUBLICATIONS + "?filter=" + SERIES_FILTER,
            "csv_sha256": hashlib.sha256(data).hexdigest(),
            "jurisdiction_count": len(rows), "assessment_rows": sum(len(r["reviews"]) for r in rows)
        },
        "jurisdictions": rows
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=ROOT / "data/oecd.json")
    args = p.parse_args()
    codes = json.loads((ROOT / "config/oecd-iso-codes.json").read_text())
    edition = build(fetch, codes, datetime.now(timezone.utc).date().isoformat())
    if args.output.exists():
        previous = json.loads(args.output.read_text())
        if edition["source"]["updated_at"] < previous["source"]["updated_at"]:
            raise ValueError("Older OECD edition; retained the last successful capture")
        before = {r["iso3"] for r in previous["jurisdictions"]}
        after = {r["iso3"] for r in edition["jurisdictions"]}
        if not before <= after:
            raise ValueError("OECD coverage lost previously listed jurisdictions; verify before replacing the existing capture")
    args.output.parent.mkdir(exist_ok=True, parents=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=args.output.parent, delete=False) as f:
        json.dump(edition, f, ensure_ascii=False, indent=2)
        f.write("\n")
    Path(f.name).replace(args.output)
    print(f"OECD edition {edition['source']['updated_at']}: {len(edition['jurisdictions'])} jurisdictions")


if __name__ == "__main__":
    main()
