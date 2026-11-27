"""Build aggregate counts from ICIJ's public CSV ZIP. The retained edition has no individual-level data."""
import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
import csv
from datetime import date, datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import unicodedata
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import zipfile


ROOT = Path(__file__).resolve().parents[1]
KINDS = ("entities", "officers", "intermediaries", "addresses", "others")
BASE = "https://offshoreleaks.icij.org"


def complete_counts(counts):
    return {kind: counts[kind] for kind in KINDS}


def slug(value):
    ascii_name = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")


@contextmanager
def archive_file(local, url):
    if local:
        yield local
        return
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "icij.zip"
        request = Request(url, headers={"User-Agent": "CoolCode Offshore Records (+https://coolcode.ca/)"})
        with urlopen(request, timeout=120) as source, path.open("wb") as destination:
            shutil.copyfileobj(source, destination, length=1024 * 1024)
        yield path


def edition_date(archive):
    dates = [match[1] for path in archive.namelist() if (match := re.fullmatch(r"GENERATED_ON_(\d{8})\.txt", path))]
    if len(dates) != 1:
        raise ValueError("Expected a single dated ICIJ edition marker")
    return datetime.strptime(dates[0], "%Y%m%d").date()


def labels_by_jurisdiction(config):
    lookup = {}
    for key, group in config["jurisdictions"].items():
        for label in group["labels"]:
            if label in lookup:
                raise ValueError(f"Ambiguous jurisdiction label {label!r}")
            lookup[label] = key
    return lookup


