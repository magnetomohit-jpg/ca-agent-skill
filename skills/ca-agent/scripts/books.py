#!/usr/bin/env python3
"""Maintain double-entry books for one entity and one financial year.

    books.py init <folder> --name "X Pvt Ltd" --fy 2025-26 --gstin 27AAAAA0000A1Z5 [--pan --cin]
    books.py add-account <folder> --account "ABC Traders" --line trade_receivables [--tag debtor]
    books.py post <folder> --file vouchers.json [--dry-run]      (JSON list of vouchers, or - for stdin)
    books.py validate <folder>
    books.py tb <folder> [--as-of 2026-03-31] [--csv out.csv]
    books.py ledger <folder> --account "HDFC Bank" [--from 2025-04-01 --to 2025-06-30]
    books.py daybook <folder> [--from --to]
    books.py close-year <folder> <new-folder>

Voucher JSON:
    [{"date": "2025-04-05", "type": "Payment", "narration": "April rent", "ref": "CHQ 1234",
      "lines": [{"account": "Rent", "dr": 50000},
                {"account": "TDS Payable - 194I", "cr": 5000},
                {"account": "HDFC Bank", "cr": 45000}]}]
"""
from __future__ import annotations

import argparse
import re
import shutil
from datetime import timedelta
from pathlib import Path

from common import (COA_HEADERS, JOURNAL_HEADERS, LINES, VOUCHER_TYPES, ZERO, Books, BooksError, D,
                    dump_json, fy_bounds, gstin_problem, inr, load_json, md_table, money, next_fy,
                    pan_problem, parse_date, read_rows, run_cli, write_rows)

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATES = SKILL_DIR / "assets" / "templates"


def drcr(v) -> str:
    v = money(v)
    if v == 0:
        return "0.00"
    return f"{inr(abs(v))} {'Dr' if v > 0 else 'Cr'}"


# --------------------------------------------------------------------------- init / accounts

def cmd_init(args):
    folder = Path(args.folder)
    if (folder / "company.json").exists() and not args.force:
        raise BooksError(f"{folder} already has books. Use --force to overwrite company.json only.")
    fy_start, _ = fy_bounds(args.fy)
    for label, value, check in (("PAN", args.pan, pan_problem), ("GSTIN", args.gstin, gstin_problem)):
        if value and check(value):
            raise BooksError(f"{label} {value}: {check(value)}")
    state = args.state_code or (args.gstin[:2] if args.gstin else "")
    company = {
        "name": args.name,
        "entity_type": args.entity_type,
        "fy": args.fy,
        "pan": (args.pan or (args.gstin[2:12] if args.gstin else "")).upper(),
        "gstin": (args.gstin or "").upper(),
        "cin": args.cin or "",
        "state_code": state,
        "gst_filing": args.gst_filing,
        "tax_regime": args.tax_regime,
        "turnover_fy_minus_2": None,
        "aato_previous_fy": None,
        "accounting_standards": "AS (Schedule III Division I)",
        "books_start": fy_start.isoformat(),
        "notes": "",
    }
    folder.mkdir(parents=True, exist_ok=True)
    dump_json(company, folder / "company.json")
    if not (folder / "chart_of_accounts.csv").exists():
        shutil.copy(SKILL_DIR / "assets" / "chart_of_accounts.csv", folder / "chart_of_accounts.csv")
    if not (folder / "journal.csv").exists():
        write_rows(folder / "journal.csv", JOURNAL_HEADERS, [])
    for tpl in ("sales_register.csv", "purchase_register.csv", "fixed_assets.csv"):
        if not (folder / tpl).exists():
            shutil.copy(TEMPLATES / tpl, folder / tpl)
    print(f"Created books for {args.name} FY {args.fy} in {folder}")
    print("Next: review chart_of_accounts.csv, add party/bank accounts, then post the opening balances "
          "as an 'Opening' voucher dated", fy_start.isoformat())


def cmd_add_account(args):
    books = Books(args.folder)
    if args.line not in LINES:
        raise BooksError(f"Unknown line {args.line!r}. Valid: {', '.join(LINES)}")
    added = []
    for name in args.account:
        if name.lower() in books.accounts:
            print(f"exists: {books.accounts[name.lower()]['account']}")
            continue
        added.append({"code": args.code or "", "account": name, "line": args.line,
                      "tag": args.tag or "", "description": args.description or ""})
    if added:
        write_rows(books.dir / "chart_of_accounts.csv", COA_HEADERS, added, append=True)
        for a in added:
            print(f"added: {a['account']} -> {LINES[args.line][2]}")


