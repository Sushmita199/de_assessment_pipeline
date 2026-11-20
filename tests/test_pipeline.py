import os
import sqlite3
import sys
import tempfile
import unittest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_DIR, "src"))

from parse_po import parse_po
from validate import validate_po
from write_excel import write_excel
from load_sqlite import load_excel_to_sqlite

SAMPLE_1 = os.path.join(PROJECT_DIR, "input", "purchase_order_sample.txt")
SAMPLE_2 = os.path.join(PROJECT_DIR, "input", "purchase_order_sample_2.txt")
TEMPLATE = os.path.join(PROJECT_DIR, "input", "output_template_blank.xlsx")


def flags_by_sku(po):
    return {item["sku"]: [f["flag"] for f in item["flags"]]
            for item in po["items"] if item["flags"]}


class TestSample1(unittest.TestCase):
    def setUp(self):
        self.po = validate_po(parse_po(SAMPLE_1))

    def test_header(self):
        h = self.po["header"]
        self.assertEqual(self.po["layout"], "table")
        self.assertEqual(h["po_number"], "TX9K2QP")
        self.assertEqual(h["ref_master_po"], "TX9H1LM")
        self.assertEqual(h["buyer"], "610 JORDAN MILLER")
        self.assertEqual(h["ship_date"], "2026-05-02")
        self.assertTrue(h["ship_to"].startswith("331 DISTRIBUTION/NORTHEAST"))
        self.assertTrue(h["bill_to"].startswith("331 MERIDIAN SOURCING"))

    def test_items_and_upc_from_next_line(self):
        self.assertEqual(len(self.po["items"]), 12)
        first = self.po["items"][0]
        self.assertEqual(first["sku"], "71097188")
        self.assertEqual(first["upc"], "0091120032129")
        self.assertEqual(first["vendor_part_no"], "04212")

    def test_exactly_the_three_planted_problems_are_flagged(self):
        self.assertEqual(flags_by_sku(self.po), {
            "71097218": ["MISSING_UPC"],
            "71293252": ["EXT_COST_MISMATCH"],
            "71293276": ["COST_REPAIRED"],
        })

    def test_bad_cost_repaired(self):
        item = next(i for i in self.po["items"] if i["sku"] == "71293276")
        self.assertEqual(item["cost"], 55.44)


class TestSample2(unittest.TestCase):
    def setUp(self):
        self.po = validate_po(parse_po(SAMPLE_2))

    def test_header_with_different_labels(self):
        h = self.po["header"]
        self.assertEqual(self.po["layout"], "labeled")
        self.assertEqual(h["po_number"], "PL7M3RK")
        self.assertEqual(h["ref_master_po"], "PL7K9SX")
        self.assertEqual(h["ship_date"], "2026-06-11")

    def test_swapped_bill_to_ship_to(self):
        self.assertTrue(self.po["header"]["ship_to"].startswith("418 DISTRIBUTION/MIDWEST"))
        self.assertTrue(self.po["header"]["bill_to"].startswith("418 MERIDIAN SOURCING"))

    def test_items_clean(self):
        self.assertEqual(len(self.po["items"]), 6)
        self.assertEqual(self.po["items"][0]["upc"], "0071230441087")
        self.assertEqual(flags_by_sku(self.po), {})


class TestUnknownLayout(unittest.TestCase):
    def test_unknown_layout_fails_whole_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "vendor3.txt")
            with open(path, "w") as f:
                f.write("INVOICE 123\nsomething else entirely\n")
            with self.assertRaises(ValueError):
                parse_po(path)


class TestLoadIsIdempotent(unittest.TestCase):
    def test_loading_twice_does_not_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            for sample in (SAMPLE_1, SAMPLE_2):
                xlsx = os.path.join(tmp, os.path.basename(sample) + ".xlsx")
                write_excel(validate_po(parse_po(sample)), TEMPLATE, xlsx)
                first = load_excel_to_sqlite(xlsx, db)
                second = load_excel_to_sqlite(xlsx, db)
                self.assertEqual(second["inserted"], 0)
                self.assertEqual(first["table_rows_total"], second["table_rows_total"])

            conn = sqlite3.connect(db)
            count = conn.execute("SELECT COUNT(*) FROM po_line_items").fetchone()[0]
            conn.close()
            self.assertEqual(count, 18)


if __name__ == "__main__":
    unittest.main()
