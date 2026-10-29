#!/usr/bin/env python3
"""Party records: party master, debtors and creditors sheets with ageing, advances, balance confirmations.

    parties.py sync    <folder>                          add a parties.csv row for every party account (fills GSTIN,
                                                          state and MSME status from the registers and tags)
    parties.py report  <folder> [--as-of 2026-03-31] [--out-dir out/] [--json]
                                                          debtors, creditors and advances sheets: party-wise balance,
                                                          not-due / overdue, Schedule III ageing, master-data checks
    parties.py confirm <folder> [--party NAME] [--as-of ...] --out-dir letters/
                                                          balance-confirmation letters (one .md per party + index)

Party accounts are the accounts on trade_receivables / trade_payables_msme / trade_payables_others (and any
account tagged debtor or creditor), excluding contra accounts such as the provision for doubtful debts.
Book an advance in the party's own account (Dr supplier / Cr customer): a supplier with a debit balance is an
advance to that supplier, a customer with a credit balance is an advance from that customer, and the balance
sheet shows them under loans and advances / other current liabilities automatically.

Open items are found first-in-first-out: payments clear the oldest bills, so a balance is made up of the
latest bills. Age runs from the due date (bill date + credit_days from parties.csv), as Schedule III requires.

parties.csv columns: party, account, type (customer/supplier/both), gstin, pan, state_code, msme_category
(micro/small/medium or blank), udyam_no, credit_days, tds_section, disputed (Y/N), email, phone, address
"""
from __future__ import annotations

import argparse
import re
from datetime import timedelta
from pathlib import Path

from common import (ZERO, Books, BooksError, D, emit, gstin_problem, inr, md_table, pan_problem, parse_date,
                    read_rows, run_cli, write_rows, write_xlsx)

PARTY_HEADERS = ["party", "account", "type", "gstin", "pan", "state_code", "msme_category", "udyam_no",
                 "credit_days", "tds_section", "disputed", "email", "phone", "address"]
DEBTOR_LINES = {"trade_receivables"}
CREDITOR_LINES = {"trade_payables_msme", "trade_payables_others"}
CONTRA = {"accumulated_depreciation", "provision_doubtful_debts", "contra"}
# Schedule III ageing buckets, in days past the due date: (label, upper bound inclusive or None).
RECEIVABLE_BUCKETS = [("Less than 6 months", 182), ("6 months - 1 year", 365), ("1-2 years", 730),
                      ("2-3 years", 1095), ("More than 3 years", None)]
PAYABLE_BUCKETS = [("Less than 1 year", 365), ("1-2 years", 730), ("2-3 years", 1095), ("More than 3 years", None)]


def party_accounts(books: Books) -> list[dict]:
    out = []
    for acc in books.accounts.values():
        if acc["tags"] & CONTRA:
            continue
        if acc["line"] in DEBTOR_LINES or "debtor" in acc["tags"]:
            out.append({**acc, "side": "customer"})
        elif acc["line"] in CREDITOR_LINES or "creditor" in acc["tags"]:
            out.append({**acc, "side": "supplier"})
    return out


def load_master(books: Books) -> dict[str, dict]:
    """parties.csv keyed by lower-case ledger account name (the `account` column, defaulting to `party`)."""
    master = {}
    for row in read_rows(books.dir / "parties.csv", required=False):
        key = (row.get("account") or row.get("party") or "").strip().lower()
        if key:
            master[key] = row
    return master


def open_items(books: Books, account: str, as_of, credit_days: int) -> tuple[D, list[dict]]:
    """Signed balance (Dr+) and the FIFO open items that make it up, each with its due date and days past due."""
    lines = [ln for ln in books.journal if ln["account"].lower() == account.lower() and ln["date"] <= as_of]
    balance = sum((ln["debit"] - ln["credit"] for ln in lines), ZERO)
    if balance == 0:
        return balance, []
    field = "debit" if balance > 0 else "credit"
    left, items = abs(balance), []
    for ln in sorted((x for x in lines if x[field]), key=lambda x: x["date"], reverse=True):
        if left <= 0:
            break
        amt = min(left, ln[field])
        left -= amt
        opening = ln["voucher_type"].lower() == "opening"
        due = ln["date"] + timedelta(days=credit_days)
        items.append({"date": ln["date"], "ref": "opening balance" if opening else (ln.get("ref") or ln.get("voucher_no")),
                      "amount": amt, "due": due, "days_past_due": (as_of - due).days, "opening": opening,
                      "narration": ln.get("narration", "")})
    return balance, list(reversed(items))