# --------------------------------------------------------------------------- posting

def _next_numbers(books: Books) -> dict[str, int]:
    seq: dict[str, int] = {}
    for ln in books.journal:
        m = re.match(r"^([A-Z]+)/[\d-]+/(\d+)$", ln.get("voucher_no") or "")
        if m:
            seq[m.group(1)] = max(seq.get(m.group(1), 0), int(m.group(2)))
    return seq


def check_voucher(books: Books, v: dict, idx: int) -> tuple[list[dict], list[str]]:
    """Validate one voucher dict; return (journal rows without voucher_no, warnings)."""
    where = f"voucher #{idx + 1} ({v.get('narration') or v.get('ref') or v.get('date')})"
    vtype = (v.get("type") or v.get("voucher_type") or "Journal").strip()
    if vtype.lower() not in VOUCHER_TYPES:
        raise BooksError(f"{where}: type {vtype!r} must be one of {', '.join(t.title() for t in VOUCHER_TYPES)}")
    d = parse_date(v.get("date"))
    if not books.fy_start <= d <= books.fy_end:
        raise BooksError(f"{where}: date {d} is outside FY {books.fy} ({books.fy_start} to {books.fy_end}). "
                         "Post it in that year's books folder.")
    lines = v.get("lines") or []
    if len(lines) < 2:
        raise BooksError(f"{where}: needs at least two lines")
    rows, total_dr, total_cr, warnings = [], ZERO, ZERO, []
    for ln in lines:
        acc = books.account(ln.get("account", ""))
        dr, cr = money(ln.get("dr") or ln.get("debit")), money(ln.get("cr") or ln.get("credit"))
        if dr < 0 or cr < 0:
            raise BooksError(f"{where}: negative amount on {acc['account']}; swap Dr/Cr instead")
        if (dr > 0) == (cr > 0):
            raise BooksError(f"{where}: line {acc['account']!r} needs exactly one of dr or cr")
        if vtype.lower() == "opening" and LINES[acc["line"]][0] == "PL":
            raise BooksError(f"{where}: opening balances cannot include P&L account {acc['account']!r}; "
                             "close last year's profit into 'Surplus in Statement of Profit and Loss'")
        total_dr += dr
        total_cr += cr
        rows.append({"date": d, "voucher_type": vtype.title(), "account": acc["account"], "debit": dr,
                     "credit": cr, "narration": ln.get("narration") or v.get("narration", ""),
                     "ref": v.get("ref", "")})
    if total_dr != total_cr:
        raise BooksError(f"{where}: debits {inr(total_dr)} != credits {inr(total_cr)} "
                         f"(difference {inr(total_dr - total_cr)})")
    ref = (v.get("ref") or "").strip()
    if ref:
        for ln in books.journal:
            if (ln.get("ref") or "").strip().lower() == ref.lower() and ln["voucher_type"].lower() == vtype.lower():
                warnings.append(f"{where}: a {vtype} voucher with ref {ref!r} already exists "
                                f"({ln.get('voucher_no')}) - possible duplicate")
                break
    return rows, warnings


def cmd_post(args):
    books = Books(args.folder)
    data = load_json(args.file)
    vouchers = data if isinstance(data, list) else data.get("vouchers", [data])
    seq = _next_numbers(books)
    out_rows, warnings, summary = [], [], []
    for i, v in enumerate(vouchers):
        rows, warns = check_voucher(books, v, i)
        warnings += warns
        prefix = VOUCHER_TYPES[rows[0]["voucher_type"].lower()]
        seq[prefix] = seq.get(prefix, 0) + 1
        vno = v.get("voucher_no") or f"{prefix}/{books.fy}/{seq[prefix]:04d}"
        for r in rows:
            r["voucher_no"] = vno
        out_rows += rows
        summary.append([vno, rows[0]["date"].isoformat(), rows[0]["voucher_type"],
                        sum((r["debit"] for r in rows), ZERO), v.get("narration", "")])
    if warnings and not args.allow_duplicates:
        raise BooksError("Nothing posted:\n  " + "\n  ".join(warnings) +
                         "\nRe-run with --allow-duplicates if these are genuinely new vouchers.")
    if args.dry_run:
        print("DRY RUN - nothing written")
    else:
        write_rows(books.dir / "journal.csv", JOURNAL_HEADERS, out_rows, append=True)
    print(md_table(["Voucher", "Date", "Type", "Amount", "Narration"], summary))
    print(f"\n{len(summary)} voucher(s) {'checked' if args.dry_run else 'posted'}.")
    if not args.dry_run:
        for msg in _cash_warnings(Books(args.folder)):
            print("WARNING:", msg)


