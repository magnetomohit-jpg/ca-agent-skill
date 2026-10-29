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
from common import gstin_checksum, gstin_problem, inr, parse_period, round_288b  # noqa: E402
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
        self.assertEqual(fs["profit_and_loss"]["pat"], 714316.34)              # tax provision 2,60,120 (s.288B)
        self.assertEqual(fs["cash_flow"]["difference"], 0)
        self.assertEqual(fs["cash_flow"]["net_change"], 442100.0)
        # March RCM (54,450 x 2) and TDS (7,500) are still payable at 31 March; nothing else is flagged.
        self.assertEqual(len(fs["checks"]), 2)
        self.assertIn("Reverse-charge GST payable at year end 1,08,900.00", fs["checks"][0])
        self.assertIn("TDS payable at year end 7,500.00", fs["checks"][1])
        self.assertTrue(fs["small_company"])
        self.assertEqual([(m["ref"], m["amount"], m["age_days"]) for m in fs["msme_dues"]], [("RC/240", 354000.0, 21)])
        net_block = [r for r in fs["ppe_reconciliation"] if r[1] == "Net block"]
        self.assertEqual(net_block[0][-1], fs["balance_sheet"]["ppe"])
        tax = {r[0]: r[1] for r in fs["tax"] if r[0]}
        self.assertEqual(tax["Net tax payable / (refundable)"], 10120.0)
        self.assertEqual(tax["Deferred tax liability / (asset), closing"], -8295.39)
        self.assertNotIn("Difference: current tax booked less computed liability", tax)

    def test_depreciation(self):
        dep = self.result["depreciation"]
        self.assertEqual(dep["tax_depreciation"], 63470.0)          # 21,870 furniture + 21,600 + 20,000 (half rate)
        self.assertAlmostEqual(dep["book_depreciation"], 123730.05, places=2)

    def test_company_tax(self):
        tax = self.result["tax"]
        self.assertEqual(tax["total_income"], 1033530.0)
        self.assertEqual(tax["liability"], 260120.0)                 # 25.168% under s.115BAA, rounded u/s 288B
        self.assertEqual(tax["interest_234c"], 1930.0)
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
        self.assertEqual(r["summary"]["Matched"]["eligible_itc"], 96000.0)   # AC/77 catering blocked u/s 17(5)
        self.assertEqual(r["bridge"][0]["amount"], 97900.0)
        self.assertEqual(r["bridge"][-1]["amount"], r["net_itc_4c"])
        self.assertEqual(r["net_itc_4c"], 105900.0)                  # 90,000 + 6,000 + 9,900 RCM
        self.assertEqual(r["rcm_itc"], 9900.0)
        self.assertNotIn("warnings", r)

    def test_company_draft(self):
        out = Path(self.tmp.name) / "draft.json"
        run("income_tax.py", "company-draft", self.books, "--out", out)
        d = json.loads(out.read_text(encoding="utf-8"))
        self.assertFalse(d["tax_audit"])
        self.assertEqual([(m["ref"], m["pay_by_45_days"]) for m in d["msme_dues_at_year_end"]], [("RC/240", "2026-04-24")])
        self.assertTrue(any("even when that date falls after 31 March" in t for t in d["todo"]))
        md = (self.books / "working" / "tax_computation.md").read_text(encoding="utf-8")
        self.assertNotIn("3CA-3CD acknowledgement", md)

    def test_compliance_overdue(self):
        c = run_json("compliance.py", self.books, "--from", "2026-10-17", "--days", "30")
        overdue = {e["item"] for e in c["overdue_unless_done"]}
        self.assertIn("Hold AGM (within 6 months of year end)", overdue)
        self.assertTrue(all(e["date"] >= "2026-10-17" for e in c["events"]))

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
        self.assertTrue((nxt / "parties.csv").exists())  # party master carries forward

    def test_party_sheets(self):
        p = run_json("parties.py", "report", self.books)
        self.assertEqual([(d["party"], d["balance"]) for d in p["debtors"]], [("Patil Retail LLP", 598400.0)])
        patil = p["debtors"][0]
        self.assertEqual(patil["max_days_past_due"], 49)      # bill 12-12-2025 + 60 credit days -> due 10-02-2026
        self.assertEqual(patil["ageing"]["Less than 6 months"], 598400.0)
        rathod = p["creditors"][0]
        self.assertTrue(rathod["msme"])
        self.assertEqual(rathod["ageing"]["Not due"], 354000.0)  # 21 days old, 45 credit days
        self.assertEqual(p["checks"], [])
        self.assertEqual(p["schedule_iii_payables"][0][0], "MSME")

    def test_confirmation_letters(self):
        out = Path(self.tmp.name) / "letters"
        run("parties.py", "confirm", self.books, "--out-dir", out)
        letters = sorted(f.name for f in out.glob("*.md"))
        self.assertEqual(letters, ["Patil_Retail_LLP.md", "Rathod_Components_Pvt_Ltd.md"])
        self.assertIn("5,98,400.00", (out / "Patil_Retail_LLP.md").read_text(encoding="utf-8"))

    def test_party_advances_reclassified(self):
        import shutil
        books = Path(self.tmp.name) / "adv"
        shutil.copytree(self.books, books)
        run("books.py", "add-account", books, "--account", "Deccan Retail Pvt Ltd", "--line", "trade_receivables",
            "--tag", "debtor")
        vouchers = Path(self.tmp.name) / "adv.json"
        vouchers.write_text(json.dumps([
            {"date": "2026-02-10", "type": "Payment", "ref": "ADV-MP-1", "narration": "Advance to Mehta Packaging",
             "lines": [{"account": "Mehta Packaging", "dr": 40000}, {"account": "HDFC Bank Current A/c", "cr": 40000}]},
            {"date": "2026-03-20", "type": "Receipt", "ref": "ADV-DR-1", "narration": "Advance from Deccan Retail",
             "lines": [{"account": "HDFC Bank Current A/c", "dr": 75000}, {"account": "Deccan Retail Pvt Ltd", "cr": 75000}]},
        ]), encoding="utf-8")
        run("books.py", "post", books, "--file", vouchers)
        fs = run_json("financials.py", books)
        self.assertEqual(fs["total_assets"], fs["total_equity_liabilities"])
        self.assertIn(["Advance to supplier - Mehta Packaging", 40000.0], fs["notes"]["st_loans_advances"])
        self.assertIn(["Advance from customer - Deccan Retail Pvt Ltd", 75000.0], fs["notes"]["other_current_liabilities"])
        self.assertFalse(any("unusual" in c for c in fs["checks"]))
        p = run_json("parties.py", "report", books)
        self.assertEqual([(a["party"], a["balance"]) for a in p["advances_to_suppliers"]], [("Mehta Packaging", 40000.0)])
        self.assertEqual([(a["party"], a["balance"]) for a in p["advances_from_customers"]],
                         [("Deccan Retail Pvt Ltd", 75000.0)])
        self.assertTrue(any("Deccan Retail" in c and "parties.csv" in c for c in p["checks"]))


