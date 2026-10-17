#!/usr/bin/env python3
"""GST return preparation from the sales and purchase registers of a books folder.

    gst.py check   <folder> --period 2025-04          validate registers (GSTIN, rates, tax maths, duplicates)
    gst.py gstr1   <folder> --period 2025-04          GSTR-1 tables: B2B/SEZ/DE, B2CL, B2CS, EXP, CDNR, CDNUR, NIL, HSN, DOCS
    gst.py gstr3b  <folder> --period 2025-04 [--credit-bf igst=0,cgst=0,sgst=0] [--filing-date 2025-05-25]
                   [--reverse-42-43 cgst=..] [--reverse-other ..] [--reclaim ..]
                                                      GSTR-3B tables 3.1, 3.2, 4, 5, 6.1 with rule 88A set-off,
                                                      interest/late fee, and a books-vs-register cross-check
    gst.py reco    <folder> --period 2025-04 --gstr2b 2b.csv [--tolerance 1]
                                                      purchase register vs GSTR-2B: match, eligible ITC per
                                                      bill, and a bridge from the 2B total to 3B table 4(C)
    gst.py annual  <folder>                           month-wise summary for GSTR-9 / GSTR-9C working

`gst.py <command> --help` describes one command and its options.

Periods: 2025-04 (month), 2025-26:Q1 (quarter, for QRMP), 2025-26 (year), or 2025-04-01..2025-06-30.
Credit notes are entered with positive amounts and doc_type CN; the script applies the sign.
"""
from __future__ import annotations

import argparse
import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import rules
from common import (ZERO, Books, BooksError, D, emit, gstin_problem, inr, md_table, money, parse_date, parse_period,
                    read_rows, rupee, run_cli, state_code_of, write_rows)

HEADS = ("igst", "cgst", "sgst", "cess")
ZERO_RATED = {"EXPWP", "EXPWOP", "SEZWP", "SEZWOP"}
NO_TAX_TYPES = {"EXPWOP", "SEZWOP", "NIL", "EXEMPT", "NONGST", "COMP"}
SALES_TYPES = {"TAX", "EXPWP", "EXPWOP", "SEZWP", "SEZWOP", "DE", "NIL", "EXEMPT", "NONGST"}
PURCHASE_TYPES = {"TAX", "IMPG", "IMPS", "ISD", "NIL", "EXEMPT", "NONGST", "COMP"}


def tax_dict():
    return {h: ZERO for h in HEADS}


BLOCKED = {"blocked", "17_5", "17(5)"}
INELIGIBLE = {"none", "no", "ineligible"}


def itc_bucket(ln: dict) -> tuple[str | None, bool]:
    """GSTR-3B table 4 bucket for a purchase line and whether it is blocked u/s 17(5).
    None = no ITC (exempt/nil/non-GST inward supply or marked ineligible)."""
    if ln["stype"] in {"NIL", "EXEMPT", "COMP", "NONGST"} or ln["itc"] in INELIGIBLE:
        return None, False
    rcm = ln["rcm"] or ln["stype"] == "IMPS"
    if ln["itc"] in {"pos", "16_4", "16(4)"}:
        bucket = "D2"
    elif ln["stype"] == "IMPG":
        bucket = "A1"
    elif ln["stype"] == "IMPS":
        bucket = "A2"
    elif ln["stype"] == "ISD":
        bucket = "A4"
    elif rcm:
        bucket = "A3"
    else:
        bucket = "A5"
    return bucket, ln["itc"] in BLOCKED and bucket != "D2"


def eligible_itc(ln: dict) -> Decimal:
    """Signed tax on a purchase line that reaches 4(C) net ITC (before manual reversals)."""
    bucket, blocked = itc_bucket(ln)
    if bucket is None or bucket == "D2" or blocked:
        return ZERO
    return sum((ln[h] for h in HEADS), ZERO) * ln["sign"]