# --------------------------------------------------------------------------- checks

def _cash_warnings(books: Books) -> list[str]:
    """Cash-in-hand can never go negative; a negative running balance means a missing receipt or wrong date."""
    msgs = []
    for acc in books.accounts_with_tag("cash"):
        bal, first_neg = ZERO, None
        for ln in sorted((x for x in books.journal if x["account"].lower() == acc["account"].lower()),
                         key=lambda x: (x["date"], x["voucher_type"].lower() != "opening")):
            bal += ln["debit"] - ln["credit"]
            if bal < 0 and first_neg is None:
                first_neg = (ln["date"], bal)
        if first_neg:
            msgs.append(f"{acc['account']} goes negative ({inr(first_neg[1])}) on {first_neg[0]} - "
                        "cash cannot be overdrawn; check for a missing receipt/withdrawal entry")
    return msgs


def cmd_validate(args):
    books = Books(args.folder)
    errors, warnings = [], []
    for vno, lines in books.vouchers().items():
        dr = sum((ln["debit"] for ln in lines), ZERO)
        cr = sum((ln["credit"] for ln in lines), ZERO)
        if dr != cr:
            errors.append(f"{vno}: debits {inr(dr)} != credits {inr(cr)}")
        if len({ln["date"] for ln in lines}) > 1:
            errors.append(f"{vno}: lines carry different dates")
        for ln in lines:
            acc = books.accounts.get(ln["account"].lower())
            if not acc:
                errors.append(f"journal.csv line {ln['_line']}: unknown account {ln['account']!r}")
                continue
            if not books.fy_start <= ln["date"] <= books.fy_end:
                errors.append(f"journal.csv line {ln['_line']}: date {ln['date']} outside FY {books.fy}")
            if ln["voucher_type"].lower() == "opening" and LINES[acc["line"]][0] == "PL":
                errors.append(f"{vno}: opening voucher uses P&L account {acc['account']!r}")
            if ln["debit"] < 0 or ln["credit"] < 0:
                errors.append(f"journal.csv line {ln['_line']}: negative amount")
    warnings += _cash_warnings(books)
    for acc in books.accounts_with_tag("suspense"):
        bal = books.balances().get(acc["account"], ZERO)
        if bal:
            warnings.append(f"Suspense account {acc['account']} has balance {drcr(bal)} - clear it before closing")
    total = books.balances()
    if sum(total.values(), ZERO) != 0:
        errors.append(f"Trial balance does not tally (difference {inr(sum(total.values(), ZERO))})")
    print(f"Checked {len(books.vouchers())} vouchers / {len(books.journal)} lines in {books.dir}")
    for e in errors:
        print("ERROR:", e)
    for w in warnings:
        print("WARNING:", w)
    print("OK - books are internally consistent" if not errors else f"{len(errors)} error(s) found")
    if errors:
        raise SystemExit(1)


# --------------------------------------------------------------------------- reports

def trial_balance(books: Books, as_of=None, start=None):
    start = start or books.fy_start
    end = as_of or books.fy_end
    if start > books.fy_start:
        opening = books.balances(end=start - timedelta(days=1))
    else:
        opening = books.opening_balances()
    period: dict[str, list] = {}
    for ln in books.journal:
        if start <= ln["date"] <= end and not (start == books.fy_start and ln["voucher_type"].lower() == "opening"):
            acc = books.accounts.get(ln["account"].lower())
            key = acc["account"] if acc else ln["account"]
            p = period.setdefault(key, [ZERO, ZERO])
            p[0] += ln["debit"]
            p[1] += ln["credit"]
    rows = []
    order = {k: i for i, k in enumerate(LINES)}
    names = set(opening) | set(period)
    for name in sorted(names, key=lambda n: (order.get(books.accounts.get(n.lower(), {}).get("line"), 99), n.lower())):
        op = opening.get(name, ZERO)
        dr, cr = period.get(name, [ZERO, ZERO])
        close = op + dr - cr
        if op == 0 and dr == 0 and cr == 0:
            continue
        line = books.accounts.get(name.lower(), {}).get("line", "?")
        rows.append({"account": name, "line": line, "opening": op, "debit": dr, "credit": cr, "closing": close})
    return rows


