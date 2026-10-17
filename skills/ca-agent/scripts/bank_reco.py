#!/usr/bin/env python3
"""Bank reconciliation: match a bank statement against the bank ledger and prepare the BRS.

    bank_reco.py <folder> --account "HDFC Bank" --statement stmt.csv [--as-of 2026-03-31] [--days 7]
                 [--suggest bank_entries.json] [--out-dir out/] [--json]

Statement CSV columns (case-insensitive): date, description, ref, withdrawal, deposit, balance
(aliases accepted: debit/credit, withdrawal_amt/deposit_amt, narration, chq_ref_no).
Matching is one-to-one on direction and amount within +/- --days, preferring a cheque/UTR reference
match and then the nearest date. --suggest writes draft vouchers for bank-only items (charges,
interest, unidentified receipts) for review before posting with books.py post.
"""
from __future__ import annotations

import argparse
import re

from common import ZERO, Books, BooksError, dump_json, emit, inr, md_table, money, parse_date, read_rows, run_cli

KEYWORDS = [
    (r"\b(chg|chgs|charges?|fee|sms|amc|commission|gst on)\b", "withdrawal", "bank_charges"),
    (r"\b(int\.?|interest)\b", "deposit", "interest_income"),
    (r"\b(int\.?|interest)\b", "withdrawal", "finance_cost"),
]


