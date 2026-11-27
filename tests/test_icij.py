"""Exercise the full CSV reader with representative graph and jurisdiction edge cases."""
from datetime import date
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from collectors import icij


class ArchivedCounts(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.path = self.directory / 'source.zip'
        self.config = json.loads((icij.ROOT / 'config/icij.json').read_text())
        self.config['investigations'] = [dict(id='panama-papers', name='Panama Papers'),
                                         dict(id='pandora-papers', name='Pandora Papers')]
        self.config['minimum_counts'] = dict.fromkeys(icij.KINDS, 0)
        self.rows = {
            'entities': [(7, 'Panama Papers', 'CAN;CAN; USA', 'Malta', 'MLT'),
                         (11, 'Pandora Papers - Atlas', '', 'Undetermined', 'XX'),
                         (12, 'Panama Papers', 'SCP', 'Delaware', 'USA'),
                         (13, 'Panama Papers', 'XXX;CAN', 'United States', 'USA')],
            'officers': [(7, 'Pandora Papers - Atlas', ' CAN ', '', '')],
        }

    def write_archive(self):
        with zipfile.ZipFile(self.path, 'w') as archive:
            archive.writestr('GENERATED_ON_20261126.txt', '')
            for kind in icij.KINDS:
                fp = io.StringIO(newline='')
                writer = csv.writer(fp)
                writer.writerow(['node_id', 'sourceID', 'country_codes', 'jurisdiction_description',
                                 'jurisdiction', 'name', 'address', 'countries'])
                for row in self.rows.get(kind, []):
                    writer.writerow([*row, 'unpublished name sentinel', 'unpublished address sentinel', 'Misaligned text'])
                archive.writestr(f'nodes-{kind}.csv', fp.getvalue())

    def test_direct_codes_types_sources_and_jurisdictions_are_separate(self):
        self.write_archive()
        edition = icij.aggregate(self.path, self.config, date(2026, 11, 27))
        self.assertEqual(edition['source_edition'], '2026-11-26')
        self.assertEqual(edition['checked_at'], '2026-11-27')
        countries = {r['code']: r['investigations'] for r in edition['countries']}
        self.assertEqual(countries['CAN']['panama-papers']['entities'], 2)
        self.assertEqual(countries['USA']['panama-papers']['entities'], 1)
        self.assertEqual(countries['CAN']['pandora-papers']['entities'], 0)
        self.assertEqual(countries['CAN']['pandora-papers']['officers'], 1)
        self.assertNotIn('MLT', countries)
        places = {r['code']: r for r in edition['jurisdictions']}
        self.assertEqual(places['malta']['iso3'], 'MLT')
        self.assertIsNone(places['delaware']['iso3'])
        self.assertEqual(places['delaware']['url'], self.config['source_url'])
        self.assertEqual(edition['unassigned']['incorporation_jurisdiction']['pandora-papers'], 1)
        self.assertEqual(edition['unassigned']['linked_country']['panama-papers']['entities'], 1)
        self.assertEqual(edition['unassigned']['unassigned_tag_occurrences']['SCP'], 1)
        self.assertEqual(sum(p['counts']['entities'] for p in edition['providers']), 4)
        self.assertNotIn('sentinel', json.dumps(edition))

    def test_invalid_capture_preserves_previous_output(self):
        config = self.directory / 'config.json'
        config.write_text(json.dumps(self.config))
        output = self.directory / 'retained.json'
        self.write_archive()
        icij.collect(self.path, config, output, date(2026, 11, 27))
        retained = output.read_bytes()
        self.rows['officers'].append(self.rows['officers'][0])
        self.write_archive()
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            icij.collect(self.path, config, output, date(2026, 11, 27))
        self.assertEqual(retained, output.read_bytes())

    def test_future_edition_and_shrunken_capture_stop_import(self):
        self.write_archive()
        with self.assertRaisesRegex(ValueError, 'newer than'):
            icij.aggregate(self.path, self.config, date(2026, 11, 25))
        self.config['minimum_counts']['entities'] = 6
        with self.assertRaisesRegex(ValueError, 'small'):
            icij.aggregate(self.path, self.config, date(2026, 11, 27))


if __name__ == '__main__':
    unittest.main()