def cmd_tb(args):
    books = Books(args.folder)
    as_of = parse_date(args.as_of) if args.as_of else None
    start = parse_date(getattr(args, "from")) if getattr(args, "from", None) else None
    rows = trial_balance(books, as_of, start)
    tot = {k: sum((r[k] for r in rows), ZERO) for k in ("opening", "debit", "credit", "closing")}
    tot_dr = sum((r["closing"] for r in rows if r["closing"] > 0), ZERO)
    tot_cr = -sum((r["closing"] for r in rows if r["closing"] < 0), ZERO)
    table = [[r["account"], LINES.get(r["line"], ("", "", r["line"]))[2], drcr(r["opening"]), r["debit"], r["credit"],
              inr(r["closing"]) if r["closing"] > 0 else "", inr(-r["closing"]) if r["closing"] < 0 else ""] for r in rows]
    table.append(["**Total**", "", drcr(tot["opening"]), tot["debit"], tot["credit"], f"**{inr(tot_dr)}**", f"**{inr(tot_cr)}**"])
    print(f"## Trial balance - {books.company.get('name')} - as of {as_of or books.fy_end}\n")
    print(md_table(["Account", "Schedule III line", "Opening", "Debit", "Credit", "Closing Dr", "Closing Cr"], table, right={2, 5, 6}))
    print("\nTallied." if tot_dr == tot_cr else f"\nNOT TALLIED - difference {inr(tot_dr - tot_cr)}")
    if args.csv:
        write_rows(args.csv, ["account", "line", "opening", "debit", "credit", "closing"], rows)
        print(f"Saved {args.csv}")


def cmd_ledger(args):
    books = Books(args.folder)
    acc = books.account(args.account)
    start = parse_date(getattr(args, "from")) if getattr(args, "from", None) else books.fy_start
    end = parse_date(args.to) if args.to else books.fy_end
    vouchers = books.vouchers()
    bal = ZERO
    rows = []
    for ln in sorted((x for x in books.journal if x["account"].lower() == acc["account"].lower()),
                     key=lambda x: (x["date"], x["voucher_type"].lower() != "opening", x.get("voucher_no", ""))):
        if ln["date"] < start:
            bal += ln["debit"] - ln["credit"]
            continue
        if ln["date"] > end:
            break
        if not rows and bal:
            rows.append(["", "", "Balance b/f", "", "", "", drcr(bal)])
        bal += ln["debit"] - ln["credit"]
        contra = sorted({x["account"] for x in vouchers.get(ln.get("voucher_no"), []) if x["account"] != ln["account"]})
        rows.append([ln["date"].isoformat(), ln.get("voucher_no", ""), ", ".join(contra)[:60], ln.get("narration", "")[:60],
                     inr(ln["debit"], blank_zero=True), inr(ln["credit"], blank_zero=True), drcr(bal)])
    print(f"## Ledger: {acc['account']} ({start} to {end})\n")
    print(md_table(["Date", "Voucher", "Particulars", "Narration", "Debit", "Credit", "Balance"], rows, right={4, 5, 6}))
    print(f"\nClosing balance: {drcr(bal)}")


def cmd_daybook(args):
    books = Books(args.folder)
    start = parse_date(getattr(args, "from")) if getattr(args, "from", None) else books.fy_start
    end = parse_date(args.to) if args.to else books.fy_end
    rows = []
    for vno, lines in books.vouchers().items():
        d = lines[0]["date"]
        if start <= d <= end:
            for ln in lines:
                rows.append([d.isoformat(), vno, ln["voucher_type"], ln["account"],
                             inr(ln["debit"], blank_zero=True), inr(ln["credit"], blank_zero=True), ln.get("narration", "")[:50]])
    rows.sort(key=lambda r: (r[0], r[1]))
    print(f"## Day book {start} to {end}\n")
    print(md_table(["Date", "Voucher", "Type", "Account", "Debit", "Credit", "Narration"], rows, right={4, 5}))


