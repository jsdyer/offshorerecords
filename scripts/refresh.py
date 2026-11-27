#!/usr/bin/env python3
"""Validate each publisher's edition before installing the complete checked set."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
SOURCES=("icij","oecd","trails")


def refresh():
    with tempfile.TemporaryDirectory(dir=ROOT) as directory:
        work=Path(directory)
        for sub in ("collectors","config","data"):
            shutil.copytree(ROOT/sub,work/sub,ignore=shutil.ignore_patterns("__pycache__"))
        archive=work/"official-archive.zip"
        url=json.loads((work/"config/icij.json").read_text())["download_url"]
        req=Request(url,headers={"User-Agent":"CoolCode Offshore Records Atlas (+https://coolcode.ca/)"})
        with urlopen(req,timeout=120) as incoming, archive.open("wb") as dest:
            shutil.copyfileobj(incoming,dest,1024*1024)
        def run(source):
            args = {"icij":["--archive",str(archive)],"trails":[str(archive)],"oecd":[]}[source]
            subprocess.run([sys.executable,"collectors/"+source+".py",*args],cwd=work,check=True,timeout=1100)
        with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
            list(pool.map(run,SOURCES))
        # Install only completed collectors. GitHub publishes after the full build and browser checks.
        for src in SOURCES:
            candidate=work/"data"/(src+".json")
            if not isinstance(json.loads(candidate.read_text(encoding="utf-8")),dict):
                raise ValueError(f"Invalid saved edition from {src}")
        for src in SOURCES:
            name=src+".json"
            os.replace(work/"data"/name,ROOT/"data"/name)
        print("Verified all archive, role and transparency inputs on "+datetime.now(timezone.utc).date().isoformat())


if __name__ == "__main__":
    refresh()
