#!/usr/bin/env python3
"""Statutory compliance calendar for an entity (GST, TDS/TCS, advance tax, ITR, tax audit, ROC/MCA, PF/ESI).

    compliance.py <folder> [--from 2026-10-17] [--days 60] [--lookback 180] [--fy 2026-27] [--ics calendar.ics] [--json]

Uses company.json: entity_type, gst_filing (monthly/qrmp/composition/none), state_code,
tds_applicable (default true), pf_esi_registered, tax_audit (true/false), agm_date, aato_previous_fy.
Without --from it lists the whole financial year (and the year-end filings that fall after it).
With --from it lists what falls due in the --days window and, first, everything that fell due in the
--lookback days before it as "overdue unless done": the books cannot show what was filed, so confirm
each item and give the late position for any that was missed. Events are built for the books' FY, the
FY containing --from, and the year before each, so old books still show current dues.
Statutory dates only: check CBDT/CBIC/MCA for extensions before relying on a date (rules.py records
the extensions known when it was last verified).
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone

import rules
from common import Books, D, emit, fy_bounds, fy_of, md_table, parse_date, run_cli, state_code_of


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


def events_for(books: Books, fy: str) -> list[dict]:
    co = books.company
    start, end = fy_bounds(fy)
    et = co.get("entity_type", "company")
    gst = co.get("gst_filing", "monthly")
    state = state_code_of(co.get("state_code") or co.get("gstin", "")[:2]) if (co.get("state_code") or co.get("gstin")) else ""
    ev = []

    def add(d, area, item, period, note=""):
        ev.append({"date": d, "area": area, "item": item, "period": period, "note": note})

    for i in range(12):
        m = add_months(start, i)
        nxt = add_months(m, 1)
        label = m.strftime("%b %Y")
        q_end = m.month in (6, 9, 12, 3)
        if gst == "monthly":
            add(date(nxt.year, nxt.month, 11), "GST", "GSTR-1", label)
            add(date(nxt.year, nxt.month, 20), "GST", "GSTR-3B + tax payment", label)
        elif gst == "qrmp":
            if q_end:
                add(date(nxt.year, nxt.month, 13), "GST", "GSTR-1 (quarterly)", f"Quarter ending {label}")
                add(date(nxt.year, nxt.month, 22 if state in rules.QRMP_22ND_STATES else 24), "GST", "GSTR-3B (quarterly)", f"Quarter ending {label}")
            else:
                add(date(nxt.year, nxt.month, 13), "GST", "IFF (optional B2B invoices)", label)
                add(date(nxt.year, nxt.month, 25), "GST", "PMT-06 tax payment", label)
        elif gst == "composition" and q_end:
            add(date(nxt.year, nxt.month, 18), "GST", "CMP-08 tax payment", f"Quarter ending {label}")
        if co.get("tds_applicable", True):
            dep = date(nxt.year, 4, 30) if m.month == 3 else date(nxt.year, nxt.month, 7)
            add(dep, "TDS", "Deposit TDS/TCS (challan ITNS 281)", label)
        if co.get("pf_esi_registered"):
            add(date(nxt.year, nxt.month, 15), "Labour", "PF ECR and ESI contribution", label)
    if co.get("tds_applicable", True):
        for q, (mm, dd) in rules.TDS_DUE["return_quarterly"].items():
            yr = start.year + (1 if mm < 4 else 0) + (1 if q == "Q4" else 0)
            add(date(yr, mm, dd), "TDS", "TDS returns 24Q/26Q (and 27EQ for TCS by the 15th)", f"{q} FY {fy}")
        add(date(end.year, 6, 15), "TDS", "Issue Form 16 to employees", f"FY {fy}")
    for mm, dd, pct in rules.ADVANCE_TAX_SCHEDULE:
        add(date(start.year + (1 if mm < 4 else 0), mm, dd), "Income tax", f"Advance tax instalment ({int(pct * 100)}% cumulative)", f"FY {fy}")
    dd = rules.ITR_DUE_DATES.get(fy)
    if dd:
        audit = et in {"company", "opc"} or co.get("tax_audit")
        if co.get("tax_audit"):
            add(dd.get("tax_audit_report_extended", dd["tax_audit_report"]), "Income tax", "Tax audit report (Form 3CA/3CB-3CD)", f"FY {fy}")
        key = "audit_extended" if audit and "audit_extended" in dd else ("audit" if audit else
                                                                           "non_audit_business" if et in {"firm", "llp", "proprietorship"} else "non_audit")
        add(dd[key], "Income tax", f"Income-tax return ({'ITR-6' if et in {'company', 'opc'} else 'ITR-5' if et in {'firm', 'llp'} else 'ITR'})", f"FY {fy}")
    if gst in {"monthly", "qrmp"}:
        aato = D(co.get("aato_previous_fy") or 0)
        note = "mandatory" if aato > rules.GSTR9_MANDATORY_ABOVE else "optional below Rs 2 crore AATO"
        add(date(end.year, 12, 31), "GST", f"GSTR-9 annual return{' + GSTR-9C' if aato > rules.GSTR9C_MANDATORY_ABOVE else ''}", f"FY {fy}", note)
    elif gst == "composition":
        add(date(end.year, 4, 30), "GST", "GSTR-4 annual return", f"FY {fy}")
    if et in {"company", "opc"}:
        agm = parse_date(co["agm_date"]) if co.get("agm_date") else date(end.year, 9, 30)
        add(date(end.year, 9, 30), "ROC", "Hold AGM (within 6 months of year end)", f"FY {fy}")
        add(agm + timedelta(days=rules.ROC["aoc4_days_after_agm"]), "ROC", "AOC-4 (financial statements)", f"FY {fy}",
            "30 days from AGM" + ("" if co.get("agm_date") else " (AGM assumed 30 Sep)"))
        add(agm + timedelta(days=rules.ROC["mgt7_days_after_agm"]), "ROC", "MGT-7/MGT-7A (annual return)", f"FY {fy}", "60 days from AGM")
        add(date(end.year, *rules.ROC["dpt3"]), "ROC", "DPT-3 (return of deposits / exempted loans)", f"as at 31 Mar {end.year}")
        add(date(start.year, 10, 31), "ROC", "MSME-1 (dues to micro/small enterprises > 45 days)", f"Apr-Sep {start.year}", "if applicable")
        add(date(end.year, 4, 30), "ROC", "MSME-1 (dues to micro/small enterprises > 45 days)", f"Oct {start.year}-Mar {end.year}", "if applicable")
        add(date(end.year, *rules.ROC["dir3_kyc"]), "ROC", "DIR-3 KYC for directors due in this cycle", f"FY {fy}", "once every 3 years")
        add(agm + timedelta(days=rules.ROC["adt1_days_after_agm"]), "ROC", "ADT-1 (auditor appointment)", f"FY {fy}", "only in an appointment year")
    if et == "llp":
        add(date(end.year, *rules.ROC["llp_form11"]), "ROC", "LLP Form 11 (annual return)", f"FY {fy}")
        add(date(end.year, *rules.ROC["llp_form8"]), "ROC", "LLP Form 8 (statement of account & solvency)", f"FY {fy}")
    return sorted(ev, key=lambda e: (e["date"], e["area"]))


def write_ics(events: list[dict], path: str, name: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//CA Agent//Compliance Calendar//EN", f"X-WR-CALNAME:{name} compliance"]
    for i, e in enumerate(events):
        d = e["date"].strftime("%Y%m%d")
        summary = f"{e['area']}: {e['item']} ({e['period']})".replace(",", "\\,")
        lines += ["BEGIN:VEVENT", f"UID:ca-agent-{d}-{i}@local", f"DTSTAMP:{stamp}", f"DTSTART;VALUE=DATE:{d}",
                  f"SUMMARY:{summary}", f"DESCRIPTION:{e['note']}".replace(",", "\\,"),
                  "BEGIN:VALARM", "TRIGGER:-P3D", "ACTION:DISPLAY", f"DESCRIPTION:{summary}", "END:VALARM", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    with open(path, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--fy", help="defaults to the books' FY")
    ap.add_argument("--from", dest="from_date", help="list only dates on/after this day")
    ap.add_argument("--days", type=int, default=60, help="window length with --from")
    ap.add_argument("--lookback", type=int, default=180,
                    help="with --from: days before it to list as 'overdue unless done' (default 180)")
    ap.add_argument("--ics", help="also write an .ics calendar file")
    ap.add_argument("--out-dir")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    args.report_name = "compliance_calendar"
    books = Books(args.folder)
    fy = args.fy or books.fy
    events = events_for(books, fy)
    overdue = []
    if args.from_date:
        # Year-end filings of the previous FY (ITR, AOC-4, GSTR-9 ...) fall inside the current FY, and the
        # window may lie in a later FY than the books.
        lo = parse_date(args.from_date)
        fys = set()
        for f in (fy, fy_of(lo)):
            y = int(f[:4])
            fys |= {f, f"{y - 1}-{str(y)[2:]}"}
        events = sorted((e for f in sorted(fys) for e in events_for(books, f)), key=lambda e: e["date"])
        hi = lo + timedelta(days=args.days)
        overdue = dedupe([dict(e, overdue_days=(lo - e["date"]).days) for e in events
                          if lo - timedelta(days=args.lookback) <= e["date"] < lo])
        events = [e for e in events if lo <= e["date"] <= hi]
    unique = dedupe(events)
    rows = [[e["date"].strftime("%d %b %Y (%a)"), e["area"], e["item"], e["period"], e["note"]] for e in unique]
    title = f"Compliance calendar - {books.company.get('name')}"
    title += f" - {args.from_date} + {args.days} days" if args.from_date else f" - FY {fy}"
    head = [f"# {title}", ""]
    if overdue:
        head += [f"## Overdue unless done (due in the {args.lookback} days before {args.from_date})", "",
                 "The books cannot show whether these were filed. Confirm each one; for any missed, give the late "
                 "position (GST: s.50 interest and late fee; TDS: s.234E fee and s.201(1A) interest; ITR: belated "
                 "return, s.234A/234F; ROC: additional fees, and an AGM not held is itself a default).", "",
                 md_table(["Due date", "Days overdue", "Area", "Compliance", "Period", "Note"],
                          [[e["date"].strftime("%d %b %Y"), e["overdue_days"], e["area"], e["item"], e["period"],
                            e["note"]] for e in overdue]), "", "## Coming up", ""]
    md = "\n".join([*head, md_table(["Due date", "Area", "Compliance", "Period", "Note"], rows), "",
                    f"Statutory dates as recorded in rules.py (verified {rules.VERIFIED_ON}); a date falling on a holiday is "
                    "not automatically extended - check notifications for extensions. Professional tax and state labour "
                    "returns vary by state and are not listed."])
    if args.ics:
        write_ics(unique, args.ics, books.company.get("name", "Entity"))
        md += f"\n\nCalendar file written to {args.ics}"
    emit(md, {"events": unique, "overdue_unless_done": overdue}, args)


def dedupe(events: list[dict]) -> list[dict]:
    seen, unique = set(), []
    for e in events:
        k = (e["date"], e["item"], e["period"])
        if k not in seen:
            seen.add(k)
            unique.append(e)
    return unique


if __name__ == "__main__":
    run_cli(main)
