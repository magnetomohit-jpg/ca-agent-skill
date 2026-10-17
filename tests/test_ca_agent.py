"""Regression tests for the CA Agent scripts.

Builds the demo company end to end in a temp folder, then checks the numbers a CA would check by
hand: books tally, balance sheet tallies, cash flow reconciles, GST returns, reconciliations, tax.

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "ca-agent" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "examples"))

import build_demo  # noqa: E402
from common import gstin_checksum, gstin_problem, inr, parse_period  # noqa: E402
from gst import set_off  # noqa: E402
from income_tax import company_tax, individual_tax, interest_234b, interest_234c, mat_tax  # noqa: E402


def run(*args) -> str:
    res = subprocess.run([sys.executable, str(SCRIPTS / args[0]), *[str(a) for a in args[1:]]],
                         capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0:
        raise AssertionError(f"{args} failed:\n{res.stdout}\n{res.stderr}")
    return res.stdout


def run_json(*args) -> dict:
    return json.loads(run(*args, "--json"))


D = lambda x: Decimal(str(x))  # noqa: E731


class DemoCompany(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.books = Path(cls.tmp.name) / "demo"
        cls.result = build_demo.build(cls.books)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_books_validate(self):
        self.assertIn("OK - books are internally consistent", run("books.py", "validate", self.books))

    def test_financial_statements(self):
        fs = run_json("financials.py", self.books)
        self.assertEqual(fs["total_assets"], fs["total_equity_liabilities"])
        self.assertEqual(fs["total_assets"], 3337965.34)
        self.assertEqual(fs["profit_and_loss"]["pbt"], 959269.95)
        self.assertEqual(fs["profit_and_loss"]["pat"], 714317.34)
        self.assertEqual(fs["cash_flow"]["difference"], 0)
        self.assertEqual(fs["cash_flow"]["net_change"], 442100.0)
        self.assertEqual(fs["checks"], [])

    def test_depreciation(self):
        dep = self.result["depreciation"]
        self.assertEqual(dep["tax_depreciation"], 63470.0)          # 21,870 furniture + 21,600 + 20,000 (half rate)
        self.assertAlmostEqual(dep["book_depreciation"], 123730.05, places=2)

    def test_company_tax(self):
        tax = self.result["tax"]
        self.assertEqual(tax["total_income"], 1033530.0)
        self.assertEqual(tax["liability"], 260119.0)                 # 25.168% under s.115BAA
        self.assertEqual(tax["interest_234c"], 1931.0)
        self.assertEqual(tax["interest_234b"], 0)
        self.assertEqual(tax["balance_payable"], 12050.0)

    def test_gstr3b_april(self):
        g = run_json("gst.py", "gstr3b", self.books, "--period", "2025-04")
        self.assertEqual(g["3.1"]["a"]["taxable"], 640000.0)
        self.assertEqual(g["3.1"]["d"]["cgst"], 4950.0)
        self.assertEqual(g["4"]["B1"]["cgst"], 500.0)               # blocked u/s 17(5)
        self.assertEqual(g["total_cash"], 19200.0)                   # 9,300 forward charge + 9,900 RCM
        self.assertEqual(g["books_crosscheck"], [])

    def test_gstr3b_late_filing(self):
        g = run_json("gst.py", "gstr3b", self.books, "--period", "2025-04", "--filing-date", "2025-06-04")
        self.assertEqual(g["late_fee"]["cgst"] + g["late_fee"]["sgst"], 750.0)   # 15 days x Rs 50
        self.assertEqual(sum(g["interest"].values()), 143.0)

    def test_gstr1_april(self):
        g = run_json("gst.py", "gstr1", self.books, "--period", "2025-04")
        b2b = g["4A/4B/6B/6C - B2B, SEZ, deemed exports"]
        self.assertEqual({r["Invoice"] for r in b2b}, {"INV/25-26/001", "INV/25-26/002"})
        self.assertEqual(len(g["5 - B2C large (inter-state invoices above Rs 1,00,000)"]), 1)
        self.assertEqual(len(g["9B - Credit/debit notes (registered)"]), 1)
        self.assertEqual(g["7 - B2C others"][0][2], 40000.0)

    def test_gstr2b_reco(self):
        r = run_json("gst.py", "reco", self.books, "--period", "2025-04", "--gstr2b",
                     ROOT / "examples" / "inputs" / "gstr2b_apr2025.csv")
        self.assertEqual(r["summary"]["Matched"]["count"], 3)        # RC-101 vs RC/101 normalised
        self.assertEqual(r["summary"]["In GSTR-2B, not in books"]["count"], 1)

    def test_bank_reco(self):
        b = run_json("bank_reco.py", self.books, "--account", "HDFC Bank Current A/c", "--statement",
                     ROOT / "examples" / "inputs" / "hdfc_statement_apr2025.csv", "--as-of", "2025-04-30")
        self.assertEqual(b["computed_bank_balance"], b["statement_balance"])
        self.assertEqual(len(b["unpresented"]), 1)
        self.assertEqual(len(b["bank_only"]), 1)

    def test_close_year(self):
        nxt = Path(self.tmp.name) / "next"
        run("books.py", "close-year", self.books, nxt)
        out = run("books.py", "tb", nxt)
        self.assertIn("Tallied.", out)
        self.assertTrue((nxt / "fixed_assets.csv").read_text().count("FA-00") == 3)


class Rules(unittest.TestCase):
    def test_new_regime_rebate_and_marginal_relief(self):
        self.assertEqual(individual_tax({"fy": "2025-26", "salary": {"gross": 1275000}}, "new")["total_tax"], 0)
        self.assertEqual(individual_tax({"fy": "2025-26", "salary": {"gross": 1285000}}, "new")["total_tax"], 10400)

    def test_old_regime(self):
        p = {"fy": "2025-26", "salary": {"gross": 1000000}, "deductions_old": {"80C": 150000}}
        self.assertEqual(individual_tax(p, "old")["total_tax"], 75400)

    def test_company_rates(self):
        self.assertEqual(company_tax(D(10000000), {}, "115BAA", D(0))["total"], 2516800)
        self.assertEqual(company_tax(D(20000000), {}, "normal", D(100000000))["total"], 5564000)
        # marginal relief just above Rs 1 crore: tax + surcharge limited to tax at 1 cr + excess income
        self.assertEqual(company_tax(D(10100000), {}, "normal", D(100000000))["total"], 2704000)

    def test_mat_rate_by_year(self):
        self.assertEqual(mat_tax(D(1000000), "2025-26")["base"], D(150000))
        self.assertEqual(mat_tax(D(1000000), "2026-27")["base"], D(140000))

    def test_interest(self):
        from datetime import date
        total, _ = interest_234c(D(100000), [(date(2025, 6, 15), D(15000)), (date(2025, 9, 15), D(30000)),
                                             (date(2025, 12, 15), D(30000)), (date(2026, 3, 15), D(25000))], "2025-26")
        self.assertEqual(total, 0)
        self.assertEqual(interest_234b(D(100000), D(0), [], "2025-26", date(2026, 7, 31)), D(4000))

    def test_set_off_minimises_cash(self):
        z = D(0)
        r = set_off({"igst": z, "cgst": D(100), "sgst": D(100), "cess": z},
                    {"igst": D(100), "cgst": D(50), "sgst": D(50), "cess": z})
        self.assertEqual(sum(r["cash"].values()), 0)

    def test_helpers(self):
        self.assertEqual(inr(D("12345678.5")), "1,23,45,678.50")
        self.assertIsNone(gstin_problem("27AAKCS1234F1Z" + gstin_checksum("27AAKCS1234F1Z")))
        self.assertIsNotNone(gstin_problem("27AAKCS1234F1ZA"))
        start, end, _ = parse_period("2025-26:Q4")
        self.assertEqual((start.month, end.month, end.year), (1, 3, 2026))


if __name__ == "__main__":
    unittest.main()