def bucket_of(days: int, buckets) -> str:
    if days < 0:
        return "Not due"
    for label, upper in buckets:
        if upper is None or days <= upper:
            return label
    return buckets[-1][0]


def build(books: Books, as_of) -> dict:
    master = load_master(books)
    debtors, creditors, adv_to_suppliers, adv_from_customers, checks = [], [], [], [], []
    for acc in sorted(party_accounts(books), key=lambda a: a["account"].lower()):
        m = master.get(acc["account"].lower(), {})
        try:
            credit_days = int(D(m.get("credit_days") or 0))
        except Exception:  # noqa: BLE001 - a typo in the master should not stop the report
            credit_days = 0
        terms_set = str(m.get("credit_days") or "").strip() != ""
        balance, items = open_items(books, acc["account"], as_of, credit_days)
        used = any(ln["account"].lower() == acc["account"].lower() for ln in books.journal)
        if not m and used:
            checks.append(f"{acc['account']}: no row in parties.csv (run parties.py sync, then fill GSTIN/PAN/credit days)")
        if balance == 0:
            continue
        is_customer = acc["side"] == "customer"
        normal = (balance > 0) if is_customer else (balance < 0)
        msme = (m.get("msme_category") or "").strip().lower() in {"micro", "small"} or "msme" in acc["tags"] \
            or acc["line"] == "trade_payables_msme"
        disputed = (m.get("disputed") or "").strip().upper().startswith("Y")
        row = {"party": acc["account"], "gstin": m.get("gstin", ""), "credit_days": credit_days if terms_set else None,
               "balance": abs(balance), "msme": msme, "disputed": disputed, "items": items,
               "oldest": items[0]["date"] if items else None,
               "days_outstanding": (as_of - items[0]["date"]).days if items else 0,
               "max_days_past_due": max((i["days_past_due"] for i in items), default=0)}
        buckets = RECEIVABLE_BUCKETS if is_customer else PAYABLE_BUCKETS
        row["ageing"] = {label: ZERO for label in ["Not due"] + [b[0] for b in buckets]}
        for it in items:
            row["ageing"][bucket_of(it["days_past_due"], buckets)] += it["amount"]
        row["overdue"] = sum((v for k, v in row["ageing"].items() if k != "Not due"), ZERO)
        if normal:
            (debtors if is_customer else creditors).append(row)
        else:
            (adv_from_customers if is_customer else adv_to_suppliers).append(row)
    # Non-party control accounts for advances, shown so the advances sheet is complete.
    for name, target in (("advances to suppliers", adv_to_suppliers), ("advance from customers", adv_from_customers)):
        acc = books.accounts.get(name)
        if acc:
            bal = books.balances(end=as_of).get(acc["account"], ZERO)
            if bal:
                target.append({"party": f"{acc['account']} (not party-wise)", "gstin": "", "credit_days": 0,
                               "balance": abs(bal), "msme": False, "disputed": False, "items": [], "oldest": None,
                               "max_days_past_due": 0, "ageing": {}, "overdue": ZERO})
    for key, m in master.items():
        if key not in books.accounts:
            checks.append(f"parties.csv row {m.get('party')!r}: no ledger account named {m.get('account') or m.get('party')!r}")
        g = (m.get("gstin") or "").strip()
        if g and (p := gstin_problem(g)):
            checks.append(f"{m.get('party')}: GSTIN {g} {p}")
        if g and m.get("pan") and g[2:12].upper() != m["pan"].strip().upper():
            checks.append(f"{m.get('party')}: PAN {m['pan']} does not match the PAN inside GSTIN {g}")
        if m.get("pan") and (p := pan_problem(m["pan"])):
            checks.append(f"{m.get('party')}: {p}")
        if (m.get("msme_category") or "").strip().lower() in {"micro", "small"} and not m.get("udyam_no"):
            checks.append(f"{m.get('party')}: marked {m['msme_category']} but no Udyam number - obtain the certificate")
    for r in creditors:
        if r["msme"]:
            late = [i for i in r["items"] if not i["opening"] and (as_of - i["date"]).days > 45]
            if late:
                checks.append(f"{r['party']} (MSME): {len(late)} bill(s) older than 45 days, Rs {inr(sum(i['amount'] for i in late))} "
                              "- s.43B(h) disallowance if unpaid at year end, interest u/s 16 MSMED Act, MSME-1 reporting")
    for r in adv_to_suppliers:
        if r["items"] and (as_of - r["items"][0]["date"]).days > 365:
            checks.append(f"{r['party']}: advance outstanding over a year - recover, adjust against bills or provide for it")
    for r in debtors:
        if r["max_days_past_due"] > 365:
            checks.append(f"{r['party']}: Rs {inr(r['overdue'])} overdue, oldest {r['max_days_past_due']} days past due - "
                          "consider a provision for doubtful debts (and GST credit note / bad-debt rules)")
    return {"debtors": debtors, "creditors": creditors, "advances_to_suppliers": adv_to_suppliers,
            "advances_from_customers": adv_from_customers, "checks": checks}