def aggregate(path, config, checked):
    with path.open("rb") as fp:
        digest = hashlib.file_digest(fp, "sha256").hexdigest()
    names = config["countries"]
    unassigned_tags = set(config["nonstandard_country_tags"]) | {"XXX"}
    jurisdiction_keys = labels_by_jurisdiction(config)
    unassigned_jurisdictions = set(config["unidentified_jurisdiction_labels"])
    investigations = {row["name"]: row["id"] for row in config["investigations"]}
    ids = list(investigations.values())
    provider_counts = defaultdict(Counter)
    global_counts = defaultdict(Counter)
    linked = defaultdict(lambda: defaultdict(Counter))
    incorporated = defaultdict(Counter)
    source_codes = defaultdict(set)
    direct_unknown = defaultdict(Counter)
    unknown_jurisdictions = Counter()
    unknown_tags = Counter()
    with zipfile.ZipFile(path) as archive:
        generated = edition_date(archive)
        if generated > checked:
            raise ValueError("Archive edition is newer than its observation date")
        for kind in KINDS:
            seen_ids = set()
            filename = f"nodes-{kind}.csv"
            if archive.namelist().count(filename) != 1:
                raise ValueError(f"Expected one {filename}")
            with archive.open(filename) as data, io.TextIOWrapper(data, encoding="utf-8-sig", newline="") as fp:
                rows = csv.DictReader(fp)
                required = {"node_id", "sourceID", "country_codes"}
                if kind == "entities":
                    required.update(("jurisdiction", "jurisdiction_description"))
                if not required.issubset(rows.fieldnames or []):
                    raise ValueError(f"Source schema changed in {filename}")
                for row in rows:
                    # The same node can have different roles in different tables. Each
                    # typed ID is unique within its table in the source edition.
                    node = int(row["node_id"])
                    if node in seen_ids or node <= 0:
                        raise ValueError(f"Duplicate or invalid typed node in {filename}")
                    seen_ids.add(node)
                    source = row["sourceID"].strip()
                    investigation = investigations[source.split(" - ", 1)[0]]
                    provider_counts[source][kind] += 1
                    global_counts[investigation][kind] += 1
                    # Multi-country strings are not always positionally aligned with the
                    # countries column. Use the direct codes, trimming spaces per tag.
                    tags = {v.strip() for v in row["country_codes"].split(";") if v.strip()}
                    assigned = False
                    for code in tags:
                        if code in names:
                            linked[code][investigation][kind] += 1
                            assigned = True
                        elif code in unassigned_tags:
                            unknown_tags[code] += 1
                        else:
                            raise ValueError(f"Unreviewed country code {code!r} in {filename}")
                    if not assigned:
                        direct_unknown[investigation][kind] += 1
                    if kind == "entities":
                        description = row["jurisdiction_description"].strip()
                        if description in unassigned_jurisdictions:
                            unknown_jurisdictions[investigation] += 1
                        else:
                            key = jurisdiction_keys[description]
                            incorporated[key][investigation] += 1
                            raw_code = row["jurisdiction"].strip()
                            if raw_code:
                                source_codes[raw_code].add(key)
            if len(seen_ids) < config["minimum_counts"][kind]:
                raise ValueError(f"Unexpectedly small {filename}; examine the archive before publishing")
    if set(global_counts) != set(ids):
        raise ValueError("An expected investigation is missing")
    sources = [{**spec, "counts": complete_counts(global_counts[spec['id']])} for spec in config["investigations"]]
    countries = [{"code": code, "name": names[code], "investigations": {
        i: complete_counts(counts[i]) for i in ids
    }} for code, counts in sorted(linked.items(), key=lambda item: names[item[0]])]
    jurisdictions = []
    for key, counts in sorted(incorporated.items(), key=lambda item: config["jurisdictions"][item[0]]["name"]):
        group = config["jurisdictions"][key]
        raw_codes = sorted(code for code, keys in source_codes.items() if key in keys)
        url = config["source_url"]
        if raw_codes and all(source_codes[code] == {key} for code in raw_codes):
            url = BASE + "/search?" + urlencode({"j": ",".join(raw_codes)})
        jurisdictions.append({"code": key, "name": group["name"], "iso3": group["iso3"],
                              "source_codes": raw_codes, "url": url,
                              "investigations": {i: counts[i] for i in ids}})
    providers = [{"id": slug(source), "name": source, "investigation": investigations[source.split(" - ", 1)[0]],
                  "counts": complete_counts(values)} for source, values in sorted(provider_counts.items())]
    if len({p["id"] for p in providers}) != len(providers):
        raise ValueError("Source label collision")
    for investigation in ids:
        classified = sum(row["investigations"][investigation] for row in jurisdictions)
        if classified + unknown_jurisdictions[investigation] != global_counts[investigation]["entities"]:
            raise ValueError("Incorporation counts do not reconcile")
    return {
        "checked_at": checked.isoformat(), "source_edition": generated.isoformat(), "source_sha256": digest,
        "source_url": config["source_url"], "download_url": config["download_url"],
        "attribution": config["attribution"], "licences": config["licences"],
        "coverage": "Full ICIJ CSV archive. Counts are unique node IDs within each record type. Each distinct directly tagged country receives one count. Source labels and entity incorporation jurisdictions are separate counts. Records without a recognized place remain in the worldwide source totals.",
        "investigations": sources, "countries": countries, "jurisdictions": jurisdictions, "providers": providers,
        "unassigned": {
            "linked_country": {i: complete_counts(direct_unknown[i]) for i in ids},
            "incorporation_jurisdiction": {i: unknown_jurisdictions[i] for i in ids},
            "unassigned_tag_occurrences": dict(sorted(unknown_tags.items()))
        }
    }


def collect(archive, config_path, output, checked):
    config = json.loads(config_path.read_text(encoding="utf-8"))
    with archive_file(archive, config["download_url"]) as path:
        result = aggregate(path, config, checked)
    if output.exists():
        previous = json.loads(output.read_text(encoding="utf-8"))
        if result["source_edition"] < previous["source_edition"]:
            raise ValueError("Older archive would replace a newer published edition")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent, mode="w", encoding="utf-8", delete=False) as fp:
        pending = Path(fp.name)
        try:
            json.dump(result, fp, ensure_ascii=False, separators=(",", ":"))
            fp.write("\n")
            fp.flush()
            os.fsync(fp.fileno())
        except BaseException:
            pending.unlink(missing_ok=True)
            raise
    pending.replace(output)
    print(f"ICIJ {result['source_edition']}: {len(result['countries'])} linked places, "
          f"{len(result['jurisdictions'])} incorporation jurisdictions, {len(result['providers'])} source labels")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="Read a previously downloaded official ZIP")
    parser.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    parser.add_argument("--config", type=Path, default=ROOT / "config/icij.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data/icij.json")
    args = parser.parse_args()
    collect(args.archive, args.config, args.output, args.as_of)