def pick(row: dict, *names):
    for n in names:
        if row.get(n) not in (None, ""):
            return row[n]
    return ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--account", required=True)
    ap.add_argument("--statement", required=True)
    ap.add_argument("--as-of")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--suggest")
    ap.add_argument("--out-dir")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    args.report_name = "bank_reconciliation"
    books = Books(args.folder)
    acc = books.account(args.account)

    bank = []
    for r in read_rows(args.statement):
        d = parse_date(pick(r, "date", "txn_date", "transaction_date", "value_date"))
        wd = money(pick(r, "withdrawal", "debit", "withdrawal_amt", "withdrawals", "dr"))
        dep = money(pick(r, "deposit", "credit", "deposit_amt", "deposits", "cr"))
        bank.append({"date": d, "desc": pick(r, "description", "narration", "particulars"), "ref": pick(r, "ref", "chq_ref_no", "cheque_no", "utr"),
                     "amount": dep - wd, "balance": pick(r, "balance", "closing_balance"), "matched": None})
    if not bank:
        raise BooksError("Bank statement has no rows")
    stmt_start = min(b["date"] for b in bank)
    as_of = parse_date(args.as_of) if args.as_of else max(b["date"] for b in bank)
    bank = [b for b in bank if b["date"] <= as_of]

    ledger = [ln for ln in books.journal if ln["account"].lower() == acc["account"].lower() and ln["date"] <= as_of]
    book_balance = sum((ln["debit"] - ln["credit"] for ln in ledger), ZERO)
    candidates = [{"date": ln["date"], "voucher": ln.get("voucher_no"), "narration": ln.get("narration", ""), "ref": ln.get("ref", ""),
                   "amount": ln["debit"] - ln["credit"], "matched": None}
                  for ln in ledger if ln["voucher_type"].lower() != "opening"]

    def ref_hit(b, c):
        ref = re.sub(r"\W", "", str(b["ref"] or "")).lower()
        text = re.sub(r"\W", "", f"{c['ref']} {c['narration']}").lower()
        return bool(ref) and len(ref) >= 4 and ref in text

    for b in sorted(bank, key=lambda x: x["date"]):
        options = [c for c in candidates if c["matched"] is None and c["amount"] == b["amount"]
                   and abs((c["date"] - b["date"]).days) <= args.days]
        if options:
            best = sorted(options, key=lambda c: (not ref_hit(b, c), abs((c["date"] - b["date"]).days)))[0]
            best["matched"], b["matched"] = b, best

    unpresented = [c for c in candidates if c["matched"] is None and c["amount"] < 0]
    uncredited = [c for c in candidates if c["matched"] is None and c["amount"] > 0 and c["date"] >= stmt_start]
    bank_only = [b for b in bank if b["matched"] is None]
    computed_bank = (book_balance - sum((c["amount"] for c in unpresented), ZERO)
                     - sum((c["amount"] for c in uncredited), ZERO) + sum((b["amount"] for b in bank_only), ZERO))
    stmt_closing = None
    last_with_balance = [b for b in bank if b["balance"] not in ("", None)]
    if last_with_balance:
        stmt_closing = money(last_with_balance[-1]["balance"])

    brs = [["Balance as per books (Dr = money in bank)", book_balance],
           ["Add: cheques/payments issued but not yet debited by bank", -sum((c["amount"] for c in unpresented), ZERO)],
           ["Less: deposits recorded in books but not yet credited by bank", -sum((c["amount"] for c in uncredited), ZERO)],
           ["Add: credits in bank not recorded in books", sum((b["amount"] for b in bank_only if b["amount"] > 0), ZERO)],
           ["Less: debits in bank not recorded in books", sum((b["amount"] for b in bank_only if b["amount"] < 0), ZERO)],
           ["**Balance as per bank statement (computed)**", computed_bank]]
    if stmt_closing is not None:
        brs.append(["Balance as per bank statement (actual)", stmt_closing])
        brs.append(["Difference (should be nil)", computed_bank - stmt_closing])

    md = [f"# Bank reconciliation statement - {acc['account']} as at {as_of}", "", md_table(["Particulars", "Rs"], brs), "",
          f"Matched {sum(1 for b in bank if b['matched'])} of {len(bank)} bank lines.", ""]
    if unpresented or uncredited:
        md += ["## Outstanding items in books", "",
               md_table(["Date", "Voucher", "Narration", "Amount"], [[c["date"].isoformat(), c["voucher"], c["narration"][:60], c["amount"]]
                                                                    for c in unpresented + uncredited]), ""]
        stale = [c for c in unpresented if (as_of - c["date"]).days > 90]
        if stale:
            md.append(f"{len(stale)} cheque(s) older than 3 months are stale - reverse them in the books.")
    if bank_only:
        md += ["## In bank, not in books (pass entries)", "",
               md_table(["Date", "Description", "Ref", "Amount"], [[b["date"].isoformat(), b["desc"][:60], b["ref"], b["amount"]] for b in bank_only]), ""]
    if stmt_closing is not None and computed_bank != stmt_closing:
        md.append("**The BRS does not agree with the statement balance - look for duplicated or wrong-amount entries in the books "
                  "or an opening difference from last year's BRS.**")

    if args.suggest and bank_only:
        def find(tag=None, line=None, words=()):
            for a in books.accounts.values():
                if (tag and tag in a["tags"]) or (line and a["line"] == line and any(w in a["account"].lower() for w in words)):
                    return a["account"]
            return None
        suspense = find(tag="suspense") or "Suspense Account"
        vouchers = []
        for b in bank_only:
            direction = "deposit" if b["amount"] > 0 else "withdrawal"
            target = None
            for pattern, side, kind in KEYWORDS:
                if side == direction and re.search(pattern, b["desc"], re.I):
                    target = {"bank_charges": find(line="other_expenses", words=("bank charge",)),
                              "interest_income": find(tag="interest_income"),
                              "finance_cost": find(line="finance_costs", words=("interest",))}[kind]
                    break
            target = target or suspense
            amt = float(abs(b["amount"]))
            lines = ([{"account": acc["account"], "dr": amt}, {"account": target, "cr": amt}] if b["amount"] > 0
                     else [{"account": target, "dr": amt}, {"account": acc["account"], "cr": amt}])
            vouchers.append({"date": b["date"].isoformat(), "type": "Receipt" if b["amount"] > 0 else "Payment",
                             "narration": f"{b['desc']} (from bank statement)"[:120], "ref": b["ref"], "lines": lines})
        dump_json(vouchers, args.suggest)
        md.append(f"\nDraft vouchers for {len(vouchers)} bank-only item(s) written to {args.suggest}. Replace '{suspense}' with the "
                  "right party/expense, then post with books.py post.")
    data = {"account": acc["account"], "as_of": as_of, "book_balance": book_balance, "computed_bank_balance": computed_bank,
            "statement_balance": stmt_closing, "unpresented": unpresented, "uncredited": uncredited,
            "bank_only": [{k: v for k, v in b.items() if k != "matched"} for b in bank_only]}
    for c in data["unpresented"] + data["uncredited"]:
        c.pop("matched", None)
    emit("\n".join(md), data, args)


if __name__ == "__main__":
    run_cli(main)