def schedule_iii_table(rows: list[dict], buckets, split) -> list[list]:
    """Schedule III ageing: one row per category with a column per bucket."""
    labels = ["Not due"] + [b[0] for b in buckets]
    out = []
    for cat, pred in split:
        sel = [r for r in rows if pred(r)]
        vals = [sum((r["ageing"].get(lab, ZERO) for r in sel), ZERO) for lab in labels]
        if any(vals):
            out.append([cat, *vals, sum(vals, ZERO)])
    return out


def cmd_sync(args):
    books = Books(args.folder)
    path = books.dir / "parties.csv"
    master = load_master(books)
    regs = {}
    for reg in ("sales_register", "purchase_register"):
        for r in books.registers(reg):
            name = (r.get("customer") or r.get("supplier") or "").strip().lower()
            if name and r.get("gstin"):
                regs[name] = r["gstin"].strip().upper()
    added = []
    for acc in sorted(party_accounts(books), key=lambda a: a["account"].lower()):
        if acc["account"].lower() in master or re.search(r"sundry|control", acc["account"], re.I):
            continue
        gstin = regs.get(acc["account"].lower(), "")
        msme = "micro/small (confirm)" if ("msme" in acc["tags"] or acc["line"] == "trade_payables_msme") else ""
        added.append({"party": acc["account"], "account": acc["account"], "type": acc["side"], "gstin": gstin,
                      "pan": gstin[2:12] if gstin else "", "state_code": gstin[:2] if gstin else "",
                      "msme_category": msme, "credit_days": "", "disputed": "N"})
    if added:
        write_rows(path, PARTY_HEADERS, added, append=path.exists() and path.stat().st_size > 0)
    print(f"{len(added)} party row(s) added to {path}" + (": " + ", ".join(a["party"] for a in added) if added else ""))
    print("Fill in credit_days, PAN, Udyam number and contact details - ageing and the 45-day MSME check use them.")