def parse_heads(spec: str | None) -> dict:
    out = tax_dict()
    for part in (spec or "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            k = k.strip().lower()
            if k not in out:
                raise BooksError(f"Unknown tax head {k!r}; use igst, cgst, sgst, cess")
            out[k] = money(v)
    return out


# --------------------------------------------------------------------------- register loading

def load_register(books: Books, kind: str, start: date, end: date, warnings: list) -> list[dict]:
    company_state = state_code_of(books.company.get("state_code") or books.company.get("gstin", "")[:2])
    rows = []
    for r in books.registers(kind):
        try:
            d = parse_date(r.get("date"))
        except BooksError as exc:
            warnings.append(f"{kind}.csv line {r['_line']}: {exc}")
            continue
        if not start <= d <= end:
            continue
        where = f"{kind}.csv line {r['_line']} ({r.get('invoice_no')})"
        doc = (r.get("doc_type") or "INV").upper()
        if doc not in {"INV", "CN", "DN"}:
            warnings.append(f"{where}: doc_type {doc!r} should be INV, CN or DN")
        stype = (r.get("supply_type") or "TAX").upper()
        valid = SALES_TYPES if kind == "sales_register" else PURCHASE_TYPES
        if stype not in valid:
            raise BooksError(f"{where}: supply_type {stype!r} must be one of {', '.join(sorted(valid))}")
        gstin = (r.get("gstin") or "").strip().upper()
        if gstin and (p := gstin_problem(gstin)):
            warnings.append(f"{where}: GSTIN {gstin} {p}")
        pos = state_code_of(r.get("place_of_supply")) if r.get("place_of_supply") else ""
        if kind == "sales_register":
            if not pos:
                pos = "96" if stype.startswith("EXP") else (gstin[:2] if gstin else company_state)
            inter = stype in ZERO_RATED or pos != company_state
        else:
            pos = pos or company_state
            supplier_state = gstin[:2] if gstin else pos
            inter = stype in {"IMPG", "IMPS"} or supplier_state != pos
        taxable = money(r.get("taxable_value"))
        rate = D(r.get("gst_rate"))
        if rate and float(rate) not in rules.GST_RATES_VALID:
            warnings.append(f"{where}: GST rate {rate}% is not a notified rate")
        if d >= rules.GST2_EFFECTIVE and float(rate) in rules.GST_RATES_LEGACY_AFTER_GST2:
            warnings.append(f"{where}: {rate}% used on {d} - the 12%/28% slabs were largely abolished from "
                            f"{rules.GST2_EFFECTIVE} (GST 2.0); confirm the HSN's current rate")
        given = {h: money(r.get(h)) for h in HEADS}
        expected = tax_dict()
        if stype not in NO_TAX_TYPES:
            t = money(taxable * rate / 100)
            if inter:
                expected["igst"] = t
            else:
                expected["cgst"] = money(t / 2)
                expected["sgst"] = t - expected["cgst"]
        expected["cess"] = given["cess"]
        if any(given[h] for h in ("igst", "cgst", "sgst")):
            tax = given
            for h in ("igst", "cgst", "sgst"):
                if abs(given[h] - expected[h]) > 1:
                    warnings.append(f"{where}: {h.upper()} {inr(given[h])} differs from {inr(expected[h])} "
                                    f"({rate}% on {inr(taxable)}, {'inter' if inter else 'intra'}-state)")
                    break
        else:
            tax = expected
        rows.append({
            "date": d, "inv": (r.get("invoice_no") or "").strip(), "doc": doc, "orig": (r.get("original_invoice_no") or "").strip(),
            "party": r.get("customer") or r.get("supplier") or "", "gstin": gstin, "pos": pos, "stype": stype,
            "hsn": (r.get("hsn") or "").strip(), "desc": r.get("description") or "", "uqc": (r.get("uqc") or "OTH").upper(),
            "qty": D(r.get("qty")), "taxable": taxable, "rate": rate, **tax, "rcm": (r.get("reverse_charge") or "N").upper().startswith("Y"),
            "inter": inter, "sign": -1 if doc == "CN" else 1, "itc": (r.get("itc") or "eligible").lower(),
            "port": r.get("port_code") or "", "sb_no": r.get("shipping_bill_no") or r.get("boe_no") or "",
            "line": r["_line"],
        })
    return rows


def invoices(rows: list[dict]) -> dict:
    """Group register lines into documents keyed by (doc, invoice_no)."""
    out: dict = {}
    for r in rows:
        k = (r["doc"], r["inv"])
        inv = out.setdefault(k, {"date": r["date"], "inv": r["inv"], "doc": r["doc"], "party": r["party"], "gstin": r["gstin"],
                                 "pos": r["pos"], "stype": r["stype"], "rcm": r["rcm"], "inter": r["inter"], "orig": r["orig"],
                                 "lines": [], "taxable": ZERO, **tax_dict(), "port": r["port"], "sb_no": r["sb_no"]})
        inv["lines"].append(r)
        inv["taxable"] += r["taxable"]
        for h in HEADS:
            inv[h] += r[h]
    for inv in out.values():
        inv["value"] = inv["taxable"] + sum(inv[h] for h in HEADS)
    return out


def rate_split(lines: list[dict]) -> list[list]:
    by_rate: dict = defaultdict(lambda: [ZERO, ZERO, ZERO, ZERO, ZERO])
    for ln in lines:
        b = by_rate[ln["rate"]]
        b[0] += ln["taxable"]
        for i, h in enumerate(HEADS, start=1):
            b[i] += ln[h]
    return [[f"{rate}%", *vals] for rate, vals in sorted(by_rate.items())]


def due_date(books: Books, start: date, end: date, form: str) -> date:
    nxt = end + timedelta(days=1)
    filing = books.company.get("gst_filing", "monthly")
    if form == "gstr1":
        return date(nxt.year, nxt.month, rules.GST_DUE_DAY["gstr1_qrmp" if filing == "qrmp" else "gstr1_monthly"])
    if filing == "qrmp":
        state = state_code_of(books.company.get("state_code") or books.company.get("gstin", "")[:2])
        return date(nxt.year, nxt.month, 22 if state in rules.QRMP_22ND_STATES else 24)
    return date(nxt.year, nxt.month, rules.GST_DUE_DAY["gstr3b_monthly"])


# --------------------------------------------------------------------------- GSTR-1

def build_gstr1(books: Books, start: date, end: date, warnings: list) -> dict:
    sales = load_register(books, "sales_register", start, end, warnings)
    docs = invoices(sales)
    b2cl_limit = rules.B2CL_THRESHOLD if start >= date(2024, 8, 1) else 250000
    all_sales = invoices(load_register(books, "sales_register", date(1900, 1, 1), date(2999, 1, 1), []))
    t = {k: [] for k in ("b2b", "b2cl", "exp", "cdnr", "cdnur", "rcm_outward")}
    b2cs: dict = defaultdict(lambda: [ZERO, ZERO, ZERO, ZERO, ZERO])
    nil = {k: [ZERO, ZERO, ZERO] for k in ("inter_reg", "intra_reg", "inter_unreg", "intra_unreg")}
    hsn = {"B2B": defaultdict(lambda: [ZERO, ZERO, ZERO, ZERO, ZERO, ZERO, ""]),
           "B2C": defaultdict(lambda: [ZERO, ZERO, ZERO, ZERO, ZERO, ZERO, ""])}
    for (doc, no), inv in sorted(docs.items(), key=lambda kv: (kv[1]["date"], kv[0][1])):
        st = inv["stype"]
        if st in {"NIL", "EXEMPT", "NONGST"}:
            key = ("inter" if inv["inter"] else "intra") + ("_reg" if inv["gstin"] else "_unreg")
            idx = {"NIL": 0, "EXEMPT": 1, "NONGST": 2}[st]
            nil[key][idx] += inv["taxable"] * inv_sign(doc)
            continue
        for ln in inv["lines"]:
            tab = "B2B" if inv["gstin"] else "B2C"
            h = hsn[tab][(ln["hsn"] or "NA", ln["uqc"], ln["rate"])]
            s = ln["sign"]
            h[0] += ln["qty"] * s
            h[1] += ln["taxable"] * s
            for i, head in enumerate(HEADS, start=2):
                h[i] += ln[head] * s
            h[6] = h[6] or ln["desc"]
        if doc in {"CN", "DN"}:
            if inv["gstin"]:
                t["cdnr"].append(inv)
            else:
                orig = all_sales.get(("INV", inv["orig"]))
                if st in ZERO_RATED or (orig and orig["inter"] and orig["value"] > b2cl_limit and not orig["gstin"]):
                    t["cdnur"].append(inv)
                else:
                    for ln in inv["lines"]:
                        b = b2cs[(inv["pos"], ln["rate"])]
                        b[0] += ln["taxable"] * ln["sign"]
                        for i, head in enumerate(HEADS, start=1):
                            b[i] += ln[head] * ln["sign"]
            continue
        if st.startswith("EXP"):
            t["exp"].append(inv)
        elif inv["gstin"]:
            t["b2b"].append(inv)
            if inv["rcm"]:
                t["rcm_outward"].append(inv)
        elif inv["inter"] and inv["value"] > b2cl_limit:
            t["b2cl"].append(inv)
        else:
            for ln in inv["lines"]:
                b = b2cs[(inv["pos"], ln["rate"])]
                b[0] += ln["taxable"]
                for i, head in enumerate(HEADS, start=1):
                    b[i] += ln[head]
    doc_ranges = []
    for doc, label in (("INV", "Invoices for outward supply"), ("CN", "Credit notes"), ("DN", "Debit notes")):
        nos = sorted({no for (d, no) in docs if d == doc}, key=_natural)
        if nos:
            doc_ranges.append([label, nos[0], nos[-1], len(nos), 0, len(nos)])
    return {"tables": t, "b2cs": b2cs, "nil": nil, "hsn": hsn, "docs": doc_ranges, "b2cl_limit": b2cl_limit,
            "invoices": docs}


def qty_text(q: Decimal) -> str:
    return str(int(q)) if q == q.to_integral_value() else f"{q:.3f}"


def inv_sign(doc):
    return -1 if doc == "CN" else 1


def _natural(s):
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", s)]


def render_gstr1(books, g, label, due) -> tuple[str, dict]:
    t = g["tables"]
    md = [f"# GSTR-1 - {books.company.get('name')} ({books.company.get('gstin')}) - {label}",
          f"Due date: {due} | All amounts in Rs | Credit notes shown as negative where netted", ""]
    data = {"period": label, "due_date": due}

    def inv_rows(invs, extra):
        rows = []
        for inv in invs:
            for rate, txv, ig, cg, sg, ce in rate_split(inv["lines"]):
                rows.append([*extra(inv), rate, txv, ig, cg, sg, ce])
        return rows

    sections = [
        ("4A/4B/6B/6C - B2B, SEZ, deemed exports", t["b2b"],
         ["GSTIN", "Receiver", "Invoice", "Date", "Value", "POS", "RCM", "Type"],
         lambda i: [i["gstin"], i["party"], i["inv"], i["date"].isoformat(), i["value"], i["pos"], "Y" if i["rcm"] else "N",
                    {"SEZWP": "SEZ with payment", "SEZWOP": "SEZ without payment", "DE": "Deemed export"}.get(i["stype"], "Regular")]),
        (f"5 - B2C large (inter-state invoices above Rs {inr(g['b2cl_limit'], 0)})", t["b2cl"],
         ["Invoice", "Date", "Value", "POS"], lambda i: [i["inv"], i["date"].isoformat(), i["value"], i["pos"]]),
        ("6A - Exports", t["exp"], ["Type", "Invoice", "Date", "Value", "Port", "Shipping bill"],
         lambda i: ["WPAY" if i["stype"] == "EXPWP" else "WOPAY", i["inv"], i["date"].isoformat(), i["value"], i["port"], i["sb_no"]]),
        ("9B - Credit/debit notes (registered)", t["cdnr"], ["GSTIN", "Receiver", "Note", "Type", "Date", "Value", "Original invoice"],
         lambda i: [i["gstin"], i["party"], i["inv"], "C" if i["doc"] == "CN" else "D", i["date"].isoformat(), i["value"], i["orig"]]),
        ("9B - Credit/debit notes (unregistered: B2CL / exports)", t["cdnur"], ["Note", "Type", "Date", "Value", "Original invoice"],
         lambda i: [i["inv"], "C" if i["doc"] == "CN" else "D", i["date"].isoformat(), i["value"], i["orig"]]),
    ]
    for title, invs, heads, extra in sections:
        rows = inv_rows(invs, extra)
        data[title] = [dict(zip(heads + ["Rate", "Taxable", "IGST", "CGST", "SGST", "Cess"], r)) for r in rows]
        md += [f"## {title}", "", md_table(heads + ["Rate", "Taxable", "IGST", "CGST", "SGST", "Cess"], rows) if rows else "_Nil_", ""]
    b2cs_rows = [[f"{pos}-{rules.STATE_CODES.get(pos, '')}", f"{rate}%", *vals] for (pos, rate), vals in sorted(g["b2cs"].items())]
    data["7 - B2C others"] = b2cs_rows
    md += ["## 7 - B2C others (net of credit notes)", "",
           md_table(["Place of supply", "Rate", "Taxable", "IGST", "CGST", "SGST", "Cess"], b2cs_rows) if b2cs_rows else "_Nil_", ""]
    nil_rows = [[{"inter_reg": "Inter-state to registered", "intra_reg": "Intra-state to registered",
                  "inter_unreg": "Inter-state to unregistered", "intra_unreg": "Intra-state to unregistered"}[k], *v]
                for k, v in g["nil"].items() if any(v)]
    data["8 - Nil/exempt/non-GST"] = nil_rows
    md += ["## 8 - Nil rated, exempted and non-GST supplies", "",
           md_table(["Description", "Nil rated", "Exempted", "Non-GST"], nil_rows) if nil_rows else "_Nil_", ""]
    for tab in ("B2B", "B2C"):
        rows = [[h, v[6][:40], u, f"{r}%", qty_text(v[0]), v[1], v[2], v[3], v[4], v[5]] for (h, u, r), v in sorted(g["hsn"][tab].items())]
        data[f"12 - HSN summary {tab}"] = rows
        md += [f"## 12 - HSN-wise summary ({tab} tab)", "",
               md_table(["HSN/SAC", "Description", "UQC", "Rate", "Qty", "Taxable", "IGST", "CGST", "SGST", "Cess"], rows, right={4})
               if rows else "_Nil_", ""]
    data["13 - Documents issued"] = g["docs"]
    md += ["## 13 - Documents issued", "",
           md_table(["Nature", "From", "To", "Total", "Cancelled", "Net issued"], g["docs"]) if g["docs"] else "_Nil_", ""]
    if t["rcm_outward"]:
        md += ["_Note: invoices flagged RCM above carry tax payable by the recipient; do not include them in your GSTR-3B "
               "tax liability._", ""]
    return "\n".join(md), data


# --------------------------------------------------------------------------- GSTR-3B

def set_off(liab: dict, credit: dict) -> dict:
    """Utilise ITC per sec 49/49A/49B and rule 88A, minimising cash. Returns usage matrix, cash and balance credit."""
    L, C = dict(liab), dict(credit)
    use = {(c, l): ZERO for c in HEADS for l in HEADS}

    def apply(c, l, cap=None):
        amt = min(C[c], L[l]) if cap is None else min(C[c], L[l], cap)
        if amt > 0:
            use[(c, l)] += amt
            C[c] -= amt
            L[l] -= amt

    apply("igst", "igst")
    need_c, need_s = max(ZERO, L["cgst"] - C["cgst"]), max(ZERO, L["sgst"] - C["sgst"])
    apply("igst", "cgst", need_c)
    apply("igst", "sgst", need_s)
    apply("igst", "cgst")   # rule 88A: IGST credit must be exhausted before CGST/SGST credit is used
    apply("igst", "sgst")
    apply("cgst", "cgst")
    apply("cgst", "igst")
    apply("sgst", "sgst")
    apply("sgst", "igst")
    apply("cess", "cess")
    return {"use": use, "cash": L, "credit_cf": C}


def build_gstr3b(books: Books, start: date, end: date, args, warnings: list) -> dict:
    sales = load_register(books, "sales_register", start, end, warnings)
    purchases = load_register(books, "purchase_register", start, end, warnings)
    t31 = {k: {"taxable": ZERO, **tax_dict()} for k in ("a", "b", "c", "d", "e")}
    t32: dict = defaultdict(lambda: [ZERO, ZERO])
    rcm_outward = ZERO
    for ln in sales:
        s = ln["sign"]
        if ln["rcm"]:
            rcm_outward += ln["taxable"] * s
            continue
        key = {"NIL": "c", "EXEMPT": "c", "NONGST": "e"}.get(ln["stype"], "b" if ln["stype"] in ZERO_RATED else "a")
        t31[key]["taxable"] += ln["taxable"] * s
        if key in ("a", "b"):
            for h in HEADS:
                t31[key][h] += ln[h] * s
        if key == "a" and not ln["gstin"] and ln["inter"]:
            t32[ln["pos"]][0] += ln["taxable"] * s
            t32[ln["pos"]][1] += ln["igst"] * s
    t4 = {k: tax_dict() for k in ("A1", "A2", "A3", "A4", "A5", "B1", "B2", "D1", "D2")}
    t5 = {"exempt_inter": ZERO, "exempt_intra": ZERO, "nongst_inter": ZERO, "nongst_intra": ZERO}
    blocked_rcm = ZERO
    blocked = tax_dict()
    for ln in purchases:
        s = ln["sign"]
        if ln["stype"] in {"NIL", "EXEMPT", "COMP", "NONGST"}:
            k = ("nongst_" if ln["stype"] == "NONGST" else "exempt_") + ("inter" if ln["inter"] else "intra")
            t5[k] += ln["taxable"] * s
            continue
        rcm = ln["rcm"] or ln["stype"] == "IMPS"
        if rcm:
            t31["d"]["taxable"] += ln["taxable"] * s
            for h in HEADS:
                t31["d"][h] += ln[h] * s
        bucket, is_blocked = itc_bucket(ln)
        if bucket is None:
            continue
        if is_blocked and bucket == "A3":
            blocked_rcm += sum(ln[h] for h in HEADS) * s
            continue
        for h in HEADS:
            t4[bucket][h] += ln[h] * s
            if is_blocked:
                t4["B1"][h] += ln[h] * s
                blocked[h] += ln[h] * s
    for h, v in parse_heads(args.reverse_42_43).items():
        t4["B1"][h] += v
    t4["B2"] = parse_heads(args.reverse_other)
    t4["D1"] = parse_heads(args.reclaim)
    t4["A"] = {h: sum(t4[k][h] for k in ("A1", "A2", "A3", "A4", "A5")) for h in HEADS}
    t4["B"] = {h: t4["B1"][h] + t4["B2"][h] for h in HEADS}
    t4["C"] = {h: t4["A"][h] - t4["B"][h] for h in HEADS}

    liab = {h: rupee(t31["a"][h] + t31["b"][h]) for h in HEADS}
    rcm_liab = {h: rupee(t31["d"][h]) for h in HEADS}
    bf = parse_heads(args.credit_bf)
    credit = {h: rupee(t4["C"][h] + bf[h]) for h in HEADS}
    neg = [h for h in HEADS if credit[h] < 0]
    if neg:
        warnings.append(f"Net ITC is negative for {', '.join(neg).upper()} - the reversal exceeds credit; "
                        "the excess is added to cash liability")
        for h in neg:
            liab[h] += -credit[h]
            credit[h] = ZERO
    so = set_off(liab, credit)
    cash = {h: so["cash"][h] + rcm_liab[h] for h in HEADS}

    due = due_date(books, start, end, "gstr3b")
    interest_fc = {h: ZERO for h in HEADS}
    interest_rcm = {h: ZERO for h in HEADS}
    late_fee = {"cgst": ZERO, "sgst": ZERO}
    filing = parse_date(args.filing_date) if args.filing_date else None
    if filing and filing > due:
        days = (filing - due).days
        rate = Decimal(str(rules.GST_INTEREST_LATE_PAYMENT))
        for h in HEADS:  # sec 50(1): interest on the tax paid in cash, for the days of delay
            interest_fc[h] = rupee(so["cash"][h] * rate * days / 365)
            interest_rcm[h] = rupee(rcm_liab[h] * rate * days / 365)
        nil_return = all(v == 0 for v in liab.values()) and all(v == 0 for v in rcm_liab.values()) and not any(t4["A"].values())
        aato = D(books.company.get("aato_previous_fy") or 0)
        per_day = rules.GST_LATE_FEE_PER_DAY_NIL if nil_return else rules.GST_LATE_FEE_PER_DAY
        cap = rules.GST_LATE_FEE_CAP_NIL if nil_return else next(
            c for lim, c in rules.GST_LATE_FEE_CAPS if lim is None or (aato and aato <= lim))
        if not aato and not nil_return:
            warnings.append("aato_previous_fy missing in company.json - late fee capped at the highest slab")
        fee = min(Decimal(days * per_day), Decimal(cap))
        late_fee = {"cgst": fee / 2, "sgst": fee / 2}
    interest = {h: interest_fc[h] + interest_rcm[h] for h in HEADS}
    return {"t31": t31, "t32": t32, "t4": t4, "t5": t5, "liab": liab, "rcm_liab": rcm_liab, "credit_bf": bf,
            "credit": credit, "setoff": so, "cash": cash, "due": due, "filing": filing, "interest": interest,
            "interest_fc": interest_fc, "interest_rcm": interest_rcm,
            "late_fee": late_fee, "rcm_outward": rcm_outward, "blocked_rcm": blocked_rcm, "blocked": blocked,
            "sales": sales, "purchases": purchases}


def books_crosscheck(books: Books, start: date, end: date, g: dict) -> list[str]:
    """Compare GST ledger movements in the journal with the register-based figures."""
    msgs = []

    def posted(tag, side, reversing_type):
        """Tax booked on the accrual side only (output: credits, input: debits), less returns booked through
        credit/debit note vouchers. Monthly set-off and payment entries post to the other side and are ignored."""
        accs = {a["account"].lower() for a in books.accounts_with_tag(tag)}
        if not accs:
            return None
        total = ZERO
        for ln in books.journal:
            if not (start <= ln["date"] <= end) or ln["account"].lower() not in accs or ln["voucher_type"].lower() == "opening":
                continue
            if side == "cr":
                total += ln["credit"] - (ln["debit"] if ln["voucher_type"].lower() == reversing_type else ZERO)
            else:
                total += ln["debit"] - (ln["credit"] if ln["voucher_type"].lower() == reversing_type else ZERO)
        return total

    for h in ("igst", "cgst", "sgst"):
        reg_out = g["t31"]["a"][h] + g["t31"]["b"][h]
        gl_out = posted(f"gst_output_{h}", "cr", "credit note")
        if gl_out is not None and abs(gl_out - reg_out) > 1:
            msgs.append(f"Output {h.upper()}: books show {inr(gl_out)}, sales register gives {inr(reg_out)} "
                        f"(difference {inr(gl_out - reg_out)}) - an invoice/credit note is missing from one side")
        reg_in = g["t4"]["A"][h] - g["blocked"][h]
        gl_in = posted(f"gst_input_{h}", "dr", "debit note")
        if gl_in is not None and abs(gl_in - reg_in) > 1:
            msgs.append(f"Input {h.upper()}: books show {inr(gl_in)}, purchase register gives {inr(reg_in)} eligible ITC "
                        f"(difference {inr(gl_in - reg_in)}) - check unbooked bills, RCM self-invoices or blocked credits")
    return msgs


def render_gstr3b(books, g, label) -> tuple[str, dict]:
    t31, t4 = g["t31"], g["t4"]
    md = [f"# GSTR-3B - {books.company.get('name')} ({books.company.get('gstin')}) - {label}",
          f"Due date: {g['due']}" + (f" | Filing date: {g['filing']}" if g["filing"] else ""), ""]
    rows = [[lab, t31[k]["taxable"], t31[k]["igst"], t31[k]["cgst"], t31[k]["sgst"], t31[k]["cess"]] for k, lab in (
        ("a", "(a) Outward taxable supplies (other than zero rated, nil rated and exempted)"),
        ("b", "(b) Outward taxable supplies (zero rated)"),
        ("c", "(c) Other outward supplies (nil rated, exempted)"),
        ("d", "(d) Inward supplies (liable to reverse charge)"),
        ("e", "(e) Non-GST outward supplies"))]
    md += ["## 3.1 Outward and reverse-charge inward supplies", "",
           md_table(["Nature of supplies", "Taxable value", "IGST", "CGST", "SGST/UTGST", "Cess"], rows), ""]
    if g["rcm_outward"]:
        md += [f"_Outward supplies on which the recipient pays tax (RCM): {inr(g['rcm_outward'])} - reported in GSTR-1 "
               "with the RCM flag, no tax payable by you._", ""]
    r32 = [[f"{pos}-{rules.STATE_CODES.get(pos, '')}", v[0], v[1]] for pos, v in sorted(g["t32"].items())]
    md += ["## 3.2 Inter-state supplies to unregistered persons", "",
           md_table(["Place of supply", "Taxable value", "IGST"], r32) if r32 else "_Nil_", ""]
    labels = [("A1", "(A)(1) Import of goods"), ("A2", "(A)(2) Import of services"),
              ("A3", "(A)(3) Inward supplies liable to reverse charge (other than 1 & 2)"),
              ("A4", "(A)(4) Inward supplies from ISD"), ("A5", "(A)(5) All other ITC"),
              ("B1", "(B)(1) Reversed: rules 38, 42, 43 and section 17(5)"), ("B2", "(B)(2) Reversed: others"),
              ("C", "(C) Net ITC available (A) - (B)"),
              ("D1", "(D)(1) ITC reclaimed (reversed in 4(B)(2) earlier)"),
              ("D2", "(D)(2) Ineligible ITC u/s 16(4) & ITC restricted due to PoS rules")]
    md += ["## 4 Eligible ITC", "",
           md_table(["Details", "IGST", "CGST", "SGST/UTGST", "Cess"], [[lab, *[t4[k][h] for h in HEADS]] for k, lab in labels]), ""]
    if g["blocked_rcm"]:
        md += [f"_RCM tax of {inr(g['blocked_rcm'])} on blocked (sec 17(5)) inward supplies is payable in cash but not claimable._", ""]
    t5 = g["t5"]
    md += ["## 5 Exempt, nil-rated and non-GST inward supplies", "",
           md_table(["Nature", "Inter-state", "Intra-state"],
                    [["From composition supplier, exempt and nil rated", t5["exempt_inter"], t5["exempt_intra"]],
                     ["Non-GST supply", t5["nongst_inter"], t5["nongst_intra"]]]), ""]
    so = g["setoff"]
    pay = []
    for h in HEADS:
        pay.append([f"{h.upper()} - other than reverse charge", g["liab"][h], *[so["use"][(c, h)] for c in HEADS],
                    so["cash"][h], g["interest_fc"][h], g["late_fee"].get(h, ZERO)])
    for h in HEADS:
        if g["rcm_liab"][h]:
            pay.append([f"{h.upper()} - reverse charge", g["rcm_liab"][h], ZERO, ZERO, ZERO, ZERO, g["rcm_liab"][h],
                        g["interest_rcm"][h], ZERO])
    md += ["## 6.1 Payment of tax (ITC utilised per sec 49 / rule 88A to minimise cash)", "",
           f"ITC available = net ITC this period + credit brought forward "
           f"(IGST {inr(g['credit_bf']['igst'])}, CGST {inr(g['credit_bf']['cgst'])}, SGST {inr(g['credit_bf']['sgst'])}). "
           "Reverse-charge tax is always paid in cash.", "",
           md_table(["Tax", "Total payable", "Paid via IGST ITC", "Paid via CGST ITC", "Paid via SGST ITC", "Paid via Cess ITC",
                     "Cash", "Interest", "Late fee"], pay), ""]
    total_cash = sum(g["cash"].values(), ZERO) + sum(g["interest"].values(), ZERO) + sum(g["late_fee"].values(), ZERO)
    md += [f"**Cash to deposit (PMT-06 / electronic cash ledger): Rs {inr(total_cash)}**", "",
           f"Credit carried forward: " + ", ".join(f"{h.upper()} {inr(v)}" for h, v in so["credit_cf"].items()), ""]
    data = {"period": label, "due_date": g["due"], "3.1": t31, "3.2": dict(g["t32"]), "4": t4, "5": t5,
            "liability": g["liab"], "rcm_liability": g["rcm_liab"], "itc_available": g["credit"],
            "setoff": {f"{c}->{l}": v for (c, l), v in so["use"].items() if v}, "cash": g["cash"], "interest": g["interest"],
            "late_fee": g["late_fee"], "total_cash": total_cash, "credit_carried_forward": so["credit_cf"]}
    return "\n".join(md), data


# --------------------------------------------------------------------------- GSTR-2B reconciliation

def norm_inv(s: str) -> str:
    s = re.sub(r"[^A-Z0-9]", "", (s or "").upper())
    return re.sub(r"(?<![0-9])0+(?=[0-9])", "", s)


def reconcile(books: Books, start: date, end: date, path: str, tol: Decimal, warnings: list):
    all_lines = load_register(books, "purchase_register", start, end, warnings)
    purchases = [p for p in all_lines if p["gstin"] and p["stype"] == "TAX" and not p["rcm"]]
    others = [p for p in all_lines if not (p["gstin"] and p["stype"] == "TAX" and not p["rcm"])]
    bk: dict = {}
    for p in purchases:
        k = (p["gstin"], norm_inv(p["inv"]))
        e = bk.setdefault(k, {"gstin": p["gstin"], "party": p["party"], "inv": p["inv"], "date": p["date"], "taxable": ZERO,
                              **tax_dict(), "eligible": ZERO, "itc_flags": set()})
        e["taxable"] += p["taxable"] * p["sign"]
        e["eligible"] += eligible_itc(p)
        if not eligible_itc(p) and sum(p[h] for h in HEADS):
            e["itc_flags"].add({"none": "ineligible", "no": "ineligible"}.get(p["itc"], p["itc"]))
        for h in HEADS:
            e[h] += p[h] * p["sign"]
    tb: dict = {}
    for r in read_rows(path):
        gstin = (r.get("gstin") or r.get("gstin_of_supplier") or "").strip().upper()
        inv = r.get("invoice_no") or r.get("invoice_number") or ""
        if not gstin:
            continue
        k = (gstin, norm_inv(inv))
        e = tb.setdefault(k, {"gstin": gstin, "party": r.get("supplier") or r.get("trade_legal_name") or "", "inv": inv,
                              "date": r.get("invoice_date") or "", "taxable": ZERO, **tax_dict(),
                              "itc_avail": (r.get("itc_availability") or "Yes")})
        sign = -1 if (r.get("doc_type") or r.get("note_type") or "").upper() in {"CN", "C", "CREDIT NOTE"} else 1
        e["taxable"] += money(r.get("taxable_value")) * sign
        portal_names = {"igst": "integrated_tax", "cgst": "central_tax", "sgst": "state_ut_tax", "cess": "cess_tax"}
        for h in HEADS:
            e[h] += money(r.get(h) or r.get(portal_names[h])) * sign
    rows = []
    unmatched_b = {k: v for k, v in bk.items() if k not in tb}
    unmatched_t = {k: v for k, v in tb.items() if k not in bk}
    for k in sorted(set(bk) & set(tb)):
        b, t = bk[k], tb[k]
        diff = {h: b[h] - t[h] for h in HEADS}
        status = "Matched" if all(abs(v) <= tol for v in diff.values()) and abs(b["taxable"] - t["taxable"]) <= tol else "Amount mismatch"
        if (t.get("itc_avail") or "").lower().startswith("n"):
            status = "In 2B but ITC not available"
        rows.append([status, b["gstin"], b["party"], b["inv"], tot(b), b["eligible"], tot(t), tot(b) - tot(t), flags(b)])
    for kb, b in list(unmatched_b.items()):   # probable matches: same supplier, same tax, different invoice number format
        for kt, t in list(unmatched_t.items()):
            if kb[0] == kt[0] and abs(tot(b) - tot(t)) <= tol:
                rows.append(["Probable match (invoice no differs)", b["gstin"], b["party"], f"{b['inv']} / {t['inv']}", tot(b),
                             b["eligible"], tot(t), tot(b) - tot(t), flags(b)])
                unmatched_b.pop(kb)
                unmatched_t.pop(kt)
                break
    for b in unmatched_b.values():
        rows.append(["In books, not in GSTR-2B", b["gstin"], b["party"], b["inv"], tot(b), b["eligible"], ZERO, tot(b), flags(b)])
    for t in unmatched_t.values():
        rows.append(["In GSTR-2B, not in books", t["gstin"], t["party"], t["inv"], ZERO, ZERO, tot(t), -tot(t), ""])
    summary = defaultdict(lambda: [0, ZERO, ZERO, ZERO])
    for r in rows:
        s = summary[r[0]]
        s[0] += 1
        s[1] += r[4]
        s[2] += r[5]
        s[3] += r[6]
    other_itc = sum((eligible_itc(p) for p in others), ZERO)
    rcm_itc = sum((eligible_itc(p) for p in others if p["rcm"] or p["stype"] == "IMPS"), ZERO)
    return rows, summary, bk, tb, {"other_itc": other_itc, "rcm_itc": rcm_itc}


def flags(e: dict) -> str:
    return ", ".join(sorted(e["itc_flags"]))


def reco_bridge(rows: list, summary: dict, extra: dict, net_itc_4c: Decimal) -> tuple[list, str | None]:
    """Walk from ITC per GSTR-2B to 4(C) net ITC as gstr3b computes it from the purchase register."""
    t2b = sum((r[6] for r in rows), ZERO)
    books = sum((r[4] for r in rows), ZERO)
    eligible = sum((r[5] for r in rows), ZERO)
    out = [["ITC as per GSTR-2B (B2B bills)", t2b]]
    for status, v in summary.items():
        if v[1] - v[3]:
            out.append([f"Add/(less): books less 2B on '{status}'", v[1] - v[3]])
    out += [["**Tax on B2B forward-charge bills in the purchase register**", books],
            ["Less: blocked u/s 17(5), ineligible or PoS-restricted on those bills", eligible - books],
            ["Add: ITC on other register lines (RCM incl. import of services, import of goods, ISD, bills without GSTIN)",
             extra["other_itc"]],
            ["**= 4(C) net ITC per gstr3b (before --reverse-42-43 / --reverse-other)**", eligible + extra["other_itc"]]]
    problem = None
    if money(eligible + extra["other_itc"]) != money(net_itc_4c):
        problem = (f"Bridge does not reach gstr3b's 4(C) figure {inr(net_itc_4c)} - difference "
                   f"{inr(eligible + extra['other_itc'] - net_itc_4c)}")
    return out, problem


def tot(e):
    return sum((e[h] for h in HEADS), ZERO)


# --------------------------------------------------------------------------- annual

def annual(books: Books, warnings: list):
    rows = []
    m = books.fy_start
    totals = [ZERO] * 9
    while m <= books.fy_end:
        end = date(m.year + (m.month == 12), m.month % 12 + 1, 1) - timedelta(days=1)

        class A:  # minimal args for build_gstr3b
            reverse_42_43 = reverse_other = reclaim = credit_bf = filing_date = None
        g = build_gstr3b(books, m, end, A, warnings)
        vals = [g["t31"]["a"]["taxable"] + g["t31"]["b"]["taxable"], g["t31"]["a"]["igst"] + g["t31"]["b"]["igst"],
                g["t31"]["a"]["cgst"], g["t31"]["a"]["sgst"], g["t31"]["c"]["taxable"] + g["t31"]["e"]["taxable"],
                g["t31"]["d"]["taxable"], g["t4"]["C"]["igst"], g["t4"]["C"]["cgst"], g["t4"]["C"]["sgst"]]
        totals = [a + b for a, b in zip(totals, vals)]
        rows.append([m.strftime("%b %Y"), *vals])
        m = end + timedelta(days=1)
    rows.append(["**Total**", *totals])
    return rows


# --------------------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.set_defaults(period=None, credit_bf=None, reverse_42_43=None, reverse_other=None, reclaim=None,
                    filing_date=None, gstr2b=None, tolerance="1")
    sub = ap.add_subparsers(dest="command", required=True, metavar="{check,gstr1,gstr3b,reco,annual}")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("folder", help="books folder")
    common.add_argument("--out-dir", help="also write the report (.md, .json; reco also .csv) here")
    common.add_argument("--json", action="store_true", help="print JSON instead of markdown")
    period = argparse.ArgumentParser(add_help=False)
    period.add_argument("--period", required=True, help="2025-04 | 2025-26:Q1 | 2025-26 | 2025-04-01..2025-04-30")
    fmt = argparse.RawDescriptionHelpFormatter
    sub.add_parser("check", parents=[common, period], formatter_class=fmt,
                   help="validate registers: GSTIN, rates, tax maths, invoice numbers, HSN digits, e-invoice",
                   description="Validate the sales and purchase registers for the period: GSTIN format and checksum, "
                               "notified rates (12%%/28%% after GST 2.0), tax maths, invoice-number format and reuse, "
                               "HSN digits by AATO, and e-invoice applicability.")
    sub.add_parser("gstr1", parents=[common, period], formatter_class=fmt, help="GSTR-1 tables",
                   description="GSTR-1 tables from the sales register: B2B/SEZ/deemed exports, B2CL, exports, "
                               "credit/debit notes (registered and unregistered), B2CS, nil/exempt/non-GST, HSN summary "
                               "(B2B and B2C tabs) and documents issued.")
    g3 = sub.add_parser("gstr3b", parents=[common, period], formatter_class=fmt,
                        help="GSTR-3B with rule 88A set-off, interest and late fee",
                        description="GSTR-3B tables 3.1, 3.2, 4, 5 and 6.1 from the registers, ITC set-off per s.49 and "
                                    "rule 88A (minimising cash), cash to deposit, credit carried forward, s.50 interest "
                                    "and late fee with --filing-date, and a books-vs-register cross-check. "
                                    "Reverse-charge tax is always paid in cash.")
    g3.add_argument("--credit-bf", help="ITC brought forward from the electronic credit ledger, e.g. igst=1000,cgst=0,sgst=0")
    g3.add_argument("--reverse-42-43", help="rule 42/43 reversal to add to 4(B)(1), e.g. cgst=120,sgst=120")
    g3.add_argument("--reverse-other", help="4(B)(2) reversals, e.g. rule 37 or ITC not yet in GSTR-2B")
    g3.add_argument("--reclaim", help="4(D)(1) ITC reclaimed")
    g3.add_argument("--filing-date", help="actual/expected filing date, for s.50 interest and the late fee")
    rc = sub.add_parser("reco", parents=[common, period], formatter_class=fmt,
                        help="purchase register vs GSTR-2B, with eligible ITC and a 2B-to-4(C) bridge",
                        description="Match B2B forward-charge bills in the purchase register with GSTR-2B (GSTIN + "
                                    "normalised invoice number; probable matches on equal tax). Each row shows the tax, "
                                    "the eligible ITC (blocked u/s 17(5), ineligible and PoS-restricted bills give nil) "
                                    "and the 2B tax. The bridge walks from ITC per GSTR-2B to the 4(C) net ITC gstr3b "
                                    "will compute; RCM, imports and ISD never appear in 2B and enter the bridge "
                                    "separately. 4(C) takes the register figure, so ITC on bills missing from 2B must be "
                                    "reversed with gstr3b --reverse-other until the supplier files.")
    rc.add_argument("--gstr2b", required=True, help="GSTR-2B B2B data as CSV (see references/gst.md for columns)")
    rc.add_argument("--tolerance", default="1", help="rupee tolerance for a match (default 1)")
    sub.add_parser("annual", parents=[common], formatter_class=fmt, help="month-wise GSTR-9 / 9C working for the FY",
                   description="Month-wise outward supplies, tax, RCM and net ITC for the books' financial year: the "
                               "working for GSTR-9 and GSTR-9C.")
    args = ap.parse_args()
    books = Books(args.folder)
    warnings: list[str] = []
    if args.command != "annual" and not args.period:
        raise BooksError("--period is required")
    if args.command == "annual":
        start, end, label = books.fy_start, books.fy_end, f"FY {books.fy}"
    else:
        start, end, label = parse_period(args.period)

    if args.command == "check":
        args.report_name = "gst_check"
        s = load_register(books, "sales_register", start, end, warnings)
        p = load_register(books, "purchase_register", start, end, warnings)
        seen = {}
        for r in s:
            k = (r["doc"], r["inv"])
            if k in seen and (seen[k]["date"] != r["date"] or seen[k]["gstin"] != r["gstin"]):
                warnings.append(f"sales_register.csv line {r['line']}: {r['doc']} {r['inv']} reused with a different date/party")
            seen.setdefault(k, r)
            if len(r["inv"]) > 16 or not re.fullmatch(r"[A-Za-z0-9/-]+", r["inv"] or "x"):
                warnings.append(f"sales_register.csv line {r['line']}: invoice number {r['inv']!r} must be <=16 chars of letters, digits, / or -")
        aato = D(books.company.get("aato_previous_fy") or 0)
        digits = 6 if aato > rules.HSN_DIGITS[0][0] else 4
        for r in s:
            if r["stype"] not in {"NIL", "EXEMPT", "NONGST"} and len(re.sub(r"\D", "", r["hsn"])) < digits:
                warnings.append(f"sales_register.csv line {r['line']}: HSN {r['hsn']!r} - at least {digits} digits required in GSTR-1")
        if aato > rules.E_INVOICE_THRESHOLD and any(r["gstin"] for r in s):
            warnings.append(f"AATO above Rs {inr(rules.E_INVOICE_THRESHOLD, 0)}: B2B, SEZ and export invoices need an e-invoice IRN")
        md = [f"# GST register check - {label}", f"{len(s)} sales lines, {len(p)} purchase lines", ""]
        md += [f"- {w}" for w in warnings] or ["- No problems found"]
        emit("\n".join(md), {"warnings": warnings}, args)
        return

    if args.command == "gstr1":
        args.report_name = "gstr1"
        g = build_gstr1(books, start, end, warnings)
        md, data = render_gstr1(books, g, label, due_date(books, start, end, "gstr1"))
    elif args.command == "gstr3b":
        args.report_name = "gstr3b"
        g = build_gstr3b(books, start, end, args, warnings)
        md, data = render_gstr3b(books, g, label)
        cross = books_crosscheck(books, start, end, g)
        data["books_crosscheck"] = cross
        md += "\n## Books vs register cross-check\n\n" + ("\n".join(f"- {c}" for c in cross) if cross else
                                                           "- GST ledgers in the journal agree with the registers")
    elif args.command == "reco":
        args.report_name = "gstr2b_reco"
        rows, summary, bk, tb, extra = reconcile(books, start, end, args.gstr2b, D(args.tolerance), warnings)
        no_adj = SimpleNamespace(reverse_42_43=None, reverse_other=None, reclaim=None, credit_bf=None, filing_date=None)
        g3 = build_gstr3b(books, start, end, no_adj, [])
        net_4c = sum(g3["t4"]["C"].values(), ZERO)
        bridge, problem = reco_bridge(rows, summary, extra, net_4c)
        if problem:
            warnings.append(problem)
        books_only = summary.get("In books, not in GSTR-2B", [0, ZERO, ZERO, ZERO])[2]
        heads = ["Status", "GSTIN", "Supplier", "Invoice", "Books tax", "Eligible ITC", "2B tax", "Difference", "ITC flag"]
        md = [f"# Purchase register vs GSTR-2B - {label}", "",
              md_table(["Status", "Count", "Tax as per books", "Eligible ITC (books)", "Tax as per 2B"],
                       [[k, v[0], v[1], v[2], v[3]] for k, v in summary.items()]),
              "", f"ITC per books {inr(sum((tot(e) for e in bk.values()), ZERO))} | ITC per GSTR-2B {inr(sum((tot(e) for e in tb.values()), ZERO))}",
              "", "## Detail", "", md_table(heads, rows), "",
              "_Matching ignores eligibility: a bill blocked u/s 17(5) can be 'Matched' and still give no ITC. "
              "The Eligible ITC column is what reaches 4(C)._", "",
              "## Bridge: GSTR-2B to GSTR-3B table 4(C)", "", md_table(["Particulars", "Rs"], bridge), ""]
        if extra["rcm_itc"]:
            md.append(f"- RCM ITC of {inr(extra['rcm_itc'])} (4(A)(2)/(3)) is not in GSTR-2B: it is self-assessed and "
                      "claimable once the reverse-charge tax is paid in cash.")
        if books_only:
            md.append(f"- {inr(books_only)} of eligible ITC is on bills not yet in GSTR-2B. gstr3b counts it in 4(A)(5); "
                      "to claim only 2B-backed credit (s.16(2)(aa)), rerun gstr3b with --reverse-other for these amounts "
                      "head-wise and reclaim them in 4(D)(1) when the supplier files.")
        md += ["", "Action points: chase suppliers for 'In books, not in GSTR-2B' (ITC cannot be claimed until it appears - "
               "sec 16(2)(aa)); book or reject in IMS the 'In GSTR-2B, not in books' items; correct amount mismatches "
               "with the supplier."]
        md = "\n".join(md)
        keys = ["status", "gstin", "supplier", "invoice", "books_tax", "eligible_itc", "gstr2b_tax", "difference", "itc_flag"]
        data = {"summary": {k: {"count": v[0], "books": v[1], "eligible_itc": v[2], "gstr2b": v[3]} for k, v in summary.items()},
                "detail": [dict(zip(keys, r)) for r in rows],
                "bridge": [{"particulars": l.replace("**", ""), "amount": a} for l, a in bridge],
                "net_itc_4c": net_4c, "rcm_itc": extra["rcm_itc"], "itc_not_in_2b": books_only}
        if args.out_dir:
            Path(args.out_dir).mkdir(parents=True, exist_ok=True)
            write_rows(Path(args.out_dir) / "gstr2b_reco.csv", keys, rows)
    else:
        args.report_name = "gst_annual"
        rows = annual(books, warnings)
        md = "\n".join([f"# GST annual summary (GSTR-9 working) - FY {books.fy}", "",
                        md_table(["Month", "Taxable outward", "IGST", "CGST", "SGST", "Nil/exempt/non-GST", "RCM inward",
                                  "Net ITC IGST", "Net ITC CGST", "Net ITC SGST"], rows), "",
                        f"GSTR-9 is mandatory above AATO Rs {inr(rules.GSTR9_MANDATORY_ABOVE, 0)}; GSTR-9C above "
                        f"Rs {inr(rules.GSTR9C_MANDATORY_ABOVE, 0)}. Due 31 December after the year."])
        data = {"months": rows}
    if warnings:
        md += "\n\n## Warnings\n\n" + "\n".join(f"- {w}" for w in dict.fromkeys(warnings))
        data["warnings"] = list(dict.fromkeys(warnings))
    emit(md, data, args)


if __name__ == "__main__":
    run_cli(main)
