#!/usr/bin/env python3
"""Build the demo books for Sahyadri Trading Private Limited (fictional), FY 2025-26, end to end.

Runs the same steps an agent following the skill would: create the books, add parties, post the
year's vouchers, book depreciation and deferred tax, compute income tax and post the provision,
then write the final reports. Usage:

    python examples/build_demo.py [output-folder]      (default: examples/demo-company)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "skills" / "ca-agent" / "scripts"
SOURCE = HERE / "source"

PARTIES = [
    ("Patil Retail LLP", "trade_receivables", "debtor"),
    ("Kaveri Systems Pvt Ltd", "trade_receivables", "debtor"),
    ("Gulf Gadgets LLC", "trade_receivables", "debtor"),
    ("Rathod Components Pvt Ltd", "trade_payables_msme", "creditor;msme"),
    ("Mehta Packaging", "trade_payables_others", "creditor"),
    ("Infotech Solutions Pvt Ltd", "trade_payables_others", "creditor"),
    ("Annapurna Caterers", "trade_payables_others", "creditor"),
    ("HDFC Bank Current A/c", "cash_equivalents", "bank"),
]


def run(*args, cwd: Path | None = None) -> str:
    """Run a skill script. Paths are passed relative to `cwd` so reports carry no machine-specific paths."""
    def arg(a):
        if isinstance(a, Path) and cwd is not None:
            try:
                return os.path.relpath(a, cwd)
            except ValueError:  # different drive on Windows
                return str(a)
        return str(a)
    cmd = [sys.executable, str(SCRIPTS / args[0]), *[arg(a) for a in args[1:]]]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=cwd)
    if res.returncode != 0:
        raise SystemExit(f"FAILED: {' '.join(cmd)}\n{res.stdout}\n{res.stderr}")
    return res.stdout


def build(dest: Path) -> dict:
    dest = dest.resolve()
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    run("books.py", "init", dest, "--name", "Sahyadri Trading Private Limited", "--fy", "2025-26",
        "--gstin", "27AAKCS1234F1ZI", "--cin", "U51909MH2019PTC123456", "--tax-regime", "115BAA", "--gst-filing", "monthly", cwd=dest.parent)
    company = json.loads((dest / "company.json").read_text(encoding="utf-8"))
    company.update({"turnover_fy_minus_2": 2800000, "aato_previous_fy": 3200000, "equity_shares_outstanding": 100000,
                    "face_value": 10, "depreciation_method": "WDV", "tds_applicable": True, "tax_audit": False,
                    "notes": "Fictional demo company for the CA Agent skill"})
    (dest / "company.json").write_text(json.dumps(company, indent=2) + "\n", encoding="utf-8")
    for name, line, tag in PARTIES:
        run("books.py", "add-account", dest, "--account", name, "--line", line, "--tag", tag, cwd=dest)
    for f in ("sales_register.csv", "purchase_register.csv", "fixed_assets.csv", "it_blocks.csv"):
        shutil.copy(SOURCE / f, dest / f)
    run("books.py", "post", dest, "--file", SOURCE / "vouchers.json", cwd=dest)

    work = dest / "working"
    work.mkdir()
    # Year-end 1: depreciation (Schedule II) and the tax WDV chart.
    run("depreciation.py", dest, "--voucher", work / "depreciation_voucher.json", "--write-next", "--out-dir", work, cwd=dest)
    run("books.py", "post", dest, "--file", work / "depreciation_voucher.json", cwd=dest)
    dep = json.loads((work / "depreciation.json").read_text(encoding="utf-8"))

    # Year-end 2: deferred tax = closing DT on timing difference less opening balance (DTL 6,871).
    closing_dt = Decimal(str(dep["deferred_tax_closing"]))   # positive = liability
    movement = closing_dt - Decimal("6871")
    dt_lines = ([{"account": "Deferred Tax", "dr": float(movement)}, {"account": "Deferred Tax Liability (Net)", "cr": float(movement)}]
                if movement > 0 else
                [{"account": "Deferred Tax Liability (Net)", "dr": float(-movement)}, {"account": "Deferred Tax", "cr": float(-movement)}])
    (work / "deferred_tax_voucher.json").write_text(json.dumps([{
        "date": "2026-03-31", "type": "Journal", "ref": "DT-FY2526",
        "narration": "Deferred tax on depreciation timing difference (AS 22)", "lines": dt_lines}], indent=2), encoding="utf-8")
    run("books.py", "post", dest, "--file", work / "deferred_tax_voucher.json", cwd=dest)

    # Year-end 3: income-tax computation. The draft is reviewed (here: the s.40A(3) cash payment is disallowed).
    run("income_tax.py", "company-draft", dest, "--depreciation-json", work / "depreciation.json", "--out", work / "tax_input.json", cwd=dest)
    tax_input = json.loads((work / "tax_input.json").read_text(encoding="utf-8"))
    tax_input["add_backs"].append({"item": "Cash payment above Rs 10,000 (office repairs, voucher PMT/2025-26/0001)",
                                   "amount": 12000, "ref": "s.40A(3)"})
    tax_input["filing_date"] = "2026-10-31"
    (work / "tax_input.json").write_text(json.dumps(tax_input, indent=2), encoding="utf-8")
    run("income_tax.py", "company", work / "tax_input.json", "--out-dir", work, cwd=dest)
    comp = json.loads((work / "tax_computation.json").read_text(encoding="utf-8"))
    liability = Decimal(str(comp["liability"]))
    (work / "tax_provision_voucher.json").write_text(json.dumps([{
        "date": "2026-03-31", "type": "Journal", "ref": "TAX-PROV-FY2526",
        "narration": "Provision for income tax FY 2025-26 (s.115BAA)",
        "lines": [{"account": "Current Tax", "dr": float(liability)}, {"account": "Provision for Income Tax", "cr": float(liability)}]}],
        indent=2), encoding="utf-8")
    run("books.py", "post", dest, "--file", work / "tax_provision_voucher.json", cwd=dest)

    # Final reports.
    reports = dest / "reports"
    run("financials.py", dest, "--out-dir", reports, cwd=dest)
    run("gst.py", "gstr1", dest, "--period", "2025-04", "--out-dir", reports, cwd=dest)
    run("gst.py", "gstr3b", dest, "--period", "2025-04", "--out-dir", reports, cwd=dest)
    run("gst.py", "reco", dest, "--period", "2025-04", "--gstr2b", HERE / "inputs" / "gstr2b_apr2025.csv", "--out-dir", reports, cwd=dest)
    run("bank_reco.py", dest, "--account", "HDFC Bank Current A/c", "--statement", HERE / "inputs" / "hdfc_statement_apr2025.csv",
        "--as-of", "2025-04-30", "--suggest", work / "bank_entries_apr2025.json", "--out-dir", reports, cwd=dest)
    run("compliance.py", dest, "--fy", "2025-26", "--ics", reports / "compliance_fy2025-26.ics", "--out-dir", reports, cwd=dest)
    return {"tax": comp, "depreciation": dep}


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "demo-company"
    out = build(target)
    print(f"Demo books built in {target}")
    print(f"Tax liability FY 2025-26: Rs {out['tax']['liability']:,.0f}; reports in {target / 'reports'}")