def cmd_report(args):
    books = Books(args.folder)
    as_of = parse_date(args.as_of) if args.as_of else books.fy_end
    r = build(books, as_of)
    args.report_name = "party_balances"

    def flags(x):
        f = (["MSME"] if x["msme"] else []) + (["disputed"] if x["disputed"] else [])
        if x["credit_days"] is None and x.get("ageing"):
            f.append("credit days not set - aged from bill date")
        return ", ".join(f)

    def sheet(rows, kind, advance=False):
        table = []
        total = sum((x["balance"] for x in rows), ZERO)
        if advance:  # advances have no due date: show how long each has been outstanding
            for x in rows:
                table.append([x["party"], x["gstin"], x["balance"], x["oldest"].isoformat() if x["oldest"] else "",
                              x["days_outstanding"] if x["oldest"] else ""])
            heads = ["Party", "GSTIN", f"{kind} balance", "Oldest unadjusted advance", "Days outstanding"]
            if rows:
                table.append(["**Total**", "", total, "", ""])
            return md_table(heads, table, right={2, 4}) if rows else "_Nil_", heads, table
        for x in rows:
            table.append([x["party"], x["gstin"], "-" if x["credit_days"] is None else x["credit_days"], x["balance"],
                          x["ageing"].get("Not due", ZERO), x["overdue"], x["oldest"].isoformat() if x["oldest"] else "",
                          max(x["max_days_past_due"], 0), flags(x)])
        if rows:
            table.append(["**Total**", "", "", total, sum((x["ageing"].get("Not due", ZERO) for x in rows), ZERO),
                          sum((x["overdue"] for x in rows), ZERO), "", "", ""])
        heads = ["Party", "GSTIN", "Credit days", f"{kind} balance", "Not due", "Past due date", "Oldest open bill",
                 "Max days past due", "Flags"]
        return md_table(heads, table, right={3, 4, 5, 7}) if rows else "_Nil_", heads, table

    title = f"# Party balances - {books.company.get('name')} - as at {as_of}"
    md = [title, ""]
    sections = []
    for key, label, kind in (("debtors", "Debtors (trade receivables)", "Receivable"),
                             ("creditors", "Creditors (trade payables)", "Payable"),
                             ("advances_to_suppliers", "Advances to suppliers (shown under loans and advances)", "Advance paid"),
                             ("advances_from_customers", "Advances from customers (shown under other current liabilities)",
                              "Advance received")):
        text, heads, table = sheet(r[key], kind, advance=key.startswith("advances"))
        md += [f"## {label}", "", text, ""]
        sections.append((label.split(" (")[0], heads, table))
    rec = schedule_iii_table(r["debtors"], RECEIVABLE_BUCKETS,
                             [("Undisputed - considered good", lambda x: not x["disputed"]),
                              ("Disputed - considered good", lambda x: x["disputed"])])
    pay = schedule_iii_table(r["creditors"], PAYABLE_BUCKETS,
                             [("MSME", lambda x: x["msme"] and not x["disputed"]),
                              ("Others", lambda x: not x["msme"] and not x["disputed"]),
                              ("Disputed dues - MSME", lambda x: x["msme"] and x["disputed"]),
                              ("Disputed dues - Others", lambda x: not x["msme"] and x["disputed"])])
    rec_heads = ["Particulars", "Not due"] + [b[0] for b in RECEIVABLE_BUCKETS] + ["Total"]
    pay_heads = ["Particulars", "Not due"] + [b[0] for b in PAYABLE_BUCKETS] + ["Total"]
    md += ["## Schedule III ageing - trade receivables (from due date of payment)", "",
           md_table(rec_heads, rec) if rec else "_Nil_", "",
           "## Schedule III ageing - trade payables (from due date of payment)", "",
           md_table(pay_heads, pay) if pay else "_Nil_", "",
           "_Ageing assumes payments clear the oldest bills first (FIFO) and runs from bill date + credit days in "
           "parties.csv. Opening balances are dated 1 April, so their age is a minimum. Mark credit-impaired or doubtful "
           "debts and disputed items by hand if they apply._", "", "## Checks", ""]
    md += [f"- {c}" for c in r["checks"]] or ["- No issues found"]
    open_rows = [[x["party"], i["date"].isoformat(), i["ref"], i["amount"], i["due"].isoformat(), i["days_past_due"]]
                 for key in ("debtors", "creditors", "advances_to_suppliers", "advances_from_customers")
                 for x in r[key] for i in x["items"]]
    emit("\n".join(md), {"as_of": as_of, **{k: [{kk: vv for kk, vv in x.items()} for x in r[k]]
                                             for k in ("debtors", "creditors", "advances_to_suppliers", "advances_from_customers")},
                         "schedule_iii_receivables": rec, "schedule_iii_payables": pay, "checks": r["checks"]}, args)
    if args.out_dir:
        sheets = [(name, [heads] + [[str(c).replace("**", "") if isinstance(c, str) else c for c in row] for row in table])
                  for name, heads, table in sections]
        sheets += [("Ageing - receivables", [rec_heads] + rec), ("Ageing - payables", [pay_heads] + pay),
                   ("Open bills", [["Party", "Date", "Ref", "Amount", "Due date", "Days past due"]] + open_rows)]
        out = Path(args.out_dir) / "party_balances.xlsx"
        if write_xlsx(out, sheets, heading=[books.company.get("name", ""), f"Party balances as at {as_of}"]):
            print(f"\nSaved {out}")


