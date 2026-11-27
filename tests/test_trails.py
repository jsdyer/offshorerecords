import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from collectors import trails


def sample():
    plan = next(plan for plan in trails.TRAILS if plan[0] == 'fireswirl-shareholding')
    holder, company, _ = plan[5][0]
    props = dict(sourceID='Panama Papers', valid_until='The Panama Papers data is current through 2015')
    nodes = [
        {'id': int(holder), 'data': {'categories': ['Officer'], 'properties':
         dict(props, name=trails.ORGANIZATIONS[holder], countries='Canada', address='Private address')}},
        {'id': int(company), 'data': {'categories': ['Entity'], 'properties':
         dict(props, name=trails.ORGANIZATIONS[company], countries='Hong Kong',
              jurisdiction_description='British Virgin Islands', incorporation_date='23-MAR-2005')}},
        {'id': 999, 'data': {'categories': ['Officer'], 'properties':
         dict(props, name='Private Person', countries='Canada')}},
    ]
    page = trails.PublicNodePage()
    page.feed('<script>document.body.nodeData = '+json.dumps(nodes)+';</script>'
              '<table><tr><td class="description"><a href="/nodes/'+company+'">Company</a></td>'
              '<td class="role">Shareholder</td><td class="role-start-date">23-MAR-2005</td>'
              '<td class="role-end-date">13-DEC-2006</td></tr></table>')
    return plan, page


class VerifiedTrails(unittest.TestCase):
    def test_only_reviewed_organizations_and_roles_leave_the_parser(self):
        plan, page = sample()
        trail = trails.project(plan, page)
        self.assertNotIn('Private', json.dumps(trail))
        self.assertEqual(trail['source_cutoff'], '2015')
        self.assertEqual(trail['nodes'][1]['countries'], ['Hong Kong'])
        self.assertEqual(trail['nodes'][1]['jurisdiction'], 'British Virgin Islands')
        self.assertEqual(trail['edges'][0]['end_date'], '2006-12-13')
        self.assertEqual(trail['nodes'][1]['incorporation_date'], '2005-03-23')
        self.assertIsNone(trails.iso('-'))

    def test_missing_edge_and_changed_identity_are_rejected(self):
        plan, page = sample()
        rows = page.rows
        page.rows = []
        with self.assertRaisesRegex(ValueError, 'Expected one public'):
            trails.project(plan, page)
        page.rows = rows
        page.nodes[plan[4]]['properties']['name'] = 'Another company'
        with self.assertRaisesRegex(ValueError, 'Organization'):
            trails.project(plan, page)

    def test_changed_dates_in_bulk_or_primary_source_do_not_advance_receipt(self):
        plan, page = sample()
        records = [trails.project(plan, page)]
        with TemporaryDirectory() as tmp:
            file = Path(tmp) / 'trails.json'
            trails.save(file, records, '2026-11-26')
            before = file.read_bytes()
            records[0]['edges'][0]['end_date'] = None
            with self.assertRaisesRegex(ValueError, 'Prior file retained'):
                trails.save(file, records, '2026-11-27')
            self.assertEqual(file.read_bytes(), before)
            archive = Path(tmp) / 'archive.zip'
            with ZipFile(archive, 'w') as z:
                z.writestr('relationships.csv', 'node_id_start,node_id_end,link,rel_type,start_date,end_date\n'
                           '12095620,10202700,shareholder of,officer_of,2005-03-23,2006-12-13\n')
            with self.assertRaisesRegex(ValueError, 'disagree'):
                trails.verify_zip(archive, records)

    def test_retained_edition_covers_each_named_source_with_exact_node_receipts(self):
        records = json.loads(trails.OUTPUT.read_text(encoding='utf-8'))
        self.assertEqual(trails.iso(records['checked_at']), records['checked_at'])
        investigations = {item['dataset'].split(' - ')[0] for item in records['trails']}
        self.assertEqual(investigations, {'Offshore Leaks','Panama Papers','Paradise Papers','Pandora Papers','Bahamas Leaks'})
        for item in records['trails']:
            names = {n['id']: n for n in item['nodes']}
            for key, node in names.items():
                self.assertEqual(node['name'], trails.ORGANIZATIONS[key])
                self.assertEqual(node['url'], trails.BASE + key)
            for edge in item['edges']:
                self.assertIn(edge['from'], names)
                self.assertIn(edge['to'], names)
                self.assertIn(edge['url'], {names[side]['url'] for side in (edge['from'], edge['to'])})


if __name__ == '__main__':
    unittest.main()
