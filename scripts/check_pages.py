#!/usr/bin/env python3
"""Verify the built sitemap, all static result pages and all of their internal links."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote
import json
import xml.etree.ElementTree as ET

BASE="https://coolcode.ca/offshorerecords/"
DIST=Path(__file__).resolve().parents[1]/"dist"


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.h1s=0
        self.canonicals=[]
        self.descriptions=[]
        self.refs=[]
        self.jsonld=False

    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=="h1":
            self.h1s+=1
        if tag=="meta" and attrs.get("name")=="description":
            self.descriptions.append(attrs.get("content",""))
        if tag=="link" and attrs.get("rel")=="canonical":
            self.canonicals.append(attrs["href"])
        if tag=="a" and attrs.get("href"):
            self.refs.append(attrs["href"])
        if tag=="script" and attrs.get("type")=="application/ld+json":
            self.jsonld=True


def main():
    urls=[n.text for n in ET.parse(DIST/"sitemap.xml").findall(".//{*}loc")]
    if len(urls)!=len(set(urls)) or BASE+"places/can/" not in urls:
        raise ValueError("Invalid sitemap membership")
    directory=(DIST/"records/index.html").read_text()
    for u in [BASE,*urls]:
        if not u.startswith(BASE) or not u.endswith("/"):
            raise ValueError("Every canonical must belong to the atlas")
        path=DIST/u[len(BASE):]/"index.html"
        html=path.read_text(encoding="utf-8")
        p=Page()
        p.feed(html)
        if p.h1s!=1 or p.canonicals!=[u] or len(p.descriptions)!=1 or not p.descriptions[0].strip():
            raise ValueError(f"Incomplete search metadata: {u}")
        if "{{" in html:
            raise ValueError(f"Unresolved build placeholder in {u}")
        if u not in (BASE,BASE+"records/") and '../'+u[len(BASE):]+'"' not in directory:
            raise ValueError("Result missing from public directory: "+u)
        for href in p.refs:
            link=urlsplit(href)
            if link.netloc or link.scheme or not link.path or link.path.startswith("/"):
                continue
            local=(path.parent/unquote(link.path)).resolve()
            if not local.is_relative_to(DIST) or not (local.is_file() or (local/"index.html").is_file()):
                raise ValueError(f"{u} links to missing local resource: {href}")
    n=json.loads((DIST/"data/status.json").read_text())["sitemap_count"]
    if n!=len(urls):
        raise ValueError("Status count differs from sitemap")
    print(f"Verified {n} source-linked sitemap pages and the explorer.")


if __name__=="__main__":
    main()