def cmd_confirm(args):
    books = Books(args.folder)
    as_of = parse_date(args.as_of) if args.as_of else books.fy_end
    if not args.out_dir:
        raise BooksError("--out-dir is required for confirmation letters")
    r = build(books, as_of)
    master = load_master(books)
    co = books.company
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    index = []
    groups = [("debtors", "owe us", "receivable from you"), ("creditors", "we owe", "payable to you"),
              ("advances_to_suppliers", "advance paid", "advance paid by us to you"),
              ("advances_from_customers", "advance received", "advance received by us from you")]
    for key, _, phrase in groups:
        for x in r[key]:
            if "(not party-wise)" in x["party"]:
                continue
            if args.party and x["party"].lower() != args.party.lower():
                continue
            m = master.get(x["party"].lower(), {})
            bills = md_table(["Date", "Reference", "Amount (Rs)"],
                             [[i["date"].isoformat(), i["ref"], i["amount"]] for i in x["items"]]) if x["items"] else ""
            letter = [f"**{co.get('name')}**", f"GSTIN: {co.get('gstin') or '-'} | CIN: {co.get('cin') or '-'}", "",
                      f"To: **{x['party']}**" + (f" (GSTIN {m['gstin']})" if m.get("gstin") else ""),
                      m.get("address", ""), "", f"**Subject: Confirmation of balance as at {as_of:%d %B %Y}**", "",
                      "Dear Sir/Madam,", "",
                      f"As per our books of account, a balance of **Rs {inr(x['balance'])}** is {phrase} as at "
                      f"{as_of:%d %B %Y}, made up of the following open items:", "", bills, "",
                      "Please confirm the balance by signing and returning a copy of this letter, or send us your statement "
                      "of account showing the differences, within 15 days. If we do not hear from you, we will take the "
                      "balance as confirmed.", "", f"For {co.get('name')}", "", "Authorised signatory", "", "---", "",
                      f"**Confirmation:** We confirm the balance of Rs {inr(x['balance'])} as at {as_of:%d %B %Y} / "
                      "we do not agree, and our statement is attached.", "", "Signature and seal: ____________________   Date: __________"]
            fname = re.sub(r"[^A-Za-z0-9]+", "_", x["party"]).strip("_") + ".md"
            (out / fname).write_text("\n".join(letter) + "\n", encoding="utf-8")
            index.append([x["party"], key.replace("_", " "), x["balance"], m.get("email", ""), fname])
    if not index:
        raise BooksError("No party with a balance matched" + (f" {args.party!r}" if args.party else ""))
    write_rows(out / "confirmations_index.csv", ["party", "category", "balance", "email", "file"], index)
    print(md_table(["Party", "Category", "Balance", "Email", "Letter"], index))
    print(f"\n{len(index)} letter(s) written to {out} (index: confirmations_index.csv). Send them from your own email; "
          "they are drafts until signed.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync", help="add missing party rows to parties.csv")
    s.add_argument("folder")
    s.set_defaults(func=cmd_sync)
    s = sub.add_parser("report", help="debtors, creditors and advances with ageing")
    s.add_argument("folder")
    s.add_argument("--as-of")
    s.add_argument("--out-dir")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_report)
    s = sub.add_parser("confirm", help="balance-confirmation letters")
    s.add_argument("folder")
    s.add_argument("--party")
    s.add_argument("--as-of")
    s.add_argument("--out-dir")
    s.set_defaults(func=cmd_confirm)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    run_cli(main)
