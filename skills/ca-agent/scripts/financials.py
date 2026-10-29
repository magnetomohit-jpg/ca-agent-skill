#!/usr/bin/env python3
"""Prepare Schedule III (Division I) financial statements from a books folder.

    financials.py <folder> [--as-of 2026-03-31] [--prev-books <last-year-folder>] [--out-dir out/] [--json]

Produces: Balance Sheet, Statement of Profit and Loss, Cash Flow Statement (indirect method, AS 3),
account-level notes, a PPE/intangibles movement table, MSME dues with bill age, a tax and deferred tax
summary, Schedule III ratios with >25% variance flags, a small-company (s.2(85)) test and pre-closing
checks. The checks cover missing year-end entries, Suspense, tally errors, statutory dues unpaid at the
year end (GST net of input credit, RCM, TDS, PF/ESI/bonus) and MSME bills older than 45 days.
With --out-dir it also writes financial_statements.md / .json / .xlsx (every sheet headed with the
entity name and CIN; PPE reconciliation, Tax and MSME dues sheets included).
The small-company test uses --prev-books revenue, else turnover_previous_fy or aato_previous_fy in
company.json, else this year's revenue.

Comparatives: last year's balance sheet comes from this year's 'Opening' vouchers; last year's
P&L needs --prev-books. P&L accounts must not be closed into reserves inside the year (books.py
close-year does that when opening the next year), so the current profit is the P&L balance.
"""
from __future__ import annotations

import argparse
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import rules

