"""Read outward investment positions from Statistics Canada table 36-10-0008-01."""
import argparse
import csv
from datetime import datetime, timezone
from io import BytesIO, TextIOWrapper
import json
from pathlib import Path
import unicodedata
from urllib.request import urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
URL = "https://www150.statcan.gc.ca/n1/tbl/csv/36100008-eng.zip"
TABLE = "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3610000801"
MEASURE = "Canadian direct investment abroad - total book value"
ALIASES = {"Czechia":"CZE", "Russian Federation":"RUS", "Türkiye":"TUR",
           "Eswatini":"SWZ", "Tanzania, United Republic of":"TZA",
           "Congo, Democratic Republic of the":"COD"}


def key(name):
    return "".join(c for c in unicodedata.normalize("NFKD", name.casefold()) if c.isalnum())


def summarize(rows, countries):
    names = {key(p["name"]): p["code"] for p in countries}
    names.update({key(n): code for n, code in ALIASES.items() if code in names.values()})
    series = {}
    years = set()
    for r in rows:
        if r["GEO"] != "Canada" or r["Canadian and foreign direct investment"] != MEASURE:
            continue
        code = names.get(key(r["Countries or regions"]))
        if not code:
            continue
        if (r["UOM"], r["SCALAR_FACTOR"]) != ("Dollars", "millions"):
            raise ValueError("Unexpected investment units")
        year = int(r["REF_DATE"])
        years.add(year)
        s = series.setdefault(code, {"label":r["Countries or regions"], "vector":r["VECTOR"], "values":{}})
        if s["vector"] != r["VECTOR"] or year in s["values"]:
            raise ValueError("Ambiguous investment series for " + code)
        s["values"][year] = {"amount":int(r["VALUE"]) if r["VALUE"] else None, "status":r["STATUS"]}
    recent = sorted(years)[-5:]
    if len(recent) != 5 or not all(c in series for c in ("BMU", "BRB", "USA")):
        raise ValueError("Expected dated investment series for Bermuda, Barbados and the United States")
    selected = {}
    for code, series_row in sorted(series.items()):
        values = {y: series_row["values"].get(y, {"amount":None,"status":".."}) for y in recent}
        if any(v["amount"] is not None for v in values.values()):
            selected[code] = {**series_row, "values":values}
    return {"source":TABLE, "download":URL, "measure":MEASURE, "years":recent, "countries":selected,
            "checked_at":datetime.now(timezone.utc).date().isoformat()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    if args.archive:
        contents = args.archive.read_bytes()
    else:
        with urlopen(URL, timeout=120) as response:
            contents = response.read()
    countries = json.loads((ROOT/"data/icij.json").read_text())["countries"]
    with ZipFile(BytesIO(contents)) as archive, archive.open("36100008.csv") as f:
        result = summarize(csv.DictReader(TextIOWrapper(f, encoding="utf-8-sig")), countries)
    (ROOT/"data/investment.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
