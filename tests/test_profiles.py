import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from build import KINDS, check_archive, place_table, review_section


class Profiles(unittest.TestCase):
    def test_country_counts_are_typed_and_link_to_exact_source(self):
        counts=dict.fromkeys(KINDS,0)
        inv={"id":"example-leak","name":"Example & sample","url":"https://example.org/archive","counts":counts.copy()}
        p={"code":"CAN","name":"Canada","investigations":{"example-leak":counts}}
        alternate={"code":"XK","name":"Kosovo","investigations":{"example-leak":counts}}
        archive={"checked_at":"2026-11-27","investigations":[inv],"countries":[p,alternate]}
        check_archive(archive)
        page=place_table(alternate,[inv])
        self.assertIn("example-leak?c=XK",page)
        self.assertIn("Example &amp; sample",page)
        del counts["officers"]
        with self.assertRaises(ValueError):
            check_archive(archive)

    def test_review_dates_remain_attached_to_original_rounds(self):
        old={"round":1,"review_year":2012,"status":"Full peer review","rating":"Older test rating","url":"https://example.org/first"}
        new={"round":2,"review_year":2021,"published_on":"2021-05-01","rating":"Later test rating","url":"https://example.org/second"}
        s=review_section([{"reviews":[old,new]}])
        self.assertLess(s.index("Later test rating"),s.index("Older test rating"))
        self.assertIn("Round 2",s)
        self.assertIn("2021-05-01",s)
