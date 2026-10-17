#!/usr/bin/env python3
"""Depreciation under the Companies Act (Schedule II) and the Income-tax Act (WDV blocks).

    depreciation.py <folder> [--method WDV|SLM] [--voucher dep.json] [--write-next] [--out-dir out/] [--json]

Reads <folder>/fixed_assets.csv (asset register) and optional <folder>/it_blocks.csv
(opening tax WDV per block). Produces the asset-wise book schedule, the class-wise PPE note,
the tax depreciation chart by block, the book-vs-tax timing difference for deferred tax, and
(optionally) a depreciation voucher for books.py post and next year's carried-forward registers.

fixed_assets.csv columns:
  asset_id, description, asset_account, acc_dep_account, sch2_category, useful_life_years,
  residual_pct, it_block, put_to_use_date, cost, opening_acc_dep, disposal_date, sale_value,
  additional_dep_eligible
it_blocks.csv columns: block, opening_wdv, additional_dep_bf
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import rules
from common import (ZERO, Books, BooksError, D, dump_json, emit, inr, md_table, money, parse_date, read_rows,
                    run_cli, write_rows)

ASSET_HEADERS = ["asset_id", "description", "asset_account", "acc_dep_account", "sch2_category", "useful_life_years",
                 "residual_pct", "it_block", "put_to_use_date", "cost", "opening_acc_dep", "disposal_date",
                 "sale_value", "additional_dep_eligible"]


def book_depreciation(asset: dict, fy_start: date, fy_end: date, method: str) -> dict:
    cost = money(asset.get("cost"))
    cat = (asset.get("sch2_category") or "").strip().lower()
    intangible = cat.startswith("intangible")
    land = cat in {"land", "freehold_land", "non_depreciable"}
    life = D(asset.get("useful_life_years") or 0)
    if land:
        life = Decimal(1)
    elif not life:
        if intangible:
            raise BooksError(f"Asset {asset.get('asset_id')}: intangible assets need useful_life_years (AS 26)")
        if cat not in rules.SCHEDULE_II_LIFE:
            raise BooksError(f"Asset {asset.get('asset_id')}: unknown sch2_category {cat!r}. "
                             f"Use one of: {', '.join(rules.SCHEDULE_II_LIFE)} or intangible_*")
        life = Decimal(rules.SCHEDULE_II_LIFE[cat])
    residual_pct = D(asset.get("residual_pct")) / 100 if asset.get("residual_pct") not in (None, "") else (
        ZERO if intangible else Decimal(str(rules.RESIDUAL_VALUE_PCT)))
    residual = money(cost * residual_pct)
    put = parse_date(asset["put_to_use_date"])
    disposal = parse_date(asset["disposal_date"]) if asset.get("disposal_date") else None
    opening_acc = money(asset.get("opening_acc_dep"))
    is_addition = put >= fy_start
    if put > fy_end or (disposal and disposal < fy_start):
        return {}
    start = max(put, fy_start)
    end = min(disposal - timedelta(days=1), fy_end) if disposal else fy_end
    days = max(0, (end - start).days + 1)
    year_days = (fy_end - fy_start).days + 1
    depreciable_left = max(ZERO, cost - residual - opening_acc)
    use_slm = method == "SLM" or intangible
    if land:
        dep = ZERO
    elif use_slm:
        dep = (cost - residual) / life * days / year_days
    else:
        rate = Decimal(1) - (residual / cost) ** (Decimal(1) / life) if cost and residual else Decimal(1) / life
        dep = (cost - opening_acc) * rate * days / year_days
    dep = money(min(dep, depreciable_left))
    closing_acc = opening_acc + dep
    result = {"asset_id": asset.get("asset_id"), "description": asset.get("description"),
              "asset_account": asset.get("asset_account") or "", "acc_dep_account": asset.get("acc_dep_account") or
              (f"Accumulated Amortisation - {asset.get('asset_account')}" if intangible else
               f"Accumulated Depreciation - {asset.get('asset_account')}"),
              "intangible": intangible, "land": land, "method": "-" if land else ("SLM" if use_slm else "WDV"),
              "life": "-" if land else life, "cost": cost, "it_block": (asset.get("it_block") or "").strip().lower(),
              "opening_cost": ZERO if is_addition else cost, "addition": cost if is_addition else ZERO,
              "opening_acc": opening_acc, "dep": dep, "days": days, "disposal": disposal,
              "sale_value": money(asset.get("sale_value")), "closing_acc": closing_acc}
    if disposal:
        nbv = cost - closing_acc
        result["gain_loss"] = result["sale_value"] - nbv
        result["closing_cost"], result["closing_acc_after"] = ZERO, ZERO
    else:
        result["gain_loss"] = ZERO
        result["closing_cost"], result["closing_acc_after"] = cost, closing_acc
    return result


def tax_depreciation(assets: list[dict], blocks_rows: list[dict], fy_start: date, fy_end: date, regime: str):
    blocks: dict = defaultdict(lambda: {"opening": ZERO, "add_full": ZERO, "add_half": ZERO, "sales": ZERO,
                                        "addl_bf": ZERO, "addl_full": ZERO, "addl_half": ZERO})
    for b in blocks_rows:
        name = (b.get("block") or "").strip().lower()
        blocks[name]["opening"] += money(b.get("opening_wdv"))
        blocks[name]["addl_bf"] += money(b.get("additional_dep_bf"))
    addl_allowed = regime not in {"115BAA", "115BAB", "new"}
    for a in assets:
        block = (a.get("it_block") or "").strip().lower()
        if block in {"land", "none", "n/a", "-"}:
            continue  # land and other non-depreciable assets are outside the block system
        if not block:
            raise BooksError(f"Asset {a.get('asset_id')}: it_block is required (one of {', '.join(rules.IT_BLOCK_RATES)})")
        if block not in rules.IT_BLOCK_RATES:
            raise BooksError(f"Asset {a.get('asset_id')}: unknown it_block {block!r}")
        put = parse_date(a["put_to_use_date"])
        cost = money(a.get("cost"))
        if fy_start <= put <= fy_end:
            days_used = (fy_end - put).days + 1
            half = days_used < rules.HALF_RATE_DAYS
            blocks[block]["add_half" if half else "add_full"] += cost
            if addl_allowed and (a.get("additional_dep_eligible") or "").upper().startswith("Y"):
                blocks[block]["addl_half" if half else "addl_full"] += cost
        else:
            blocks[block]  # ensure the block appears
        if a.get("disposal_date") and fy_start <= parse_date(a["disposal_date"]) <= fy_end:
            blocks[block]["sales"] += money(a.get("sale_value"))
    rows = []
    for name, b in sorted(blocks.items()):
        rate = Decimal(str(rules.IT_BLOCK_RATES[name]))
        full_base = b["opening"] + b["add_full"]
        sales_left = b["sales"]
        reduce_full = min(sales_left, full_base)
        full_base -= reduce_full
        sales_left -= reduce_full
        half_base = b["add_half"] - min(sales_left, b["add_half"])
        sales_left -= min(sales_left, b["add_half"])
        stcg = sales_left  # sale proceeds exceeding the whole block -> deemed STCG u/s 50
        dep = money(full_base * rate + half_base * rate / 2)
        addl_rate = Decimal(str(rules.ADDITIONAL_DEPRECIATION))
        addl = money(b["addl_bf"] + b["addl_full"] * addl_rate + b["addl_half"] * addl_rate / 2) if addl_allowed else ZERO
        addl_cf = money(b["addl_half"] * addl_rate / 2) if addl_allowed else ZERO
        base = full_base + half_base
        addl = min(addl, max(ZERO, base - dep))
        closing = base - dep - addl
        rows.append({"block": name, "rate": rate, "opening": b["opening"], "add_full": b["add_full"], "add_half": b["add_half"],
                     "sales": b["sales"], "base": base, "dep": dep, "additional": addl, "closing": closing,
                     "stcg_50": stcg, "additional_cf": addl_cf})
    return rows, addl_allowed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--method", choices=["WDV", "SLM"], help="book method (default company.json depreciation_method or WDV)")
    ap.add_argument("--voucher", help="write a depreciation voucher JSON for books.py post")
    ap.add_argument("--write-next", action="store_true", help="write fixed_assets_next_year.csv and it_blocks_next_year.csv")
    ap.add_argument("--out-dir")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    args.report_name = "depreciation"
    books = Books(args.folder)
    method = args.method or books.company.get("depreciation_method", "WDV").upper()
    regime = books.company.get("tax_regime", "115BAA")
    assets = read_rows(books.dir / "fixed_assets.csv")
    blocks_rows = read_rows(books.dir / "it_blocks.csv", required=False)

    sched = [r for r in (book_depreciation(a, books.fy_start, books.fy_end, method) for a in assets) if r]
    tax_rows, addl_allowed = tax_depreciation(assets, blocks_rows, books.fy_start, books.fy_end, regime)

    asset_table = [[r["asset_id"], r["description"], r["method"], r["life"], r["opening_cost"], r["addition"],
                    r["cost"] if r["disposal"] else ZERO, r["opening_acc"], r["dep"], r["closing_cost"] - r["closing_acc_after"],
                    r["gain_loss"] if r["disposal"] else ""] for r in sched]
    classes: dict = defaultdict(lambda: [ZERO] * 8)
    for r in sched:
        c = classes[r["asset_account"] or r["description"]]
        disposed_acc = r["closing_acc"] if r["disposal"] else ZERO
        vals = [r["opening_cost"], r["addition"], r["cost"] if r["disposal"] else ZERO, r["closing_cost"],
                r["opening_acc"], r["dep"], disposed_acc, r["closing_acc_after"]]
        classes[r["asset_account"] or r["description"]] = [a + b for a, b in zip(c, vals)]
    class_table = [[k, *v, v[3] - v[7], v[0] - v[4]] for k, v in sorted(classes.items())]
    tax_table = [[t["block"], f"{t['rate'] * 100:.0f}%", t["opening"], t["add_full"], t["add_half"], t["sales"], t["dep"],
                  t["additional"], t["closing"], t["stcg_50"] if t["stcg_50"] else ""] for t in tax_rows]
    book_dep = sum((r["dep"] for r in sched), ZERO)
    tax_dep = sum((t["dep"] + t["additional"] for t in tax_rows), ZERO)
    book_nbv = sum((r["closing_cost"] - r["closing_acc_after"] for r in sched
                    if not r["land"] and r["it_block"] not in {"land", "none", "n/a", "-"}), ZERO)
    tax_wdv = sum((t["closing"] for t in tax_rows), ZERO)
    timing = book_nbv - tax_wdv
    if regime in {"115BAA", "115BAB"}:
        eff = Decimal(str(rules.COMPANY[regime]["rate"])) * Decimal("1.10") * Decimal(str(1 + rules.CESS))
    else:
        eff = Decimal(str(rules.COMPANY["normal_rate_small"])) * Decimal(str(1 + rules.CESS))
    dt = money(timing * eff)

    md = [f"# Depreciation - {books.company.get('name')} - FY {books.fy}",
          f"Book method: {method} (Companies Act Schedule II; intangibles straight-line over useful life). "
          f"Tax regime: {regime}{'' if addl_allowed else ' - additional depreciation not available'}.", "",
          "## Asset-wise book depreciation", "",
          md_table(["Asset", "Description", "Method", "Life", "Opening cost", "Additions", "Disposals (cost)",
                    "Opening acc. dep.", "Depreciation", "Closing NBV", "Gain/(loss) on sale"], asset_table, right={3}),
          "", "## PPE / intangibles note (gross block, depreciation, net block)", "",
          md_table(["Class", "Gross opening", "Additions", "Disposals", "Gross closing", "Dep. opening", "For the year",
                    "On disposals", "Dep. closing", "Net closing", "Net opening"], class_table),
          "", "## Income-tax depreciation (WDV blocks)", "",
          md_table(["Block", "Rate", "Opening WDV", "Additions >=180 days", "Additions <180 days (half rate)", "Sale proceeds",
                    "Depreciation", "Additional dep.", "Closing WDV", "STCG u/s 50"], tax_table),
          "", "## Summary", "",
          md_table(["Item", "Amount"], [["Depreciation as per books (add back in tax computation)", book_dep],
                                        ["Depreciation as per Income-tax Act (deduct)", tax_dep],
                                        ["Closing net block (books, excluding land)", book_nbv], ["Closing WDV (tax)", tax_wdv],
                                        ["Timing difference (books - tax)", timing],
                                        [f"Deferred tax {'liability' if dt >= 0 else 'asset'} at {money(eff * 100)}%", abs(dt)]]),
          "", "Deferred tax expense for the year = closing deferred tax above less the opening balance in the books "
          "(AS 22). Recognise a deferred tax asset on losses only with virtual certainty."]
    if any(t["stcg_50"] for t in tax_rows):
        md.append("\nSale proceeds exceed a block's WDV: the excess is a short-term capital gain u/s 50.")
    if blocks_rows == [] and any(parse_date(a["put_to_use_date"]) < books.fy_start for a in assets):
        md.append("\nNOTE: it_blocks.csv not found - opening tax WDV assumed nil for assets bought before this year. "
                  "Take opening WDV from last year's ITR depreciation schedule.")

    if args.voucher:
        dep_accs = [a["account"] for a in books.accounts.values() if a["line"] == "depreciation"]
        if not dep_accs:
            raise BooksError("No depreciation expense account in chart_of_accounts.csv")
        by_acc: dict = defaultdict(lambda: ZERO)
        for r in sched:
            if r["dep"]:
                by_acc[r["acc_dep_account"]] += r["dep"]
        for name in by_acc:
            books.account(name)  # fail early with a suggestion if the account is missing
        amort = next((a for a in dep_accs if "amorti" in a.lower()), dep_accs[0])
        dep_acc = next((a for a in dep_accs if "amorti" not in a.lower()), dep_accs[0])
        lines = []
        intangible_total = sum((r["dep"] for r in sched if r["intangible"]), ZERO)
        if book_dep - intangible_total:
            lines.append({"account": dep_acc, "dr": float(book_dep - intangible_total)})
        if intangible_total:
            lines.append({"account": amort, "dr": float(intangible_total)})
        lines += [{"account": k, "cr": float(v)} for k, v in by_acc.items()]
        voucher = [{"date": books.fy_end.isoformat(), "type": "Journal", "ref": f"DEP-{books.fy}",
                    "narration": f"Depreciation for FY {books.fy} as per Schedule II ({method})", "lines": lines}]
        dump_json(voucher, args.voucher)
        md.append(f"\nDepreciation voucher written to {args.voucher} - post with: books.py post {args.folder} --file {args.voucher}")
        disposals = [r for r in sched if r["disposal"]]
        if disposals:
            md.append("Disposals need their own voucher: Dr Bank (sale value) and Dr accumulated depreciation, Cr asset at cost, "
                      "with the balance to Profit/Loss on Sale of Fixed Assets.")

    if args.write_next:
        nxt = []
        for a, r in zip([a for a in assets if book_depreciation(a, books.fy_start, books.fy_end, method)], sched):
            if r["disposal"]:
                continue
            row = {h: a.get(h, "") for h in ASSET_HEADERS}
            row["opening_acc_dep"] = r["closing_acc"]
            nxt.append(row)
        for a in assets:  # assets not yet put to use stay as they are
            if parse_date(a["put_to_use_date"]) > books.fy_end:
                nxt.append({h: a.get(h, "") for h in ASSET_HEADERS})
        write_rows(books.dir / "fixed_assets_next_year.csv", ASSET_HEADERS, nxt)
        write_rows(books.dir / "it_blocks_next_year.csv", ["block", "opening_wdv", "additional_dep_bf"],
                   [{"block": t["block"], "opening_wdv": t["closing"], "additional_dep_bf": t["additional_cf"]} for t in tax_rows])
        md.append("\nWrote fixed_assets_next_year.csv and it_blocks_next_year.csv (books.py close-year carries them forward).")

    data = {"method": method, "assets": sched, "classes": {k: v for k, v in classes.items()}, "tax_blocks": tax_rows,
            "book_depreciation": book_dep, "tax_depreciation": tax_dep, "closing_nbv": book_nbv, "closing_tax_wdv": tax_wdv,
            "timing_difference": timing, "deferred_tax_closing": dt, "deferred_tax_rate": eff}
    emit("\n".join(md), data, args)


if __name__ == "__main__":
    run_cli(main)
