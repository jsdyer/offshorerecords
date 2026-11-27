import csv
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from collectors.oecd import chart_data, main, parse_rows, publications, ROOT


EDITION = "https://datawrapper.dwcdn.net/ASdf2/7/"
CODES = {"CA": "CAN", "MT": "MLT", "CG": "COG", "JM": "JAM", "AL": "ALB", "DZ": "DZA"}
HEADER = ["Jurisdiction", "Year of publication", "<b>Overall<br>rating</b>",
          "A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "C4", "C5"]


def csv_data(*rows):
    text = io.StringIO()
    writer = csv.writer(text)
    writer.writerow(HEADER)
    writer.writerows([*row, *[""] * 10] for row in rows)
    return text.getvalue().encode()


def work(name, year, suffix, doi, date=None):
    return {"DOI": doi, "title": [f"Global Forum on Transparency and Exchange of Information for Tax Purposes: {name} {year} {suffix}"],
            "published": {"date-parts": [date or [year, 3, 12]]}}


def registry(*items):
    return publications(lambda _: json.dumps({"message": {"total-results": len(items), "items": items}}).encode())


class OECDReviews(unittest.TestCase):
    def test_latest_source_assessment_and_exact_report_kind(self):
        data = csv_data((":mt: Malta", "2013", "Largely Compliant"),
                        (":mt: Malta (Round 2)", "2020", "Partially Compliant"),
                        (":mt: Malta (Round 2 suppl.) ", "2024", "Largely Compliant"))
        reports = registry(work("Malta", 2024, "(Second Round)", "10.1787/sample-en"),
                           work("Malta", 2024, "(Second Round, Supplementary Report)", "10.1787/correct-en", [2024,3,28]))
        malta, = parse_rows(data, EDITION, reports, CODES)
        self.assertEqual((malta["iso3"], malta["round"], malta["review_year"]), ("MLT", 2, 2024))
        self.assertEqual((malta["url"], malta["published_on"]), ("https://doi.org/10.1787/correct-en", "2024-03-28"))
        self.assertEqual([r["rating"] for r in malta["reviews"]], ["Largely Compliant", "Partially Compliant", "Largely Compliant"])
        self.assertEqual(malta["status"], "Supplementary peer review")

    def test_legal_framework_provisional_and_unreviewed_stages(self):
        data = csv_data((":cg: Congo (Republic of the)", "2026", "Phase 1 only**"),
                        (":al: Albania (fast-track)", "2017", "Provisionally Largely Compliant"),
                        (":jm: Jamaica", "n/a", "Not yet reviewed"),
                        (":dz: Algeria", "2026", "Largely Compliant"))
        reports = registry(work("Congo", 2026, "(Second Round, Phase 1)", "10.1787/congo-en"))
        rows = {r["iso3"]: r for r in parse_rows(data, EDITION, reports, CODES)}
        self.assertEqual(rows["COG"]["jurisdiction"], "Congo (Republic of the)")
        self.assertIsNone(rows["COG"]["rating"])
        self.assertEqual(rows["COG"]["round"], 2)
        self.assertIn("Limited exchange experience", rows["COG"]["status"])
        self.assertIsNone(rows["JAM"]["review_year"])
        self.assertIsNone(rows["JAM"]["rating"])
        self.assertEqual(rows["ALB"]["rating"], "Provisionally Largely Compliant")
        self.assertIsNone(rows["DZA"]["round"])  # No round marker and no matched publication.
        self.assertEqual(rows["DZA"]["url"], EDITION)

    def test_no_unverified_alias_or_ambiguous_report(self):
        reports = registry(work("Canada", 2017, "(Second Round)", "10.1787/a-en"),
                           work("Canada", 2017, "(Second Round)", "10.1787/b-en"))
        row, = parse_rows(csv_data((":ca: Canada (Round 2)", "2017", "Largely Compliant")), EDITION, reports, CODES)
        self.assertEqual(row["url"], EDITION)
        self.assertIsNone(row["published_on"])

    def test_find_only_publisher_advertised_version_and_displayed_update_date(self):
        home = b'<iframe title="Exchange of information on request (EOIR)" src="https://datawrapper.dwcdn.net/ASdf2/"></iframe>'
        redir = f'<meta http-equiv="refresh" content="0; url={EDITION}">'.encode()
        chart = b'<h1>Exchange of information on request</h1><p>Last update: 3 November 2026</p>'
        blobs = [home, redir, chart, b'table']
        self.assertEqual(chart_data(lambda _: blobs.pop(0)), (EDITION,"2026-11-03",b'table',EDITION+"data.csv"))
        blobs = [home, b'<meta http-equiv="refresh" content="0; url=https://other.example/ASdf2/7/">']
        with self.assertRaises(ValueError):
            chart_data(lambda _: blobs.pop(0))
        for bad in (b"<h1>Other measure</h1><p>Last update: 3 November 2026</p>", b"<h1>Exchange of information on request</h1>"):
            blobs = [home, redir, bad]
            with self.assertRaises(ValueError):
                chart_data(lambda _: blobs.pop(0))

    def test_schema_or_outcome_drift_is_rejected(self):
        for bad in (csv_data((":ca: Canada", "2012", "Test label")),
                    csv_data((":ca: Canada (Unrecognized report type)", "2015", "Compliant")),
                    csv_data((":xy: Unknown", "2015", "Compliant")),
                    b"Jurisdiction,Year of publication\nCanada,2017\n"):
            with self.assertRaises(ValueError):
                parse_rows(bad, EDITION, {}, CODES)

    def test_failed_refresh_and_lost_coverage_preserve_the_previous_capture(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "edition.json"
            original = {"source": {"updated_at": "2026-10-01"}, "jurisdictions": [{"iso3": "CAN"}]}
            data = json.dumps(original).encode()
            path.write_bytes(data)
            replacements = [
                {"source": {"updated_at": "2026-09-01"}, "jurisdictions": [{"iso3": "CAN"}]},
                {"source": {"updated_at": "2026-11-03"}, "jurisdictions": []},
            ]
            for next_edition in replacements:
                with patch("sys.argv", ["oecd.py", "--output", str(path)]), patch("collectors.oecd.build", return_value=next_edition):
                    with self.assertRaises(ValueError):
                        main()
                self.assertEqual(path.read_bytes(), data)
            with patch("sys.argv", ["oecd.py", "--output", str(path)]), patch("collectors.oecd.fetch", side_effect=OSError("offline")):
                with self.assertRaises(OSError):
                    main()
            self.assertEqual(path.read_bytes(), data)

    def test_committed_edition_has_traceable_malta_and_consistent_counts(self):
        data = json.loads((ROOT / "data/oecd.json").read_text())
        rows = data["jurisdictions"]
        self.assertEqual(len({r["iso3"] for r in rows}), data["source"]["jurisdiction_count"])
        self.assertEqual(sum(len(r["reviews"]) for r in rows), data["source"]["assessment_rows"])
        malta = next(r for r in rows if r["iso3"] == "MLT")
        report = next(r for r in malta["reviews"] if r["review_year"] == 2024)
        self.assertEqual((report["rating"], report["published_on"]), ("Largely Compliant", "2024-03-28"))
        self.assertTrue(report["url"].startswith("https://doi.org/10.1787/"))