class Individuals(unittest.TestCase):
    PERSON = {"name": "Test", "fy": "2025-26", "age": 32, "tds": 300000,
              "salary": {"gross": 2400000, "professional_tax": 2500,
                         "hra": {"received": 360000, "rent_paid": 300000, "basic_da": 960000, "city": "Pune"}},
              "deductions_old": {"80C": 150000, "80D": 25000}}

    def write(self, data) -> Path:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(data, tmp)
        tmp.close()
        self.addCleanup(Path(tmp.name).unlink)
        return Path(tmp.name)

    def test_hra_rule_2a(self):
        self.assertEqual(individual_tax(self.PERSON, "old")["hra_exempt"], D(204000))   # 3,00,000 less 10% of 9,60,000
        self.assertEqual(individual_tax(self.PERSON, "new")["hra_exempt"], 0)

    def test_on_time_return(self):
        r = run_json("income_tax.py", "individual", self.write(dict(self.PERSON, filing_date="2026-07-31")))
        self.assertFalse(r["belated"])
        self.assertEqual(r["late"]["new"]["fee_234f"], 0)
        self.assertEqual(r["old"]["total_tax"], 419170.0)
        self.assertEqual(r["recommended"], "new")

    def test_belated_return_locked_into_new_regime(self):
        # High deductions make the old regime cheaper, but a belated return cannot opt out of the new one.
        p = {"fy": "2025-26", "salary": {"gross": 1500000}, "filing_date": "2026-10-17",
             "deductions_old": {"80C": 150000, "80D": 50000, "80CCD1B": 50000, "OTHER": 400000}}
        r = run_json("income_tax.py", "individual", self.write(p))
        self.assertTrue(r["belated"])
        self.assertFalse(r["old_regime_available"])
        self.assertLess(r["old"]["total_tax"], r["new"]["total_tax"])
        self.assertEqual(r["recommended"], "new")
        late = r["late"]["new"]
        self.assertEqual(late["fee_234f"], 5000.0)
        # 234A: unpaid tax rounded down to Rs 100, 1% a month for Aug-Oct 2026, then rounded u/s 288B
        self.assertEqual(late["interest_234a"], float(round_288b(D(r["new"]["total_tax"]) // 100 * 100 * D("0.03"))))
        self.assertEqual(late["payable"] % 10, 0)

    def test_itr_form_due_date(self):
        f = self.write({"fy": "2025-26", "total_income": 1500000})
        r = run_json("income_tax.py", "itr-form", f, "--as-of", "2026-10-17")
        self.assertEqual((r["form"], r["status"], r["due_date"]), ("ITR-1", "belated", "2026-07-31"))
        self.assertEqual(run_json("income_tax.py", "itr-form", f, "--as-of", "2027-01-05")["status"], "window_closed")
        with tempfile.TemporaryDirectory() as out:
            run("income_tax.py", "itr-form", f, "--as-of", "2026-07-01", "--out-dir", out)
            self.assertEqual(json.loads((Path(out) / "itr_form.json").read_text(encoding="utf-8"))["status"], "on_time")


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

    def test_round_288b(self):
        self.assertEqual(round_288b(D("260119.40")), 260120)
        self.assertEqual(round_288b(D("1934.99")), 1930)
        self.assertEqual(round_288b(D("1935")), 1940)
        self.assertEqual(round_288b(D("-2504")), -2500)

    def test_helpers(self):
        self.assertEqual(inr(D("12345678.5")), "1,23,45,678.50")
        self.assertIsNone(gstin_problem("27AAKCS1234F1Z" + gstin_checksum("27AAKCS1234F1Z")))
        self.assertIsNotNone(gstin_problem("27AAKCS1234F1ZA"))
        start, end, _ = parse_period("2025-26:Q4")
        self.assertEqual((start.month, end.month, end.year), (1, 3, 2026))


if __name__ == "__main__":
    unittest.main()