from common import (LINES, ZERO, Books, BooksError, D, emit, inr, load_json, md_table, money, parse_date, run_cli,
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
        label = name
        if line == "cash_equivalents" and b < 0:
            line = "st_borrowings"
            notes.append(f"{name} has a credit (overdraft) balance and is shown under short-term borrowings")
        elif line == "trade_receivables" and b < 0 and not (acc["tags"] & CONTRA_TAGS):
            line, label = "other_current_liabilities", f"Advance from customer - {name}"
            notes.append(f"{name} has a credit balance (advance received) and is shown under other current liabilities")
        elif line in ("trade_payables_msme", "trade_payables_others") and b > 0:
            line, label = "st_loans_advances", f"Advance to supplier - {name}"
            notes.append(f"{name} has a debit balance (advance paid) and is shown under short-term loans and advances")
        nature = LINES[line][1]
        amt = b if nature in ("asset", "expense", "tax") else -b
        if amt < 0 and not (acc["tags"] & CONTRA_TAGS) and LINES[line][0] == "BS" and line not in (
                "deferred_tax_liab", "deferred_tax_asset", "other_equity"):
            warnings.append(f"{name} ({LINES[line][2]}) has an unusual {'credit' if nature == 'asset' else 'debit'} "
                            f"balance of {inr(abs(amt))} - reclassify (e.g. advance from customer / to supplier) or correct")
        lines[line] += amt
        detail[line].append((label, amt))
    net_dta = lines["deferred_tax_asset"] - lines["deferred_tax_liab"]
    lines["deferred_tax_asset"], lines["deferred_tax_liab"] = (net_dta, ZERO) if net_dta >= 0 else (ZERO, -net_dta)
    # Net DTA/DTL (AS 22 para 29). An account whose balance lands on the other side is labelled so the note
    # does not show "Deferred Tax Liability" under the asset heading without explanation.
    if net_dta >= 0:
        detail["deferred_tax_asset"] = detail["deferred_tax_asset"] + [
            (f"{n} (debit balance, shown as a deferred tax asset)" if a < 0 else f"Less: {n}", -a)
            for n, a in detail["deferred_tax_liab"]]
        detail["deferred_tax_liab"] = []
    else:
        detail["deferred_tax_liab"] = detail["deferred_tax_liab"] + [
            (f"{n} (credit balance, shown as a deferred tax liability)" if a < 0 else f"Less: {n}", -a)
            for n, a in detail["deferred_tax_asset"]]
        detail["deferred_tax_asset"] = []

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


def msme_open_items(books: Books, as_of) -> list[dict]:
    """Open bills of MSME-tagged creditors at `as_of`, oldest first. Payments are taken to clear the oldest bills
    (FIFO), so the closing credit balance is made up of the latest credits. The MSMED Act s.15 limit is 15 days
    from acceptance, or the agreed credit term up to 45 days; `pay_by_45` assumes the longest term."""
    items = []
    for acc in books.accounts_with_tag("msme"):
        name = acc["account"]
        credits = [ln for ln in books.journal
                   if ln["account"].lower() == name.lower() and ln["date"] <= as_of and ln["credit"]]
        balance = -sum((ln["debit"] - ln["credit"] for ln in books.journal
                        if ln["account"].lower() == name.lower() and ln["date"] <= as_of), ZERO)
        left, open_ = balance, []
        for ln in sorted(credits, key=lambda x: x["date"], reverse=True):
            if left <= 0:
                break
            amt = min(left, ln["credit"])
            left -= amt
            opening = ln["voucher_type"].lower() == "opening"
            open_.append({"supplier": name, "ref": "opening balance" if opening else (ln.get("ref") or ln.get("voucher_no")),
                          "date": None if opening else ln["date"], "amount": amt,
                          "age_days": None if opening else (as_of - ln["date"]).days,
                          "pay_by_15": None if opening else ln["date"] + timedelta(days=15),
                          "pay_by_45": None if opening else ln["date"] + timedelta(days=45)})
        items += reversed(open_)
    return items


def statutory_dues(books: Books, closing: dict, as_of=None) -> list[str]:
    """Statutory liabilities still unpaid in the closing balances (GST net of input credit, RCM, TDS, PF/ESI/bonus).

    Wording and due dates follow the report date: the March return at year end, otherwise the return for the
    period containing `as_of` (the quarter's return for QRMP filers)."""
    import rules
    from common import month_end, state_code_of
    msgs = []
    as_of = as_of or books.fy_end
    when = "at year end" if as_of == books.fy_end else f"as at {as_of}"
    qrmp = books.company.get("gst_filing") == "qrmp"
    period_end = month_end(as_of)
    if qrmp:
        while period_end.month not in (3, 6, 9, 12):
            period_end = month_end(period_end + timedelta(days=1))
    nxt = period_end + timedelta(days=1)
    if qrmp:
        state = state_code_of(books.company.get("state_code") or books.company.get("gstin", "")[:2])
        gst_due = nxt.replace(day=22 if state in rules.QRMP_22ND_STATES else 24)
        gst_return = f"GSTR-3B for the quarter ending {period_end.strftime('%b %Y')}"
    else:
        gst_due = nxt.replace(day=20)
        gst_return = f"{period_end.strftime('%B')} GSTR-3B"
    after_month = month_end(as_of) + timedelta(days=1)  # TDS: 7th of next month, 30 April for March
    tds_due = after_month.replace(day=30) if as_of.month == 3 else after_month.replace(day=7)

    def total(tags):
        return -sum((closing.get(a["account"], ZERO) for t in tags for a in books.accounts_with_tag(t)), ZERO)

    heads = ("igst", "cgst", "sgst")
    gst_net = total([f"gst_output_{h}" for h in heads] + [f"gst_input_{h}" for h in heads])
    if gst_net > 0:
        msgs.append(f"GST payable {when}: output tax exceeds input credit by {inr(gst_net)} - confirm it is paid "
                    f"with the {gst_return} (due {gst_due:%d %b %Y}); unpaid GST is disallowed u/s 43B until paid")
    rcm = total([f"gst_rcm_{h}" for h in heads])
    if rcm > 0:
        msgs.append(f"Reverse-charge GST payable {when} {inr(rcm)} - payable in cash with the {gst_return} "
                    f"(due {gst_due:%d %b %Y}); the input credit is available only after payment")
    tds = total(["tds_payable"])
    if tds > 0:
        msgs.append(f"TDS payable {when} {inr(tds)} - deposit by {tds_due:%d %b %Y}; if deposited after the ITR due date, "
                    "30% of the expense is disallowed u/s 40(a)(ia) and interest u/s 201(1A) applies")
    other = total(["statutory_43b"])
    if other > 0:
        msgs.append(f"PF/ESI/bonus/other statutory dues payable {when} {inr(other)} - s.43B allows them only if "
                    "paid by the ITR due date; employees' PF/ESI deposited after the statutory due date is disallowed "
                    "for good u/s 36(1)(va)")
    return msgs


def small_company_status(books: Books, cur: dict, prev: dict | None, has_prev_pl: bool) -> tuple[bool | None, str]:
    """Section 2(85) test on paid-up capital and the previous year's turnover. Returns (likely small, explanation)."""
    co = books.company
    if (co.get("entity_type") or "company").lower() not in {"company", "opc"}:
        return None, ""
    lim = rules.SMALL_COMPANY
    capital = cur["bs"]["share_capital"]
    if has_prev_pl and prev:
        turnover, src = prev["pl"]["revenue"], "previous year's revenue from --prev-books"
    elif co.get("turnover_previous_fy") is not None:
        turnover, src = D(co["turnover_previous_fy"]), "turnover_previous_fy in company.json"
    elif co.get("aato_previous_fy") is not None:
        turnover, src = D(co["aato_previous_fy"]), "aato_previous_fy (GST turnover) in company.json"
    else:
        turnover, src = cur["pl"]["revenue"], "this year's revenue (no previous-year figure given)"
    small = capital <= lim["paid_up_capital"] and turnover <= lim["turnover"]
    text = (f"Small company test (s.2(85)): paid-up capital {inr(capital)} (limit {inr(lim['paid_up_capital'], 0)}), "
            f"turnover {inr(turnover)} from {src} (limit {inr(lim['turnover'], 0)}): "
            + ("within both limits, so it is a small company unless it is a public company, a holding or subsidiary "
               "company, a s.8 company or governed by a special Act. A small company need not include the cash flow "
               "statement (s.2(40)); it is still shown here." if small else
               "outside the limits, so it is not a small company and the cash flow statement is required."))
    return small, text


def ppe_reconciliation(books: Books, as_of) -> list[list]:
    """Gross block and accumulated depreciation movement per account (PPE and intangibles), from the journal."""
    rows, totals = [], {}
    for acc in sorted(books.accounts.values(), key=lambda a: (a["line"], "accumulated_depreciation" in a["tags"], a["account"])):
        if acc["line"] not in ("ppe", "intangible_assets"):
            continue
        contra = "accumulated_depreciation" in acc["tags"]
        lns = [ln for ln in books.journal if ln["account"].lower() == acc["account"].lower() and ln["date"] <= as_of]
        if not lns:
            continue
        sign = -1 if contra else 1   # accumulated depreciation is shown as a positive figure
        opening = sign * sum((ln["debit"] - ln["credit"] for ln in lns if ln["voucher_type"].lower() == "opening"), ZERO)
        dr = sum((ln["debit"] for ln in lns if ln["voucher_type"].lower() != "opening"), ZERO)
        cr = sum((ln["credit"] for ln in lns if ln["voucher_type"].lower() != "opening"), ZERO)
        add, ded = (cr, dr) if contra else (dr, cr)
        closing = opening + add - ded
        kind = "Accumulated depreciation" if contra else "Gross block"
        rows.append([LINES[acc["line"]][2], kind, acc["account"], opening, add, ded, closing])
        t = totals.setdefault((acc["line"], kind), [ZERO] * 4)
        for i, v in enumerate((opening, add, ded, closing)):
            t[i] += v
    for line in ("ppe", "intangible_assets"):
        g = totals.get((line, "Gross block"), [ZERO] * 4)
        a = totals.get((line, "Accumulated depreciation"), [ZERO] * 4)
        if any(g) or any(a):
            rows.append([LINES[line][2], "Net block", "", g[0] - a[0], "", "", g[3] - a[3]])
    return rows


def tax_summary(books: Books, cur: dict, opening: dict, closing: dict) -> list[list]:
    """Tax expense, provision against taxes paid, and the deferred tax movement; adds the income-tax computation
    from <books>/working/tax_computation.json when income_tax.py company has written one."""
    pl = cur["pl"]

    def bal(src, tag):
        return sum((src.get(a["account"], ZERO) for a in books.accounts_with_tag(tag)), ZERO)

    def dt_net(src):  # positive = net liability
        return -sum((src.get(a["account"], ZERO) for a in books.accounts.values()
                     if a["line"] in ("deferred_tax_liab", "deferred_tax_asset")), ZERO)

    tax_exp = pl["current_tax"] + pl["deferred_tax"]
    rows = [["Profit before tax", pl["pbt"]], ["Current tax", pl["current_tax"]], ["Deferred tax", pl["deferred_tax"]],
            ["Total tax expense", tax_exp],
            ["Effective tax rate (%)", money(tax_exp * 100 / pl["pbt"]) if pl["pbt"] else ""], ["", ""],
            ["Provision for income tax (closing)", -bal(closing, "tax_provision")],
            ["Less: advance tax, TDS/TCS and self-assessment tax (closing)", bal(closing, "tax_asset")],
            ["Net tax payable / (refundable)", -bal(closing, "tax_provision") - bal(closing, "tax_asset")], ["", ""],
            ["Deferred tax liability / (asset), opening", dt_net(opening)],
            ["Charge / (credit) to profit and loss", pl["deferred_tax"]],
            ["Deferred tax liability / (asset), closing", dt_net(closing)]]
    comp_path = books.dir / "working" / "tax_computation.json"
    if comp_path.exists():
        comp = load_json(comp_path)
        rows += [["", ""], ["Income-tax computation (working/tax_computation.json)", ""],
                 ["Total income", D(comp.get("total_income"))], ["Tax liability", D(comp.get("liability"))],
                 ["Interest u/s 234A/B/C", D(comp.get("interest_234a")) + D(comp.get("interest_234b")) + D(comp.get("interest_234c"))],
                 ["Balance payable / (refund)", D(comp.get("balance_payable"))]]
        if D(comp.get("liability")) != pl["current_tax"]:
            rows.append(["Difference: current tax booked less computed liability", pl["current_tax"] - D(comp.get("liability"))])
    return rows


def checks(books: Books, cur: dict, closing: dict, as_of) -> list[str]:
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
    msgs += statutory_dues(books, closing, as_of)
    for it in msme_open_items(books, as_of):
        if it["date"] is None:
            msgs.append(f"MSME creditor {it['supplier']}: {inr(it['amount'])} brought forward from last year is still "
                        "unpaid - over 45 days old (MSMED Act s.16 interest, MSME-1, s.43B(h) in the year of payment)")
        elif it["age_days"] > 45:
            msgs.append(f"MSME creditor {it['supplier']}: {inr(it['amount'])} ({it['ref']}, {it['date']}) is "
                        f"{it['age_days']} days old at year end - beyond the 45-day limit: disallowed u/s 43B(h) this "
                        "year, MSMED Act s.16 interest and MSME-1 reporting apply")
    if cur["eq_liab"] != cur["assets"]:
        msgs.append(f"BALANCE SHEET DOES NOT TALLY: difference {inr(cur['eq_liab'] - cur['assets'])}")
    return msgs


# --------------------------------------------------------------------------- rendering

def render(books: Books, cur: dict, prev: dict | None, cf: dict, ratio_rows: list, msgs: list, as_of, has_prev_pl: bool,
           extra: dict):
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

    ppe = extra["ppe"]
    if ppe:
        md += ["**PPE and intangible assets - movement in the year** (gross block and accumulated depreciation from the "
               "journal; add the Schedule III ageing of CWIP and any revaluation by hand)", "",
               md_table(["Line", "Block", "Account", "Opening", "Additions / charge", "Disposals / on disposals", "Closing"],
                        ppe, right={3, 4, 5, 6}), ""]
    if extra["msme"]:
        md += ["**Dues to micro and small enterprises at year end** (oldest bills first; payments assumed to clear the "
               "oldest bills; s.43B(h) and MSMED Act s.15/16)", "",
               md_table(["Supplier", "Bill / ref", "Date", "Amount", "Age (days)", "Pay by (15 days)", "Pay by (45 days)"],
                        [[i["supplier"], i["ref"], i["date"] or "b/f", i["amount"], "" if i["age_days"] is None else i["age_days"],
                          i["pay_by_15"] or "", i["pay_by_45"] or ""] for i in extra["msme"]]), ""]
    md += ["## Income tax and deferred tax", "", md_table(["Particulars", yr], extra["tax"], right={1}), ""]
    md += ["## Ratios (Schedule III additional regulatory information)", ""]
    rr = [[r["ratio"], "" if r["current"] is None else f"{r['current']}", "" if r["previous"] is None else f"{r['previous']}",
           "" if r["variance_pct"] is None else f"{r['variance_pct']}%", "explain (>25%)" if r["explain"] else ""] for r in ratio_rows]
    md += [md_table(["Ratio", "Current", "Previous", "Variance", ""], rr, right={1, 2, 3}),
           "Debt service coverage ratio needs principal repayments - compute separately if the company has term debt.", ""]
    md += ["## Checks before finalising", ""]
    md += [f"- {m}" for m in (msgs + cur["notes"])] or ["- No issues found"]
    if extra["small_company"]:
        md += ["", extra["small_company"]]
    md += ["", "_Draft prepared from the books. Review classifications, provisions, contingent liabilities, related-party "
           "and MSME disclosures, and Schedule III additional regulatory information before approval and audit._"]
    sheets = [("Balance Sheet", xl_bs), ("Profit and Loss", xl_pl), ("Cash Flow", xl_cf), ("Notes", xl_notes),
              ("Ratios", [["Ratio", "Current", "Previous", "Variance %"]] +
               [[r["ratio"], r["current"], r["previous"], r["variance_pct"]] for r in ratio_rows])]
    if ppe:
        sheets.insert(4, ("PPE reconciliation", [["Line", "Block", "Account", "Opening", "Additions / charge",
                                                  "Disposals / on disposals", "Closing"]] + ppe))
    sheets.append(("Tax", [["Particulars", yr]] + extra["tax"]))
    if extra["msme"]:
        sheets.append(("MSME dues", [["Supplier", "Bill / ref", "Date", "Amount", "Age (days)", "Pay by (15 days)",
                                      "Pay by (45 days)"]] +
                       [[i["supplier"], i["ref"], i["date"].isoformat() if i["date"] else "b/f", i["amount"],
                         i["age_days"], i["pay_by_15"].isoformat() if i["pay_by_15"] else "",
                         i["pay_by_45"].isoformat() if i["pay_by_45"] else ""] for i in extra["msme"]]))
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
    msgs = checks(books, cur, closing, as_of)
    if cf["difference"]:
        msgs.append(f"Cash flow does not reconcile by {inr(cf['difference'])} - check account line mapping")
    small, small_text = small_company_status(books, cur, prev, has_prev_pl)
    extra = {"ppe": ppe_reconciliation(books, as_of), "tax": tax_summary(books, cur, opening, closing),
             "msme": msme_open_items(books, as_of), "small_company": small_text}
    markdown, sheets = render(books, cur, prev, cf, ratio_rows, msgs, as_of, has_prev_pl, extra)
    data = {"company": books.company.get("name"), "fy": books.fy, "as_of": as_of,
            "balance_sheet": cur["bs"], "total_assets": cur["assets"], "total_equity_liabilities": cur["eq_liab"],
            "profit_and_loss": cur["pl"], "cash_flow": cf, "ratios": ratio_rows, "checks": msgs,
            "notes": {k: v for k, v in cur["detail"].items() if v}, "small_company": small,
            "small_company_test": small_text, "msme_dues": extra["msme"],
            "ppe_reconciliation": extra["ppe"], "tax": extra["tax"]}
    emit(markdown, data, args)
    if args.out_dir:
        co = books.company
        heading = [co.get("name") or "", f"CIN: {co.get('cin') or 'n/a'} | Financial year {books.fy} | Amounts in Rs"]
        if write_xlsx(Path(args.out_dir) / "financial_statements.xlsx", sheets, heading):
            print(f"\nSaved {Path(args.out_dir) / 'financial_statements.xlsx'}")


if __name__ == "__main__":
    run_cli(main)
