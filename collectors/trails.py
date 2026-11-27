"""Recheck the curated relationship examples against the original ICIJ node pages.

    python collectors/trails.py
    python collectors/trails.py /path/to/full-ICIJ-download.zip

The optional ZIP cross-checks the public tables against ICIJ's bulk relationships.
A missing or altered source record retains the current output. After reviewing an
intentional change, rerun with --accept-changes. Standard library only.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from io import TextIOWrapper
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from urllib.request import Request, urlopen
from zipfile import ZipFile

BASE = 'https://offshoreleaks.icij.org/nodes/'
OUTPUT = Path(__file__).resolve().parents[1] / 'data' / 'trails.json'
# Only these editorially checked organizational records may enter the published file.
ORGANIZATIONS = {
    '240513158': 'Concilium Trustees Canada Inc. as trustee of THE ONEIPA TRUST',
    '240513157': 'Rocky Enterprises Limited', '240500922': 'ONEIPA LIMITED',
    '80025884': '726526 Ontario Inc.', '82003400': 'Clydesdale Holdings (Bermuda) Limited',
    '82001470': 'NATC HOLDING COMPANY, LTD.',
    '12095620': 'FIRESWIRL SYSTEMS INC.', '10202700': 'SWIRL MARKETING LIMITED',
    '56052846': 'BETSSON AB', '56072048': 'PRICEWATERHOUSECOOPERS',
    '56081303': 'BETSSON MALTA HOLDING LIMITED', '55027598': 'BML GROUP LIMITED',
    '51821': 'Cantox Inc.', '169305': 'Blue Trust',
    '23000002': 'M & A CORPORATE SERVICES LIMITED', '20135138': 'PUNTO LARGA LTD.',
}
# A receipt is the public page that lists every selected connection in a trail.
TRAILS = [
    ('canada-trustee-bvi', 'A Canadian trustee and a British Virgin Islands company',
     'ICIJ tags the corporate trustee as Canadian and lists it as a shareholder of ONEIPA LIMITED. The company record names Rocky Enterprises Limited as director.',
     'The shareholder record names the trustee acting for the trust. The director has a separate role.',
     '240500922', [('240513158', '240500922', 'Shareholder'), ('240513157', '240500922', 'Director')]),
    ('fireswirl-shareholding', 'When a shareholding began and ended',
     'The Panama Papers give both dates for Fireswirl Systems Inc.’s shareholding in Swirl Marketing Limited.',
     'ICIJ links the shareholder to Canada and the entity to Hong Kong. The entity’s registration jurisdiction is the British Virgin Islands.',
     '12095620', [('12095620', '10202700', 'Shareholder')]),
    ('ontario-bermuda', 'One Ontario shareholder, two Bermuda companies',
     'Appleby’s files list 726526 Ontario Inc. as a shareholder of Clydesdale Holdings (Bermuda) Limited and NATC Holding Company, Ltd.',
     'The two incorporation dates belong to the companies. The source gives no start or end date for either shareholding.',
     '80025884', [('80025884', '82003400', 'Shareholder'), ('80025884', '82001470', 'Shareholder')]),
    ('bml-betsson', 'Who appears on BML Group Limited’s Malta record?',
     'The Malta registry snapshot lists Betsson AB and Betsson Malta Holding Limited as shareholders. Pricewaterhousecoopers appears as auditor.',
     'The register dates BML Group Limited’s incorporation to 2004. The relationship rows leave the dates for these roles blank.',
     '55027598', [('56052846', '55027598', 'Shareholder'), ('56081303', '55027598', 'Shareholder'),
                  ('56072048', '55027598', 'Auditor')]),
    ('cantox-blue-trust', 'A Canadian organization recorded as a trust settlor',
     'Offshore Leaks identifies Cantox Inc. as the settlor of Blue Trust, registered in the Cook Islands.',
     'A settlor establishes a trust. The source gives a start date for this role and leaves the end date blank.',
     '51821', [('51821', '169305', 'Trust settlor')]),
    ('punto-larga-intermediary', 'The intermediary on a Bahamas company record',
     'The Bahamas Leaks registry names M & A Corporate Services Limited as an intermediary for Punto Larga Ltd.',
     'January 7, 2005 is the company’s incorporation date. The intermediary entry supplies no relationship dates.',
     '23000002', [('23000002', '20135138', 'Intermediary')]),
]


class PublicNodePage(HTMLParser):
    """Read the published connection table and its graph-node metadata."""
    def __init__(self):
        super().__init__()
        self.rows = []
        self.nodes = {}
        self.row = self.cell = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'tr':
            self.row = {}
        elif tag == 'td' and self.row is not None:
            self.cell = attrs.get('class', '')
            self.row[self.cell] = ''
        elif tag == 'a' and self.cell == 'description':
            link = re.fullmatch(r'/nodes/(\d+)', attrs.get('href', ''))
            if link:
                self.row['node_id'] = link[1]

    def handle_data(self, data):
        assignment = re.match(r'\s*document\.body\.nodeData\s*=\s*', data)
        if assignment:
            nodes, _ = json.JSONDecoder().raw_decode(data[assignment.end():])
            self.nodes.update({str(n['id']): n['data'] for n in nodes})
        elif self.cell is not None:
            self.row[self.cell] += data

    def handle_endtag(self, tag):
        if tag == 'td':
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            if 'node_id' in self.row and 'role' in self.row:
                self.rows.append({k: v.strip() for k, v in self.row.items()})
            self.row = None


def iso(value):
    if not value or value.strip() == '-':
        return None
    value = value.strip()
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return date.fromisoformat(value).isoformat()
    return datetime.strptime(value, '%d-%b-%Y').date().isoformat()


def fetch(node_id):
    req = Request(BASE + node_id, headers={'User-Agent': 'CoolCode Offshore Records source verification'})
    with urlopen(req, timeout=30) as response:
        if response.geturl().rstrip('/') != BASE + node_id:
            raise ValueError(f'Unexpected redirect for ICIJ node {node_id}')
        raw = response.read().decode('utf-8')
    page = PublicNodePage()
    page.feed(raw)
    page.close()
    return page


def project(plan, page):
    trail_id, title, summary, note, receipt, connections = plan
    root = page.nodes[receipt]['properties']
    dataset = root['sourceID']
    cutoff = re.fullmatch(r'.*current through (.*?)[.]?', root['valid_until'])
    if not cutoff:
        raise ValueError(f'Unknown source cutoff for {receipt}')
    nodes, edges = {}, []
    for left, right, role in connections:
        for node_id in (left, right):
            if node_id in nodes:
                continue
            raw = page.nodes[node_id]
            prop = raw['properties']
            if prop['name'].strip() != ORGANIZATIONS[node_id] or prop['sourceID'] != dataset:
                raise ValueError(f'Organization or dataset changed at {node_id}')
            kind, = raw['categories']
            if kind not in ('Entity', 'Officer', 'Intermediary'):
                raise ValueError(f'Unexpected node category at {node_id}')
            countries = [c.strip() for c in prop.get('countries', '').split(';')
                         if c.strip() and c.strip() != 'Not identified']
            nodes[node_id] = dict(id=node_id, name=ORGANIZATIONS[node_id], kind=kind, countries=countries,
                                  jurisdiction=prop.get('jurisdiction_description') or None,
                                  incorporation_date=iso(prop.get('incorporation_date')), url=BASE + node_id)
        if receipt not in (left, right):
            raise ValueError('The cited record must be an endpoint of its displayed edge')
        other = right if receipt == left else left
        rows = [r for r in page.rows if r['node_id'] == other and r['role'] == role]
        if len(rows) != 1:
            raise ValueError(f'Expected one public {role} connection {left} → {right}, found {len(rows)}')
        row = rows[0]
        edges.append({'from': left, 'to': right, 'role': role, 'start_date': iso(row.get('role-start-date')),
                      'end_date': iso(row.get('role-end-date')), 'url': BASE + receipt})
    return dict(id=trail_id, title=title, summary=summary, note=note, dataset=dataset,
                source_cutoff=cutoff[1], nodes=list(nodes.values()), edges=edges)


def verify_zip(path, trails):
    expected = {(edge['from'], edge['to'], edge['role'].lower() + ' of'):
                (edge['start_date'], edge['end_date']) for trail in trails for edge in trail['edges']}
    found = {}
    with ZipFile(path) as archive, archive.open('relationships.csv') as raw:
        for row in csv.DictReader(TextIOWrapper(raw, encoding='utf-8-sig', newline='')):
            key = (row['node_id_start'], row['node_id_end'], row['link'])
            if key in expected:
                if row['rel_type'] not in ('officer_of', 'intermediary_of') or key in found:
                    raise ValueError(f'Unexpected bulk relationship {key}')
                found[key] = (iso(row['start_date']), iso(row['end_date']))
    if found != expected:
        raise ValueError('ICIJ bulk relationships disagree with the published tables')


def save(path, trails, checked_at, allow_changes=False):
    edition = dict(source='International Consortium of Investigative Journalists, Offshore Leaks Database',
                   source_url='https://offshoreleaks.icij.org/', checked_at=checked_at, trails=trails)
    if path.exists() and not allow_changes:
        previous = json.loads(path.read_text(encoding='utf-8'))
        if previous['trails'] != trails:
            raise ValueError('Public evidence changed. Prior file retained for review.')
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, mode='w', encoding='utf-8', delete=False) as tmp:
        json.dump(edition, tmp, ensure_ascii=False, indent=2)
        tmp.write('\n')
    replacement = Path(tmp.name)
    replacement.chmod(0o644)
    replacement.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', nargs='?', type=Path, help='Optional official bulk CSV archive')
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--accept-changes', action='store_true')
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=3) as pool:
        pages = pool.map(fetch, [plan[4] for plan in TRAILS])
        trails = [project(plan, page) for plan, page in zip(TRAILS, pages)]
    if args.archive:
        verify_zip(args.archive, trails)
    save(args.output, trails, datetime.now(timezone.utc).date().isoformat(), args.accept_changes)
    print(f'Checked {len(trails)} trails and {sum(len(t["edges"]) for t in trails)} original relationships.')


if __name__ == '__main__':
    main()
