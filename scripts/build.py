#!/usr/bin/env python3
"""Build the explorer, country and investigation pages from locally saved editions."""
from collections import Counter
from datetime import date
from html import escape
import json
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlencode, urlsplit
from xml.etree import ElementTree as ET
from search_metadata import add_search_metadata

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://coolcode.ca/offshorerecords/"
ICIJ = "https://offshoreleaks.icij.org"
NOTE = "https://coolcode.ca/field-notes/reading-offshore-records/"
KINDS = ("entities", "officers", "intermediaries", "addresses", "others")
LABELS = ("Entities", "Officers", "Intermediaries", "Addresses", "Other records")
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def e(value):
    return escape(str(value), quote=True)


def link(href, title):
    return f'<a href="{e(href)}">{e(title)}</a>'


def sourced(href, title):
    u = urlsplit(href)
    if u.scheme != "https" or not u.hostname or u.username or u.password:
        raise ValueError("Source links must use HTTPS")
    return link(href, title)


def put(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def check_counts(counts):
    if any(type(counts.get(k)) is not int or counts[k] < 0 for k in KINDS):
        raise ValueError(f"Missing or invalid typed archive counts: {counts}")


def check_archive(ed):
    date.fromisoformat(ed["checked_at"][:10])
    ids = [inv["id"] for inv in ed["investigations"]]
    if len(ids) != len(set(ids)) or not all(SLUG.fullmatch(r) for r in ids):
        raise ValueError("Investigation routes must be unique")
    codes = [p["code"] for p in ed["countries"]]
    if "CAN" not in codes or len(codes) != len(set(codes)):
        raise ValueError("Missing Canada or duplicate linked-country codes")
    for p in ed["countries"]:
        if not re.fullmatch("[A-Z]{2,3}",p["code"]) or not p["name"]:
            raise ValueError(f'Invalid linked country: {p["code"]}')
        if set(p["investigations"]) != set(ids):
            raise ValueError(f'Incomplete release counts for {p["code"]}')
        for counts in p["investigations"].values():
            check_counts(counts)
    for inv in ed["investigations"]:
        check_counts(inv["counts"])
        sourced(inv["url"],inv["name"])


def archive_url(inv, code):
    return ICIJ+"/investigations/"+inv["id"]+"?"+urlencode({"c":code})


def browse(page, title, desc, body):
    prefix = "../"*page.count("/")
    return f'''<!doctype html><html lang="en-CA"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)} · Offshore Records Atlas</title>
<meta name="description" content="{e(desc)}"><link rel="canonical" href="{BASE}{page}">
<meta property="og:type" content="website"><meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}"><meta property="og:url" content="{BASE}{page}">
<link rel="stylesheet" href="{prefix}profiles.css"><link rel="icon" href="{prefix}favicon.svg">
<script defer src="/assets/tool-metrics.js" referrerpolicy="no-referrer"></script></head>
<body class="record-page" data-tool-id="offshorerecords"><header><nav class="record-wrap">{link(prefix,"Offshore Records Atlas")} {link(prefix+"records/","Country and investigation index")} {link("https://coolcode.ca/","CoolCode.ca")}</nav></header>
<main class="record-wrap"><h1>{e(title)}</h1>{body}</main>
<footer><div class="record-wrap">{link(NOTE,"Field note on Canadian offshore records")} {link(ICIJ+"/pages/database","Data from ICIJ · ODbL and CC BY-SA")} {link("https://coolcode.ca/report/?tool=offshorerecords","Report a correction")}</div></footer></body></html>'''


def table(caption, headings, rows):
    head = "".join(f'<th scope="col">{e(h)}</th>' for h in headings)
    cells = []
    for first,rest in rows:
        cells.append('<tr><th scope="row">'+first+'</th>'+''.join('<td>'+x+'</td>' for x in rest)+'</tr>')
    return '<table><caption>'+e(caption)+'</caption><thead><tr>'+head+'</tr></thead><tbody>'+''.join(cells)+'</tbody></table>'


def place_table(country, investigations):
    rows=[]
    for inv in investigations:
        counts=country["investigations"][inv["id"]]
        rows.append((sourced(archive_url(inv,country["code"]),inv["name"]),[f"{counts[k]:,}" for k in KINDS]))
    return table(f'Directly country-tagged records for {country["name"]}',["Investigation",*LABELS],rows)


def review_section(reviews):
    content=["<h2>OECD tax-information exchange reviews</h2><p>The OECD Global Forum assesses how well a jurisdiction can exchange information on a foreign tax authority’s request. The assessment applies to that jurisdiction and review period.</p><ul>"]
    assessments = [r for j in reviews for r in j["reviews"]]
    for r in sorted(assessments,key=lambda item:str(item.get("published_on") or item.get("review_year") or ""),reverse=True):
        date_label=r.get("published_on") or r.get("review_year")
        details=[r.get("rating"),f'Round {r["round"]}' if r.get("round") else None,date_label,r.get("status")]
        label=" · ".join(dict.fromkeys(str(v) for v in details if v))
        content.append("<li>"+e(label)+" · "+sourced(r["url"],"Review source")+"</li>")
    return "".join(content)+"</ul>"


def jurisdiction_page(j,ed,reviews):
    if not SLUG.fullmatch(j["code"]):
        raise ValueError("Invalid incorporation label")
    total=sum(j["investigations"].values())
    title=j["name"]+" as an offshore incorporation jurisdiction"
    desc=f'ICIJ’s archive contains {total:,} entity records with {j["name"]} as their incorporation jurisdiction. See the counts by investigation.'
    rows=[]
    for inv in ed["investigations"]:
        rows.append((link("../../investigations/"+inv["id"]+"/",inv["name"]),
                     [f'{j["investigations"].get(inv["id"],0):,}',e(inv["coverage"])]))
    body=[f'<p class="lead">{e(desc)}</p><p>Archive edition {e(ed["source_edition"])}. '+sourced(j["url"],"ICIJ data and definitions")+'</p>',
          '<p>'+link("../../?jurisdiction="+j["code"]+"#jurisdictions","Compare this incorporation jurisdiction")+'</p>',
          '<div class="record-scroll" tabindex="0">'+table("Entity records with this jurisdiction label",["Investigation","Entity records","Historical coverage"],rows)+'</div>',
          '<p>These are the companies, foundations or trusts appearing in the contributing files. The mix of service providers and registries determines which places appear most often.</p>']
    if reviews:
        body.append(review_section(reviews))
    elif not j.get("iso3"):
        body.append("<p>The archive uses a historical, regional or otherwise distinct jurisdiction label. The atlas has no verified OECD match for this label.</p>")
    else:
        body.append("<p>This edition has no matching OECD review for this jurisdiction.</p>")
    return "incorporation/"+j["code"]+"/",title,desc,"".join(body)


def place_page(p, ed, incs, reviews):
    code=p["code"]
    name=p["name"]
    totals=Counter()
    for counts in p["investigations"].values():
        totals.update(counts)
    title=f"{name} in the offshore investigations"
    desc=(f'The archive records {totals["entities"]:,} entity records and {totals["officers"]:,} '
          f'officer records directly linked to {name}. Explore the breakdown across investigations.')
    body=[f'<p class="lead">{e(desc)}</p><p>{link("../../?country="+code,"Explore this country in the atlas")}</p>',
          f'<p>ICIJ export dated {e(ed["source_edition"])}. Archive checked {e(ed["checked_at"])}. Each investigation has its own historical coverage.</p>',
          '<div class="record-scroll" tabindex="0" role="region" aria-label="Record counts">'+place_table(p,ed["investigations"])+'</div>',
          '<p>Each row counts records carrying this country tag. A tag can identify a correspondence address or other source-specific connection. One record can carry several country tags. Officer records include both people and organizations.</p>']
    if incs:
        rows=[]
        for inv in ed["investigations"]:
            n=sum(j["investigations"].get(inv["id"],0) for j in incs)
            rows.append((link("../../investigations/"+inv["id"]+"/",inv["name"]),[f"{n:,}"]))
        body.append('<h2>Place of incorporation</h2><p>This separate count uses the jurisdiction on the entity record. An officer’s location can differ from the place where the entity was formed.</p>'+table("Entity records incorporated here",["Investigation","Entity records"],rows))
    if reviews:
        body.append(review_section(reviews))
    body.append('<h2>Reading the figures</h2><p>Each investigation covers a particular set of providers or registries and a particular period. These counts cannot establish current ownership, the value of assets, taxes paid or wrongdoing. '+sourced(ICIJ+"/pages/data","ICIJ source coverage")+'.</p>')
    return f"places/{code.lower()}/",title,desc,"".join(body)


def investigation_page(inv,ed,countries):
    counts=inv["counts"]
    title=inv["name"]+" records and source coverage"
    desc=(f'This archive edition contains {counts["entities"]:,} {inv["name"]} entity records '
          f'and {counts["officers"]:,} officer records.')
    body=[f'<p class="lead">{e(desc)}</p><p>{e(inv["coverage"])} {sourced(inv["url"],"Open the investigation at ICIJ")}.</p>',
          table("Records by type",["Record type","Records"],[(e(label),[f"{counts[k]:,}"]) for k,label in zip(KINDS,LABELS)])]
    providers=[r for r in ed["providers"] if r["investigation"]==inv["id"]]
    if providers:
        rows=[(e(r["name"]),[f'{r["counts"][k]:,}' for k in KINDS]) for r in sorted(providers,key=lambda x:x["name"])]
        body+=['<h2>Contributing sources</h2><div class="record-scroll" tabindex="0">'+table("Archive records by provider or registry",["Source",*LABELS],rows)+'</div>']
    linked=[p for p in countries if any(p["investigations"][inv["id"]].values())]
    body.append('<h2>Places with tagged records in this investigation</h2><ul class="record-index">')
    for p in linked:
        body.append('<li>'+link("../../places/"+p["code"].lower()+"/",p["name"])+'</li>')
    body.append('</ul><p>Entity, officer and address records have different meanings. A company’s country tag and its jurisdiction of incorporation can differ.</p>')
    return "investigations/"+inv["id"]+"/",title,desc,"".join(body)


def trail_page(trail,checked):
    if not SLUG.fullmatch(trail["id"]):
        raise ValueError("Invalid trail route")
    path="trails/"+trail["id"]+"/"
    nodes={str(n["id"]):n for n in trail["nodes"]}
    rows=[]
    for edge in trail["edges"]:
        start,end=nodes[str(edge["from"])],nodes[str(edge["to"])]
        dates=" to ".join(str(v or "unrecorded") for v in (edge.get("start_date"),edge.get("end_date")))
        rows.append((sourced(start["url"],start["name"]),[e(edge["role"]),sourced(end["url"],end["name"]),e(dates)]))
    release=trail["dataset"]
    body=[f'<p class="lead">{e(trail["summary"])}</p><p>{e(release)} · Source records through {e(trail["source_cutoff"])} · Checked {e(checked)}</p>',
          '<div class="record-scroll" tabindex="0">'+table("Relationships recorded in the source",["Organization","Recorded role","Connected entity","Start to end"],rows)+'</div>',
          '<h2>Locations in the underlying records</h2><ul>']
    for n in nodes.values():
        connection=", ".join(n["countries"]) or "No country tag supplied"
        location="Incorporation jurisdiction: "+n["jurisdiction"] if n.get("jurisdiction") else "No incorporation jurisdiction supplied on this record"
        body.append('<li>'+sourced(n["url"],n["name"])+f' — {e(n["kind"])}. Linked countries: {e(connection)}. {e(location)}.</li>')
    body+=['</ul><h2>How to read this example</h2><p>'+e(trail["note"])+'</p>',
           '<p>ICIJ’s historical records document the roles shown above. This entry supplies no finding of tax evasion or other misconduct.</p>',
           '<p>'+link("../../#trails","Explore more organization relationships")+'</p>']
    return path,trail["title"],trail["summary"],"".join(body)


def build(root=ROOT):
    ed=read(root/"data/icij.json")
    check_archive(ed)
    oecd=read(root/"data/oecd.json")
    trails=read(root/"data/trails.json")
    if not trails.get("trails") or not oecd.get("jurisdictions"):
        raise ValueError("Expected sourced role examples and OECD reviews")
    countries=sorted(ed["countries"],key=lambda p:p["name"].casefold())
    tool=read(root/"tool.json")
    with tempfile.TemporaryDirectory(dir=root) as tmp:
        stage=Path(tmp)/"site"
        shutil.copytree(root/"web",stage)
        shutil.copytree(root/"assets",stage,dirs_exist_ok=True)
        shutil.copytree(root/"data",stage/"data",dirs_exist_ok=True)
        if not (stage/"favicon.svg").is_file():
            raise ValueError("Expected a tool favicon")
        hrefs=[]
        def save(spec):
            path,title,desc,body=spec
            put(stage/path/"index.html",browse(path,title,desc,body))
            hrefs.append(path)
        for p in countries:
            incs=[j for j in ed["jurisdictions"] if j.get("iso3")==p["code"]]
            reviews=[r for r in oecd["jurisdictions"] if r.get("iso3")==p["code"]]
            save(place_page(p,ed,incs,reviews))
        for j in ed["jurisdictions"]:
            reviews=[r for r in oecd["jurisdictions"] if j.get("iso3") and r.get("iso3")==j["iso3"]]
            save(jurisdiction_page(j,ed,reviews))
        for inv in ed["investigations"]:
            save(investigation_page(inv,ed,countries))
        for trail in trails["trails"]:
            save(trail_page(trail,trails["checked_at"]))
        directory='<p class="lead">Read how a country appears in the archive, or start with an investigation to check its coverage and contributing sources.</p><h2>Investigations</h2><ul>'
        directory+="".join('<li>'+link("../investigations/"+i["id"]+"/",i["name"])+'</li>' for i in ed["investigations"])
        directory+='</ul><h2>Documented organization relationships</h2><ul>'
        directory+="".join('<li>'+link("../trails/"+t["id"]+"/",t["title"])+'</li>' for t in trails["trails"])
        directory+='</ul><h2>Incorporation jurisdictions</h2><ul class="record-index">'
        directory+="".join('<li>'+link("../incorporation/"+j["code"]+"/",j["name"])+'</li>' for j in ed["jurisdictions"])
        directory+='</ul><h2>Linked countries and territories</h2><ul class="record-index">'
        directory+="".join('<li>'+link("../places/"+p["code"].lower()+"/",p["name"])+'</li>' for p in countries)+'</ul>'
        save(("records/","Offshore records by country and investigation","Browse source-linked summaries of countries and investigations in ICIJ’s Offshore Leaks Database.",directory))
        index=(stage/"index.html").read_text()
        if index.count("{{CANADA}}")!=1:
            raise ValueError("Missing Canada opening table")
        index=index.replace("{{CANADA}}",place_table(next(p for p in countries if p["code"]=="CAN"),ed["investigations"]))
        dataset={"@type":"Dataset","@id":BASE+"#archive","name":"Offshore Leaks record counts by country and investigation",
                 "creator":{"@type":"Organization","name":"International Consortium of Investigative Journalists"},
                 "isBasedOn":ed["source_url"],"license":"https://opendatacommons.org/licenses/odbl/1-0/",
                 "distribution":{"@type":"DataDownload","contentUrl":BASE+"data/icij.json","encodingFormat":"application/json"}}
        put(stage/"index.html",add_search_metadata(index,tool,category="ReferenceApplication",datasets=[dataset]))
        xml=ET.Element("urlset",xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
        for path in sorted(hrefs):
            ET.SubElement(ET.SubElement(xml,"url"),"loc").text=BASE+path
        put(stage/"sitemap.xml",ET.tostring(xml,encoding="unicode",xml_declaration=True))
        # Oldest verified component is the latest date through which all three inputs were checked.
        dates=[ed["checked_at"],oecd["source"]["checked_at"],trails["checked_at"]]
        checked=min(date.fromisoformat(v[:10]) for v in dates).isoformat()
        status={"checked_at":checked,"archive_checked_at":ed["checked_at"],"country_count":len(countries),
                "investigation_count":len(ed["investigations"]),"jurisdiction_count":len(ed["jurisdictions"]),
                "entity_count":sum(i["counts"]["entities"] for i in ed["investigations"]),
                "source_edition":ed.get("source_edition"),"oecd_checked_at":oecd["source"]["checked_at"],
                "trails_checked_at":trails["checked_at"],"trail_count":len(trails["trails"]),"sitemap_count":len(hrefs)}
        put(stage/"data/status.json",json.dumps(status,indent=2)+"\n")
        put(stage/".nojekyll","")
        dest=root/"dist"
        if dest.exists():
            shutil.rmtree(dest)
        stage.rename(dest)
        print(f"Built {len(countries)} linked-country profiles and {len(hrefs)} sitemap entries.")


if __name__=="__main__":
    build()
