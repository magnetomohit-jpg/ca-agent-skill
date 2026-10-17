#!/usr/bin/env python3
"""Prepare Schedule III (Division I) financial statements from a books folder.

    financials.py <folder> [--as-of 2026-03-31] [--prev-books <last-year-folder>] [--out-dir out/] [--json]

Produces: Balance Sheet, Statement of Profit and Loss, Cash Flow Statement (indirect method, AS 3),
account-level notes, Schedule III ratios with >25% variance flags, and pre-closing checks.
With --out-dir it also writes financial_statements.md / .json / .xlsx.

Comparatives: last year's balance sheet comes from this year's 'Opening' vouchers; last year's
P&L needs --prev-books. P&L accounts must not be closed into reserves inside the year (books.py
close-year does that when opening the next year), so the current profit is the P&L balance.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path

from common import (LINES, ZERO, Books, BooksError, D, emit, inr, md_table, money, parse_date, run_cli,
                    write_xlsx)

BS_LAYOUT = [
    ("I. EQUITY AND LIABILITIES", None),
    ("(1) Shareholders' funds", ["share_capital", "other_equity"]),
    ("(2) Share application money pending allotment", ["share_application_money"]),
    ("(3) Non-current liabilities", ["lt_borrowings", "deferred_tax_liab", "other_lt_liabilities", "lt_provisions"]),
    ("(4) Current liabilities", ["st_borrowings", "trade_payables_msme", "trade_payables_others",
                                 "other_current_liabilities", "st_provisions"]),
    ("TOTAL", "eq_liab"),
    ("II. ASSETS", None),
    ("(1) Non-current assets", ["ppe", "intangible_assets", "cwip", "intangible_under_dev", "nc_investments",
                                "deferred_tax_asset", "lt_loans_advances", "other_nc_assets"]),
    ("(2) Current assets", ["current_investments", "inventories", "trade_receivables", "cash_equivalents",
                            "st_loans_advances", "other_current_assets"]),
    ("TOTAL", "assets"),
]
PL_EXPENSE_LINES = ["cost_materials", "purchases_stock", "changes_inventories", "employee_benefits",
                    "finance_costs", "depreciation", "other_expenses"]
CURRENT_ASSET_LINES = ["current_investments", "inventories", "trade_receivables", "cash_equivalents",
                       "st_loans_advances", "other_current_assets"]
CURRENT_LIAB_LINES = ["st_borrowings", "trade_payables_msme", "trade_payables_others",
                      "other_current_liabilities", "st_provisions"]
CONTRA_TAGS = {"accumulated_depreciation", "provision_doubtful_debts", "contra"}
TAX_TAGS = {"tax_provision", "tax_asset"}


# --------------------------------------------------------------------------- core computation

def compute(books: Books, bal: dict) -> dict:
    """Group signed balances into Schedule III lines (natural sign: assets/expenses Dr+, others Cr+)."""
    lines = {k: ZERO for k in LINES}
    detail: dict[str, list] = {k: [] for k in LINES}
    notes, warnings = [], []
    def order(item):
        acc = books.accounts.get(item[0].lower())
        return (bool(acc and acc["tags"] & CONTRA_TAGS), item[0].lower())

    for name, b in sorted(bal.items(), key=order):
        if b == 0:
            continue
        acc = books.accounts.get(name.lower())
        if not acc:
            raise BooksError(f"Journal uses unknown account {name!r}; run books.py validate")
        line = acc["line"]
        if line == "cash_equivalents" and b < 0:
            line = "st_borrowings"
            notes.append(f"{name} has a credit (overdraft) balance and is shown under short-term borrowings")
        nature = LINES[line][1]
        amt = b if nature in ("asset", "expense", "tax") else -b
        if amt < 0 and not (acc["tags"] & CONTRA_TAGS) and LINES[line][0] == "BS" and line not in (
                "deferred_tax_liab", "deferred_tax_asset", "other_equity"):
            warnings.append(f"{name} ({LINES[line][2]}) has an unusual {'credit' if nature == 'asset' else 'debit'} "
                            f"balance of {inr(abs(amt))} - reclassify (e.g. advance from customer / to supplier) or correct")
        lines[line] += amt
        detail[line].append((name, amt))
    net_dta = lines["deferred_tax_asset"] - lines["deferred_tax_liab"]
    dt_detail = detail["deferred_tax_asset"] + [(n, -a) for n, a in detail["deferred_tax_liab"]]
    lines["deferred_tax_asset"], lines["deferred_tax_liab"] = (net_dta, ZERO) if net_dta >= 0 else (ZERO, -net_dta)
    if net_dta >= 0:
        detail["deferred_tax_asset"], detail["deferred_tax_liab"] = dt_detail, []
    else:
        detail["deferred_tax_liab"], detail["deferred_tax_asset"] = [(n, -a) for n, a in dt_detail], []

    pl = {"revenue": lines["revenue_operations"], "other_income": lines["other_income"]}
    pl["total_income"] = pl["revenue"] + pl["other_income"]
    pl["expenses"] = {k: lines[k] for k in PL_EXPENSE_LINES}
    pl["total_expenses"] = sum(pl["expenses"].values(), ZERO)
    pl["profit_before_exceptional"] = pl["total_income"] - pl["total_expenses"]
    pl["exceptional"] = lines["exceptional_items"]
    pl["pbt"] = pl["profit_before_exceptional"] - pl["exceptional"]
    pl["current_tax"] = lines["current_tax"]
    pl["deferred_tax"] = lines["deferred_tax"]
    pl["pat"] = pl["pbt"] - pl["current_tax"] - pl["deferred_tax"]

    bs = {k: lines[k] for k, v in LINES.items() if v[0] == "BS"}
    bs["other_equity_opening_and_movements"] = bs["other_equity"]
    bs["other_equity"] = bs["other_equity"] + pl["pat"]
    detail["other_equity"].append(("Profit/(loss) for the year", pl["pat"]))
    eq_liab = sum((bs[k] for k in LINES if LINES[k][0] == "BS" and LINES[k][1] in ("equity", "liability")), ZERO)
    assets = sum((bs[k] for k in LINES if LINES[k][0] == "BS" and LINES[k][1] == "asset"), ZERO)
    return {"lines": lines, "detail": detail, "pl": pl, "bs": bs, "eq_liab": eq_liab, "assets": assets,
            "notes": notes, "warnings": warnings}


def cash_flow(books: Books, opening: dict, closing: dict, cur: dict) -> dict:
    """Indirect-method cash flow from balance movements. Reconciles to the change in cash by construction."""
    pl = cur["pl"]

    def tagged_pl(tag):  # natural-sign P&L amount for accounts carrying a tag
        total = ZERO
        for acc in books.accounts_with_tag(tag):
            b = closing.get(acc["account"], ZERO)
            total += -b if LINES[acc["line"]][1] == "income" else b
        return total

    delta: dict[str, Decimal] = {}
    for name in set(opening) | set(closing):
        acc = books.accounts.get(name.lower())
        if acc and LINES[acc["line"]][0] == "BS":
            delta[name] = closing.get(name, ZERO) - opening.get(name, ZERO)

    dep = pl["expenses"]["depreciation"]
    fin = pl["expenses"]["finance_costs"]
    int_inc, div_inc = tagged_pl("interest_income"), tagged_pl("dividend_income")
    gain, loss = tagged_pl("gain_on_sale"), tagged_pl("loss_on_sale")

    op = [("Net profit before tax", pl["pbt"]), ("Adjustments for:", None),
          ("Depreciation and amortisation", dep), ("Finance costs", fin),
          ("Interest income", -int_inc), ("Dividend income", -div_inc),
          ("Profit on sale of assets/investments", -gain), ("Loss on sale of assets/investments", loss)]
    op_before_wc = pl["pbt"] + dep + fin - int_inc - div_inc - gain + loss
    op.append(("Operating profit before working capital changes", op_before_wc))
    wc: dict[str, Decimal] = {}
    tax_movement = ZERO
    groups: dict[str, Decimal] = {}
    for name, dlt in delta.items():
        acc = books.accounts[name.lower()]
        line = acc["line"]
        cls = LINES[line][4]
        if acc["tags"] & TAX_TAGS:
            tax_movement += -dlt
        elif cls == "operating":
            wc[line] = wc.get(line, ZERO) - dlt
        else:
            groups[cls if line not in ("nc_investments", "current_investments") else "investments"] = \
                groups.get(cls if line not in ("nc_investments", "current_investments") else "investments", ZERO) - dlt
            if cls == "financing":
                groups[f"fin:{line}"] = groups.get(f"fin:{line}", ZERO) - dlt
    op.append(("Working capital changes:", None))
    for line, amt in sorted(wc.items(), key=lambda kv: list(LINES).index(kv[0])):
        label = LINES[line][2]
        op.append((f"(Increase)/decrease in {label.lower()}" if LINES[line][1] == "asset"
                   else f"Increase/(decrease) in {label.lower()}", amt))
    cash_generated = op_before_wc + sum(wc.values(), ZERO)
    op.append(("Cash generated from operations", cash_generated))
    taxes_paid = -pl["current_tax"] + tax_movement
    op.append(("Income taxes paid (net of refunds)", taxes_paid))
    net_op = cash_generated + taxes_paid

    capex = groups.get("investing", ZERO) - dep + gain - loss
    inv = [("Purchase of property, plant and equipment and intangibles (net of disposals)", capex),
           ("(Purchase)/sale of investments (net)", groups.get("investments", ZERO)),
           ("Interest received", int_inc), ("Dividend received", div_inc)]
    net_inv = capex + groups.get("investments", ZERO) + int_inc + div_inc

    fin_rows = [
        ("Proceeds from issue of share capital", groups.get("fin:share_capital", ZERO) + groups.get("fin:share_application_money", ZERO)),
        ("Other equity movements (securities premium, dividends paid)", groups.get("fin:other_equity", ZERO)),
        ("Long-term borrowings taken/(repaid) (net)", groups.get("fin:lt_borrowings", ZERO)),
        ("Short-term borrowings taken/(repaid) (net)", groups.get("fin:st_borrowings", ZERO)),
        ("Finance costs paid", -fin),
    ]
    net_fin = sum((a for _, a in fin_rows), ZERO)
    cash_open = sum((opening.get(a["account"], ZERO) for a in books.accounts.values() if a["line"] == "cash_equivalents"), ZERO)
    cash_close = sum((closing.get(a["account"], ZERO) for a in books.accounts.values() if a["line"] == "cash_equivalents"), ZERO)
    net = net_op + net_inv + net_fin
    return {"operating": op, "net_operating": net_op, "investing": inv, "net_investing": net_inv,
            "financing": fin_rows, "net_financing": net_fin, "net_change": net,
            "cash_opening": cash_open, "cash_closing": cash_close,
            "difference": money(cash_close - cash_open - net)}


def ratios(cur: dict, prev: dict | None) -> list[dict]:
    def calc(s, p_avg):
        b, pl = s["bs"], s["pl"]
        ca = sum((b[k] for k in CURRENT_ASSET_LINES), ZERO)
        cl = sum((b[k] for k in CURRENT_LIAB_LINES), ZERO)
        equity = b["share_capital"] + b["other_equity"] + b["share_application_money"]
        debt = b["lt_borrowings"] + b["st_borrowings"]
        cogs = pl["expenses"]["cost_materials"] + pl["expenses"]["purchases_stock"] + pl["expenses"]["changes_inventories"]
        purchases = pl["expenses"]["cost_materials"] + pl["expenses"]["purchases_stock"]
        ebit = pl["pbt"] + pl["expenses"]["finance_costs"]
        avg = p_avg or (lambda k: b[k])
        out = {
            "Current ratio": (ca, cl),
            "Debt-equity ratio": (debt, equity),
            "Return on equity (%)": (pl["pat"] * 100, avg("equity_total")),
            "Inventory turnover": (cogs, avg("inventories")),
            "Trade receivables turnover": (pl["revenue"], avg("trade_receivables")),
            "Trade payables turnover": (purchases, avg("trade_payables")),
            "Net capital turnover": (pl["revenue"], ca - cl),
            "Net profit ratio (%)": (pl["pat"] * 100, pl["revenue"]),
            "Return on capital employed (%)": (ebit * 100, equity + debt + b["deferred_tax_liab"]),
        }
        return {k: (money(n / d) if d else None) for k, (n, d) in out.items()}

    def with_totals(s):
        b = dict(s["bs"])
        b["equity_total"] = b["share_capital"] + b["other_equity"] + b["share_application_money"]
        b["trade_payables"] = b["trade_payables_msme"] + b["trade_payables_others"]
        return {**s, "bs": b}

    cur_t = with_totals(cur)
    prev_t = with_totals(prev) if prev else None
    avg = (lambda k: (cur_t["bs"][k] + prev_t["bs"][k]) / 2) if prev_t else None
    c = calc(cur_t, avg)
    p = calc(prev_t, None) if prev_t and prev_t["pl"]["revenue"] else {}
    rows = []
    for k, v in c.items():
        pv = p.get(k) if p else None
        var = money((v - pv) / abs(pv) * 100) if (v is not None and pv) else None
        rows.append({"ratio": k, "current": v, "previous": pv, "variance_pct": var,
                     "explain": var is not None and abs(var) > 25})
    return rows


def checks(books: Books, cur: dict, closing: dict) -> list[str]:
    msgs = list(cur["warnings"])
    pl, lines = cur["pl"], cur["lines"]
    if pl["pbt"] > 0 and pl["current_tax"] == 0:
        msgs.append("Profit before tax is positive but no current tax is booked - compute it with income_tax.py "
                    "and post Dr Current Tax / Cr Provision for Income Tax")
    if lines["ppe"] > 0 and pl["expenses"]["depreciation"] == 0:
        msgs.append("Property, plant and equipment exist but no depreciation is booked - run depreciation.py")
    if (pl["expenses"]["purchases_stock"] > 0 or pl["expenses"]["cost_materials"] > 0) and lines["changes_inventories"] == 0 \
            and lines["inventories"] == 0:
        msgs.append("Purchases exist but no inventory/closing stock is recorded - confirm closing stock is nil or book it")
    if lines["trade_payables_others"] > 0 and lines["trade_payables_msme"] == 0:
        msgs.append("All trade payables are shown as non-MSME - confirm suppliers' Udyam status (MSMED Act disclosure "
                    "and sec 43B(h) 45-day rule)")
    for acc in books.accounts_with_tag("suspense"):
        if closing.get(acc["account"], ZERO):
            msgs.append(f"Suspense account {acc['account']} is not cleared")
    if cur["eq_liab"] != cur["assets"]:
        msgs.append(f"BALANCE SHEET DOES NOT TALLY: difference {inr(cur['eq_liab'] - cur['assets'])}")
    return msgs


# --------------------------------------------------------------------------- rendering

def render(books: Books, cur: dict, prev: dict | None, cf: dict, ratio_rows: list, msgs: list, as_of, has_prev_pl: bool):
    co = books.company
    yr = as_of.strftime("%d-%m-%Y")
    pyr = f"31-03-{as_of.year - 1}" if as_of.month == 3 and as_of.day == 31 else "Previous"
    note_no, note_map = 2, {}
    for key in [k for k, v in LINES.items() if v[0] == "BS"] + ["revenue_operations", "other_income"] + PL_EXPENSE_LINES \
            + ["exceptional_items"]:
        amount = cur["bs"].get(key, cur["lines"].get(key, ZERO))
        if amount or (prev and prev["bs"].get(key, prev["lines"].get(key, ZERO))):
            note_map[key] = note_no
            note_no += 1

    def pv(key, src="bs"):
        if not prev:
            return ""
        return prev[src].get(key, ZERO) if src == "bs" else prev["pl"].get(key, ZERO)

    bs_rows, xl_bs = [], [["Particulars", "Note", yr, pyr]]
    for label, keys in BS_LAYOUT:
        if keys is None:
            bs_rows.append([f"**{label}**", "", "", ""])
            xl_bs.append([label, "", "", ""])
        elif isinstance(keys, str):
            c = cur[keys]
            p = prev[keys] if prev else ""
            bs_rows.append([f"**{label}**", "", f"**{inr(c)}**", f"**{inr(p)}**" if prev else ""])
            xl_bs.append([label, "", c, p])
        else:
            shown = [k for k in keys if cur["bs"][k] or (prev and prev["bs"][k])]
            if not shown:
                continue
            bs_rows.append([label, "", "", ""])
            xl_bs.append([label, "", "", ""])
            for k in shown:
                bs_rows.append([f"&nbsp;&nbsp;{LINES[k][2]}", note_map.get(k, ""), cur["bs"][k], pv(k)])
                xl_bs.append([f"    {LINES[k][2]}", note_map.get(k, ""), cur["bs"][k], pv(k)])

    pl = cur["pl"]
    ppl = prev["pl"] if (prev and has_prev_pl) else None

    def pp(key, sub=None):
        if not ppl:
            return ""
        return ppl[key][sub] if sub else ppl[key]

    pl_rows = [
        ["I. Revenue from operations", note_map.get("revenue_operations", ""), pl["revenue"], pp("revenue")],
        ["II. Other income", note_map.get("other_income", ""), pl["other_income"], pp("other_income")],
        ["**III. Total income (I + II)**", "", pl["total_income"], pp("total_income")],
        ["IV. Expenses:", "", "", ""],
    ]
    for k in PL_EXPENSE_LINES:
        if pl["expenses"][k] or (ppl and ppl["expenses"][k]):
            pl_rows.append([f"&nbsp;&nbsp;{LINES[k][2]}", note_map.get(k, ""), pl["expenses"][k], pp("expenses", k)])
    pl_rows += [
        ["**Total expenses (IV)**", "", pl["total_expenses"], pp("total_expenses")],
        ["V. Profit before exceptional items and tax (III - IV)", "", pl["profit_before_exceptional"], pp("profit_before_exceptional")],
        ["VI. Exceptional items", note_map.get("exceptional_items", ""), pl["exceptional"], pp("exceptional")],
        ["**VII. Profit before tax (V - VI)**", "", pl["pbt"], pp("pbt")],
        ["VIII. Tax expense: (1) Current tax", "", pl["current_tax"], pp("current_tax")],
        ["&nbsp;&nbsp;(2) Deferred tax", "", pl["deferred_tax"], pp("deferred_tax")],
        ["**IX. Profit/(loss) for the year (VII - VIII)**", "", pl["pat"], pp("pat")],
    ]
    shares = D(co.get("equity_shares_outstanding") or 0)
    if shares:
        eps = money(pl["pat"] / shares)
        pl_rows.append([f"X. Earnings per equity share (face value Rs {co.get('face_value', 10)}): basic and diluted", "",
                        eps, money(ppl["pat"] / shares) if ppl else ""])
    xl_pl = [["Particulars", "Note", yr, pyr]] + [[str(r[0]).replace("**", "").replace("&nbsp;", " "), *r[1:]] for r in pl_rows]

    cf_rows = [["**A. Cash flow from operating activities**", ""]]
    cf_rows += [[("&nbsp;&nbsp;" if a is not None else "") + l, a if a is not None else ""] for l, a in cf["operating"]
                if a is None or a != 0 or l.startswith(("Net profit", "Operating profit", "Cash generated"))]
    cf_rows += [["**Net cash from operating activities (A)**", cf["net_operating"]],
                ["**B. Cash flow from investing activities**", ""]]
    cf_rows += [["&nbsp;&nbsp;" + l, a] for l, a in cf["investing"] if a]
    cf_rows += [["**Net cash used in investing activities (B)**", cf["net_investing"]],
                ["**C. Cash flow from financing activities**", ""]]
    cf_rows += [["&nbsp;&nbsp;" + l, a] for l, a in cf["financing"] if a]
    cf_rows += [["**Net cash from financing activities (C)**", cf["net_financing"]],
                ["**Net increase/(decrease) in cash and cash equivalents (A+B+C)**", cf["net_change"]],
                ["Cash and cash equivalents at the beginning of the year", cf["cash_opening"]],
                ["Cash and cash equivalents at the end of the year", cf["cash_closing"]]]
    xl_cf = [["Particulars", yr]] + [[str(r[0]).replace("**", "").replace("&nbsp;", " "), r[1]] for r in cf_rows]

    md = [f"# Financial statements - {co.get('name')}",
          f"CIN: {co.get('cin') or 'n/a'} | PAN: {co.get('pan') or 'n/a'} | GSTIN: {co.get('gstin') or 'n/a'} | "
          f"Financial year {books.fy} | Amounts in Rs",
          "", f"## Balance Sheet as at {yr}", "",
          md_table(["Particulars", "Note", yr, pyr], bs_rows, right={2, 3}),
          "", f"## Statement of Profit and Loss for the year ended {yr}", "",
          md_table(["Particulars", "Note", yr, pyr if ppl else f"{pyr} (n/a - pass --prev-books)"], pl_rows, right={2, 3}),
          "", f"## Cash Flow Statement for the year ended {yr} (indirect method, AS 3)", "",
          md_table(["Particulars", yr], cf_rows, right={1}),
          "" if cf["difference"] == 0 else f"\n**Cash flow does not reconcile to cash movement by {inr(cf['difference'])}**",
          "", "## Notes to the financial statements", "",
          "**Note 1 - Significant accounting policies:** prepared under the historical cost convention on an accrual "
          "basis in accordance with the Accounting Standards notified under section 133 of the Companies Act, 2013 "
          "(edit to reflect the entity's actual policies: revenue recognition, inventory valuation, depreciation "
          "method, employee benefits, taxes).", ""]
    xl_notes = [["Note", "Line", "Account", yr, pyr]]
    for key, no in note_map.items():
        rows = []
        prev_detail = dict(prev["detail"].get(key, [])) if prev else {}
        names = [n for n, _ in cur["detail"].get(key, [])] + [n for n in prev_detail if n not in dict(cur["detail"].get(key, []))]
        cur_detail = dict(cur["detail"].get(key, []))
        for n in names:
            rows.append([n, cur_detail.get(n, ZERO), prev_detail.get(n, "") if prev else ""])
            xl_notes.append([no, LINES[key][2], n, cur_detail.get(n, ZERO), prev_detail.get(n, "") if prev else ""])
        total = cur["bs"].get(key, cur["lines"].get(key, ZERO))
        rows.append(["**Total**", total, (prev["bs"].get(key, prev["lines"].get(key, ZERO)) if prev else "")])
        md += [f"**Note {no} - {LINES[key][2]}**", "", md_table(["Particulars", yr, pyr], rows, right={1, 2}), ""]

    md += ["## Ratios (Schedule III additional regulatory information)", ""]
    rr = [[r["ratio"], "" if r["current"] is None else f"{r['current']}", "" if r["previous"] is None else f"{r['previous']}",
           "" if r["variance_pct"] is None else f"{r['variance_pct']}%", "explain (>25%)" if r["explain"] else ""] for r in ratio_rows]
    md += [md_table(["Ratio", "Current", "Previous", "Variance", ""], rr, right={1, 2, 3}),
           "Debt service coverage ratio needs principal repayments - compute separately if the company has term debt.", ""]
    md += ["## Checks before finalising", ""]
    md += [f"- {m}" for m in (msgs + cur["notes"])] or ["- No issues found"]
    md += ["", "_Draft prepared from the books. Review classifications, provisions, contingent liabilities, related-party "
           "and MSME disclosures, and Schedule III additional regulatory information before approval and audit._"]
    sheets = [("Balance Sheet", xl_bs), ("Profit and Loss", xl_pl), ("Cash Flow", xl_cf), ("Notes", xl_notes),
              ("Ratios", [["Ratio", "Current", "Previous", "Variance %"]] +
               [[r["ratio"], r["current"], r["previous"], r["variance_pct"]] for r in ratio_rows])]
    return "\n".join(md), sheets


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--as-of")
    ap.add_argument("--prev-books", help="last year's books folder, for P&L comparatives")
    ap.add_argument("--out-dir")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    args.report_name = "financial_statements"

    books = Books(args.folder)
    as_of = parse_date(args.as_of) if args.as_of else books.fy_end
    closing = books.balances(end=as_of)
    opening = books.opening_balances()
    cur = compute(books, closing)
    has_prev_pl = False
    if args.prev_books:
        pbooks = Books(args.prev_books)
        prev = compute(pbooks, pbooks.balances())
        has_prev_pl = True
    else:
        prev = compute(books, opening) if opening else None
    cf = cash_flow(books, opening, closing, cur)
    ratio_rows = ratios(cur, prev if has_prev_pl or prev else None)
    msgs = checks(books, cur, closing)
    if cf["difference"]:
        msgs.append(f"Cash flow does not reconcile by {inr(cf['difference'])} - check account line mapping")
    markdown, sheets = render(books, cur, prev, cf, ratio_rows, msgs, as_of, has_prev_pl)
    data = {"company": books.company.get("name"), "fy": books.fy, "as_of": as_of,
            "balance_sheet": cur["bs"], "total_assets": cur["assets"], "total_equity_liabilities": cur["eq_liab"],
            "profit_and_loss": cur["pl"], "cash_flow": cf, "ratios": ratio_rows, "checks": msgs,
            "notes": {k: v for k, v in cur["detail"].items() if v}}
    emit(markdown, data, args)
    if args.out_dir:
        if write_xlsx(Path(args.out_dir) / "financial_statements.xlsx", sheets):
            print(f"\nSaved {Path(args.out_dir) / 'financial_statements.xlsx'}")


if __name__ == "__main__":
    run_cli(main)