def cmd_close_year(args):
    """Carry balance-sheet balances into a new books folder for the next FY; P&L closes to retained earnings."""
    books = Books(args.folder)
    errors = [ln for ln in books.journal if ln["account"].lower() not in books.accounts]
    if errors:
        raise BooksError("Fix unknown accounts first (run validate)")
    re_accs = books.accounts_with_tag("retained_earnings")
    if not re_accs:
        raise BooksError("Tag one other_equity account 'retained_earnings' (e.g. Surplus in Statement of Profit and Loss)")
    closing = books.balances()
    profit_dr = ZERO
    lines = []
    for name, bal in sorted(closing.items()):
        if bal == 0:
            continue
        if LINES[books.account(name)["line"]][0] == "PL":
            profit_dr += bal
        else:
            lines.append((name, bal))
    re_name = re_accs[0]["account"]
    merged = {n: b for n, b in lines}
    merged[re_name] = merged.get(re_name, ZERO) + profit_dr
    new_fy = next_fy(books.fy)
    new_start, _ = fy_bounds(new_fy)
    dest = Path(args.new_folder)
    if (dest / "journal.csv").exists() and dest.joinpath("journal.csv").stat().st_size > 80 and not args.force:
        raise BooksError(f"{dest} already has a journal; use --force to overwrite")
    dest.mkdir(parents=True, exist_ok=True)
    company = dict(books.company)
    company["fy"] = new_fy
    company["books_start"] = new_start.isoformat()
    dump_json(company, dest / "company.json")
    shutil.copy(books.dir / "chart_of_accounts.csv", dest / "chart_of_accounts.csv")
    rows = []
    for name, bal in sorted(merged.items()):
        if bal == 0:
            continue
        rows.append({"date": new_start, "voucher_no": f"OPN/{new_fy}/0001", "voucher_type": "Opening", "account": name,
                     "debit": bal if bal > 0 else ZERO, "credit": -bal if bal < 0 else ZERO,
                     "narration": f"Balance brought forward from FY {books.fy}", "ref": ""})
    write_rows(dest / "journal.csv", JOURNAL_HEADERS, rows)
    for tpl in ("sales_register.csv", "purchase_register.csv"):
        shutil.copy(TEMPLATES / tpl, dest / tpl)
    for src, dst in (("fixed_assets_next_year.csv", "fixed_assets.csv"), ("it_blocks_next_year.csv", "it_blocks.csv")):
        if (books.dir / src).exists():
            shutil.copy(books.dir / src, dest / dst)
            print(f"carried forward {src} -> {dst}")
    if not (dest / "fixed_assets.csv").exists():
        shutil.copy(TEMPLATES / "fixed_assets.csv", dest / "fixed_assets.csv")
        print("NOTE: run depreciation.py with --write-next before closing to carry the asset register forward")
    print(f"Opened FY {new_fy} books in {dest}: {len(rows)} opening balances; "
          f"FY {books.fy} {'profit' if profit_dr <= 0 else 'loss'} of {inr(abs(profit_dr))} transferred to {re_name}.")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init")
    s.add_argument("folder")
    s.add_argument("--name", required=True)
    s.add_argument("--fy", required=True, help="e.g. 2025-26")
    s.add_argument("--entity-type", default="company",
                   choices=["company", "opc", "llp", "firm", "proprietorship", "individual", "huf", "trust"])
    s.add_argument("--pan")
    s.add_argument("--gstin")
    s.add_argument("--cin")
    s.add_argument("--state-code")
    s.add_argument("--gst-filing", default="monthly", choices=["monthly", "qrmp", "composition", "none"])
    s.add_argument("--tax-regime", default="115BAA", choices=["115BAA", "115BAB", "normal", "new", "old"])
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("add-account")
    s.add_argument("folder")
    s.add_argument("--account", required=True, action="append", help="repeatable")
    s.add_argument("--line", required=True, help="Schedule III line key, e.g. trade_receivables")
    s.add_argument("--tag", help="semicolon-separated tags, e.g. bank or debtor")
    s.add_argument("--code")
    s.add_argument("--description")
    s.set_defaults(func=cmd_add_account)

    s = sub.add_parser("post")
    s.add_argument("folder")
    s.add_argument("--file", required=True, help="voucher JSON file, or - for stdin")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--allow-duplicates", action="store_true")
    s.set_defaults(func=cmd_post)

    s = sub.add_parser("validate")
    s.add_argument("folder")
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("tb")
    s.add_argument("folder")
    s.add_argument("--as-of")
    s.add_argument("--from")
    s.add_argument("--csv")
    s.set_defaults(func=cmd_tb)

    s = sub.add_parser("ledger")
    s.add_argument("folder")
    s.add_argument("--account", required=True)
    s.add_argument("--from")
    s.add_argument("--to")
    s.set_defaults(func=cmd_ledger)

    s = sub.add_parser("daybook")
    s.add_argument("folder")
    s.add_argument("--from")
    s.add_argument("--to")
    s.set_defaults(func=cmd_daybook)

    s = sub.add_parser("close-year")
    s.add_argument("folder")
    s.add_argument("new_folder")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_close_year)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    run_cli(main)
