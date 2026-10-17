#!/usr/bin/env python3
"""Income-tax computations for companies (ITR-6), individuals (old vs new regime) and ITR form choice.

    income_tax.py company-draft <books-folder> [--depreciation-json dep/depreciation.json] --out tax_input.json
    income_tax.py company <tax_input.json> [--out-dir out/] [--json]
    income_tax.py individual <person.json> [--json]
    income_tax.py itr-form <profile.json>
    income_tax.py advance-tax --tax 250000 --fy 2026-27 [--presumptive]
    income_tax.py tds-rates

company-draft reads the books and pre-fills a computation input (profit, book depreciation, tagged
disallowances, interest income, TDS and advance tax with dates, cash payments over Rs 10,000 for
s.40A(3)) plus a TODO list of items that need judgment. Edit the JSON, then run `company`.
All rates come from rules.py; FY 2025-26 is computed under the Income-tax Act 1961 and FY 2026-27
onwards under the Income-tax Act 2025 (same rate structure, renumbered sections).
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import rules
from common import (ZERO, Books, BooksError, D, dump_json, emit, fy_bounds, inr, load_json, md_table, money,
                    months_between_inclusive, parse_date, round_down_100, round_to_10, rupee, run_cli)

P = lambda x: Decimal(str(x))  # noqa: E731  - rate literal to Decimal


def slab_tax(income: Decimal, slabs) -> Decimal:
    tax, lower = ZERO, ZERO
    for upper, rate in slabs:
        if income <= lower:
            break
        top = income if upper is None else min(income, P(upper))
        tax += (top - lower) * P(rate)
        if upper is None:
            break
        lower = P(upper)
    return tax


def fy_rules(table: dict, fy: str):
    if fy in table:
        return table[fy]
    latest = sorted(table)[-1]
    if fy > latest:
        return table[latest]
    raise BooksError(f"No rates for FY {fy} in rules.py (have {', '.join(sorted(table))})")


# --------------------------------------------------------------------------- interest 234A/B/C

def interest_234c(tax_due: Decimal, payments: list[tuple[date, Decimal]], fy: str, presumptive=False) -> tuple[Decimal, list]:
    if tax_due < rules.ADVANCE_TAX_THRESHOLD:
        return ZERO, []
    start, _ = fy_bounds(fy)
    rows, total = [], ZERO
    for i, (m, d, pct) in enumerate(rules.ADVANCE_TAX_SCHEDULE):
        due = date(start.year + (1 if m < 4 else 0), m, d)
        if presumptive and i < 3:
            continue
        paid = sum((a for dt, a in payments if dt <= due), ZERO)
        required = tax_due * P(pct)
        shortfall = max(ZERO, required - paid)
        if (i == 0 and paid >= tax_due * P(0.12)) or (i == 1 and paid >= tax_due * P(0.36)):
            shortfall = ZERO
        months = 1 if m == 3 else 3
        interest = round_down_100(shortfall) * P(0.01) * months
        rows.append([due.isoformat(), f"{int(pct * 100)}%", money(required), money(paid), money(shortfall), months, money(interest)])
        total += interest
    return money(total), rows


def interest_234b(assessed: Decimal, advance_paid: Decimal, sa: list[tuple[date, Decimal]], fy: str, upto: date) -> Decimal:
    if assessed < rules.ADVANCE_TAX_THRESHOLD or advance_paid >= assessed * P(0.9):
        return ZERO
    _, end = fy_bounds(fy)
    start = end + timedelta(days=1)
    remaining = assessed - advance_paid
    interest = ZERO
    for dt, amt in sorted(sa):
        if dt > upto or remaining <= 0:
            break
        part = min(amt, remaining)
        interest += round_down_100(part) * P(0.01) * months_between_inclusive(start, dt)
        remaining -= part
    if remaining > 0:
        interest += round_down_100(remaining) * P(0.01) * months_between_inclusive(start, upto)
    return money(interest)


def interest_234a(unpaid: Decimal, due: date, filed: date) -> Decimal:
    if filed <= due or unpaid <= 0:
        return ZERO
    return money(round_down_100(unpaid) * P(0.01) * months_between_inclusive(due + timedelta(days=1), filed))


def payments(items) -> list[tuple[date, Decimal]]:
    return [(parse_date(p["date"]), money(p["amount"])) for p in (items or [])]


# --------------------------------------------------------------------------- company

def surcharge_with_relief(base_fn, income: Decimal, bands: list) -> tuple[Decimal, Decimal]:
    """Surcharge by income band with marginal relief at each threshold. base_fn(income) -> tax before surcharge."""
    base = base_fn(income)
    rate, threshold, prev_rate = ZERO, None, ZERO
    for limit, r in bands:
        if income > limit:
            prev_rate, rate, threshold = rate, P(r), P(limit)
    if not rate:
        return ZERO, ZERO
    surcharge = base * rate
    cap = base_fn(threshold) * (1 + prev_rate) + (income - threshold)
    relief = max(ZERO, base + surcharge - cap)
    return money(surcharge), money(relief)


def company_tax(normal: Decimal, special: dict, regime: str, turnover_fy2: Decimal) -> dict:
    c = rules.COMPANY
    if regime in ("115BAA", "115BAB"):
        rate = P(c[regime]["rate"])
    else:
        rate = P(c["normal_rate_small"] if turnover_fy2 <= c["small_turnover_limit"] else c["normal_rate"])
    cg = rules.CG_RATES
    ltcg112a_taxable = max(ZERO, special.get("ltcg_112a", ZERO) - P(cg["ltcg_112a_exemption"]))
    special_tax = (special.get("stcg_111a", ZERO) * P(cg["stcg_111a"]) + ltcg112a_taxable * P(cg["ltcg_112a"])
                   + special.get("ltcg_112", ZERO) * P(cg["ltcg_112"]))
    total_income = normal + sum(special.values(), ZERO)

    def base_fn(income):
        n = max(ZERO, normal - (total_income - income))
        return n * rate + special_tax * (income / total_income if total_income else 0)

    base = normal * rate + special_tax
    if regime in ("115BAA", "115BAB"):
        surcharge, relief = money(base * P(c[regime]["surcharge"])), ZERO
    else:
        surcharge, relief = surcharge_with_relief(base_fn, total_income, c["surcharge_normal"])
    cess = money((base + surcharge - relief) * P(rules.CESS))
    return {"rate": rate, "tax_normal": money(normal * rate), "tax_special": money(special_tax), "base": money(base),
            "surcharge": surcharge, "marginal_relief": relief, "cess": cess,
            "total": rupee(base + surcharge - relief + cess)}


def mat_tax(book_profit: Decimal, fy: str) -> dict:
    rate = P(fy_rules(rules.COMPANY["mat_rate"], fy))
    base_fn = lambda inc: inc * rate  # noqa: E731
    base = book_profit * rate
    surcharge, relief = surcharge_with_relief(base_fn, book_profit, rules.COMPANY["surcharge_normal"])
    cess = money((base + surcharge - relief) * P(rules.CESS))
    return {"rate": rate, "base": money(base), "surcharge": surcharge, "marginal_relief": relief, "cess": cess,
            "total": rupee(base + surcharge - relief + cess)}


def cmd_company(args):
    inp = load_json(args.input)
    fy = inp["fy"]
    regime = inp.get("regime", "115BAA")
    if regime not in {"115BAA", "115BAB", "normal"}:
        raise BooksError("regime must be 115BAA, 115BAB or normal")
    pbt = money(inp.get("profit_before_tax"))
    adds = [(a["item"], money(a["amount"]), a.get("ref", "")) for a in inp.get("add_backs", []) if money(a["amount"])]
    deds = [(a["item"], money(a["amount"]), a.get("ref", "")) for a in inp.get("deductions", []) if money(a["amount"])]
    heads = {k: money(v) for k, v in (inp.get("income_other_heads") or {}).items()}
    special = {k: heads.pop(k) for k in ("stcg_111a", "ltcg_112a", "ltcg_112") if k in heads}
    other_heads_total = sum(heads.values(), ZERO) + sum(special.values(), ZERO)
    business = pbt + sum((a for _, a, _ in adds), ZERO) - sum((d for _, d, _ in deds), ZERO) - other_heads_total
    bf = inp.get("brought_forward") or {}
    bf_loss = min(money(bf.get("business_loss")), max(ZERO, business))
    after_loss = business - bf_loss
    normal_heads = sum(heads.values(), ZERO)
    unabsorbed = min(money(bf.get("unabsorbed_depreciation")), max(ZERO, after_loss + normal_heads))
    gti_normal = after_loss + normal_heads - unabsorbed
    allowed_115baa = {"80JJAA", "80M", "80LA"}
    via = []
    for d in inp.get("chapter_via", []):
        sec = str(d.get("section", d.get("item", ""))).upper().replace(" ", "")
        if regime in ("115BAA", "115BAB") and sec not in allowed_115baa:
            raise BooksError(f"Deduction {sec} is not available under section {regime} (only 80JJAA, 80M, 80LA)")
        via.append((sec, money(d["amount"])))
    via_total = min(sum((a for _, a in via), ZERO), max(ZERO, gti_normal))
    normal_income = max(ZERO, gti_normal - via_total)
    total_income = round_to_10(normal_income + sum(special.values(), ZERO))
    normal_income = total_income - sum(special.values(), ZERO)
    turnover = money(inp.get("turnover_fy_minus_2") or 0)
    tax = company_tax(normal_income, special, regime, turnover)

    mat = None
    mat_credit_created = mat_credit_used = ZERO
    liability = tax["total"]
    notes = []
    if regime == "normal":
        book_profit = pbt + sum((money(a["amount"]) for a in inp.get("mat_adjustments", [])), ZERO)
        mat = mat_tax(book_profit, fy)
        mat["book_profit"] = book_profit
        bf_credit = money(inp.get("mat_credit_bf"))
        if mat["total"] > tax["total"]:
            liability = mat["total"]
            if fy <= "2025-26":
                mat_credit_created = mat["total"] - tax["total"]
            else:
                notes.append("From tax year 2026-27 MAT is a final tax: no MAT credit is created (Finance Act 2026).")
        elif bf_credit:
            if fy <= "2025-26":
                mat_credit_used = min(bf_credit, tax["total"] - mat["total"])
            elif inp.get("mat_credit_usable"):
                mat_credit_used = min(bf_credit, tax["total"] - mat["total"], money(tax["total"] * P(0.25)))
                notes.append("MAT credit set-off capped at 25% of tax (verify eligibility under Finance Act 2026).")
            else:
                notes.append("Brought-forward MAT credit not used: from tax year 2026-27 its use is restricted "
                             "(reportedly only after switching to the concessional regime, capped at 25%). Set "
                             "mat_credit_usable=true after confirming eligibility.")
            liability = tax["total"] - mat_credit_used
    tds = money(inp.get("tds_tcs"))
    adv = payments(inp.get("advance_tax"))
    sa = payments(inp.get("self_assessment_paid"))
    adv_total = sum((a for d, a in adv if d <= fy_bounds(fy)[1]), ZERO)
    tax_due_234 = max(ZERO, liability - tds)
    due = parse_date(inp["due_date"]) if inp.get("due_date") else fy_rules(rules.ITR_DUE_DATES, fy).get(
        "audit_extended", fy_rules(rules.ITR_DUE_DATES, fy)["audit"])
    filed = parse_date(inp["filing_date"]) if inp.get("filing_date") else due
    i234c, c_rows = interest_234c(tax_due_234, adv, fy)
    i234b = interest_234b(tax_due_234, adv_total, sa, fy, filed)
    sa_before_due = sum((a for d, a in sa if d <= due), ZERO)
    i234a = interest_234a(tax_due_234 - adv_total - sa_before_due, due, filed)
    fee = P(rules.LATE_FILING_FEE["default"]) if filed > due else ZERO
    paid = tds + adv_total + sum((a for _, a in sa), ZERO)
    balance = round_to_10(liability + i234a + i234b + i234c + fee - paid)  # s.288B

    lines = [["**Profits and gains of business or profession**", ""], ["Net profit before tax as per P&L", pbt],
             ["Add:", ""]]
    lines += [[f"&nbsp;&nbsp;{i} {('(' + r + ')') if r else ''}", a] for i, a, r in adds]
    lines += [["Less:", ""]] + [[f"&nbsp;&nbsp;{i} {('(' + r + ')') if r else ''}", a] for i, a, r in deds]
    if other_heads_total:
        lines.append(["&nbsp;&nbsp;Income considered under other heads", other_heads_total])
    lines += [["**Business income**", business]]
    if bf_loss:
        lines.append(["Less: brought-forward business loss set off", bf_loss])
    for k, v in heads.items():
        lines.append([f"Income from other sources / {k.replace('_', ' ')}", v])
    for k, v in special.items():
        lines.append([f"Capital gains - {k.replace('_', ' ').upper()} (special rate)", v])
    if unabsorbed:
        lines.append(["Less: unabsorbed depreciation set off", unabsorbed])
    lines += [["**Gross total income**", gti_normal + sum(special.values(), ZERO)]]
    for sec, a in via:
        lines.append([f"Less: deduction u/s {sec}", a])
    lines += [["**Total income (rounded off u/s 288A)**", total_income], ["", ""],
              [f"Tax on normal income @ {tax['rate'] * 100:.0f}%", tax["tax_normal"]]]
    if tax["tax_special"]:
        lines.append(["Tax on special-rate income (111A/112A/112)", tax["tax_special"]])
    lines += [["Surcharge", tax["surcharge"]]]
    if tax["marginal_relief"]:
        lines.append(["Less: marginal relief", tax["marginal_relief"]])
    lines += [["Health and education cess @ 4%", tax["cess"]], [f"**Tax under {'normal provisions' if regime == 'normal' else 's.' + regime}**", tax["total"]]]
    if mat:
        lines += [[f"Book profit for MAT", mat["book_profit"]],
                  [f"MAT @ {mat['rate'] * 100:.0f}% + surcharge + cess", mat["total"]],
                  ["Tax payable: higher of the two", max(tax["total"], mat["total"])]]
        if mat_credit_used:
            lines.append(["Less: MAT credit set off", mat_credit_used])
        if mat_credit_created:
            lines.append(["MAT credit carried forward (15 years)", mat_credit_created])
    lines += [["**Tax liability**", liability], ["Less: TDS / TCS", tds], ["Less: advance tax", adv_total],
              ["Less: self-assessment tax paid", sum((a for _, a in sa), ZERO)],
              ["Add: interest u/s 234A", i234a], ["Add: interest u/s 234B", i234b], ["Add: interest u/s 234C", i234c],
              ["Add: fee u/s 234F", fee],
              [f"**{'Balance tax payable (self-assessment, challan 280)' if balance > 0 else 'Refund due'}**", abs(balance)]]
    fy_start_year = fy_bounds(fy)[0].year
    year_label = f"AY {fy_start_year + 1}-{(fy_start_year + 2) % 100:02d}" if fy <= "2025-26" else f"tax year {fy}, Income-tax Act 2025"
    md = [f"# Computation of total income - {inp.get('name', '')}",
          f"FY {fy} ({year_label}) | "
          f"Status: domestic company | Regime: {regime} | Return: ITR-6 (e-verify with DSC) | Due date {due}", "",
          md_table(["Particulars", "Rs"], lines, right={1}), ""]
    if c_rows:
        md += ["## Interest u/s 234C (deferment of advance tax)", "",
               md_table(["Instalment due", "Cumulative %", "Required", "Paid", "Shortfall", "Months", "Interest"], c_rows), ""]
    md += ["## ITR-6 schedules to fill", "",
           "- Part A-GEN (company details, audit info: Form 3CA-3CD acknowledgement), Part A-BS / A-P&L (from financials.py)",
           "- Schedule BP (business income, add-backs/deductions above), Schedule DOA/DEP (from depreciation.py IT chart)",
           "- Schedule OS / CG for other heads; Schedule CYLA/BFLA/CFL for losses; Schedule VI-A",
           f"- {'Schedule MAT / MATC' if regime == 'normal' else 'Option for s.' + regime + ' (Form 10-IC filed in the first year of option)'}",
           "- Schedule TDS2 / TCS (match with Form 26AS and AIS), Schedule IT (advance and self-assessment challans)",
           "- Schedule SH-1/SH-2 (shareholding), AL-1/AL-2 if unlisted/start-up, Schedule 40/43B and other disclosures"]
    for n in notes:
        md.append(f"\n_{n}_")
    data = {"fy": fy, "regime": regime, "business_income": business, "gross_total_income": gti_normal + sum(special.values(), ZERO),
            "total_income": total_income, "tax": tax, "mat": mat, "mat_credit_created": mat_credit_created,
            "mat_credit_used": mat_credit_used, "liability": liability, "tds_tcs": tds, "advance_tax": adv_total,
            "interest_234a": i234a, "interest_234b": i234b, "interest_234c": i234c, "fee_234f": fee,
            "balance_payable": balance, "due_date": due, "notes": notes}
    args.report_name = "tax_computation"
    emit("\n".join(md), data, args)


def cmd_company_draft(args):
    import financials  # local: only needed here
    books = Books(args.folder)
    closing = books.balances()
    cur = financials.compute(books, closing)
    pl = cur["pl"]

    def total_tag(tag):
        t = ZERO
        for a in books.accounts_with_tag(tag):
            b = closing.get(a["account"], ZERO)
            t += b if financials.LINES[a["line"]][1] in ("expense", "tax", "asset") else -b
        return money(t)

    add_backs = [{"item": "Depreciation as per books", "amount": pl["expenses"]["depreciation"], "ref": "s.32 - tax depreciation deducted below"}]
    for tag, label, ref in (("disallow_37", "Penalties, fines, interest on income tax", "Expl. 1 to s.37(1) / s.40(a)(ii)"),
                            ("csr", "CSR expenditure", "Expl. 2 to s.37(1)"),
                            ("donation", "Donations (claim 80G separately only under the normal regime)", "s.37(1)"),
                            ("provision", "Provisions for unascertained liabilities / doubtful debts", "s.36(1)(vii)/s.37"),
                            ("disallow", "Other disallowable expenses", "review")):
        amt = total_tag(tag)
        if amt:
            add_backs.append({"item": label, "amount": amt, "ref": ref})
    tax_dep = ZERO
    if args.depreciation_json:
        dj = load_json(args.depreciation_json)
        tax_dep = money(dj.get("tax_depreciation"))
    deductions = [{"item": "Depreciation as per Income-tax Act", "amount": tax_dep,
                   "ref": "s.32" + ("" if tax_dep else " - TODO run depreciation.py --json and fill")}]
    other_heads = {}
    interest = total_tag("interest_income")
    dividend = total_tag("dividend_income")
    if interest:
        other_heads["interest"] = interest
    if dividend:
        other_heads["dividend"] = dividend
    gain = total_tag("gain_on_sale")
    if gain:
        deductions.append({"item": "Profit on sale of assets credited to P&L (tax via block / capital gains)", "amount": gain, "ref": "s.50 / s.45"})
    loss = total_tag("loss_on_sale")
    if loss:
        add_backs.append({"item": "Loss on sale of assets debited to P&L", "amount": loss, "ref": "capital in nature"})

    tds = ZERO
    adv = []
    for a in books.accounts_with_tag("tax_asset"):
        if "advance_tax" in a["tags"] or "advance tax" in a["account"].lower():
            for ln in books.journal:
                if ln["account"].lower() == a["account"].lower() and ln["debit"] and ln["voucher_type"].lower() != "opening":
                    adv.append({"date": ln["date"].isoformat(), "amount": float(ln["debit"])})
        elif "self_assessment" not in a["tags"]:
            tds += sum((ln["debit"] - ln["credit"] for ln in books.journal
                        if ln["account"].lower() == a["account"].lower() and ln["voucher_type"].lower() != "opening"), ZERO)

    cash_payments = []
    cash_accs = {a["account"].lower() for a in books.accounts_with_tag("cash")}
    for vno, lines in books.vouchers().items():
        cash_cr = sum((ln["credit"] for ln in lines if ln["account"].lower() in cash_accs), ZERO)
        if cash_cr > 10000:
            others = [ln["account"] for ln in lines if ln["account"].lower() not in cash_accs and ln["debit"]]
            others_lines = [books.accounts.get(o.lower(), {}).get("line") for o in others]
            if any(l in ("cash_equivalents",) for l in others_lines):
                continue  # deposit of cash into bank is not an expense payment
            cash_payments.append({"voucher": vno, "date": lines[0]["date"].isoformat(), "amount": float(cash_cr), "to": ", ".join(others)})

    todo = [
        "Confirm tax depreciation (depreciation.py) and remove book depreciation if already adjusted",
        "s.43B: statutory dues (PF/ESI employer share, bonus, leave encashment, GST, interest to banks) unpaid at year end "
        "and not paid by the ITR due date must be added back",
        "s.43B(h): amounts due to micro/small enterprises outstanding beyond 15/45 days at year end and unpaid by 31 March are disallowed",
        "s.40(a)(ia): 30% of expenses on which TDS was not deducted/deposited by the ITR due date",
        "s.36(1)(va): employees' PF/ESI contribution deposited after the statutory due date is disallowed in full",
        "s.40A(2)(b): excess payments to related parties; s.37: personal or capital expenditure",
        "Income-tax/deferred tax are below PBT - do not add back again",
        "Turnover of FY-2 decides 25% vs 30% under the normal regime",
    ]
    if cash_payments:
        todo.insert(0, f"s.40A(3): {len(cash_payments)} cash payment voucher(s) above Rs 10,000 listed under cash_payments_over_10000 - "
                       "disallow those that are expenses (Rs 35,000 for transporters) unless a rule 6DD exception applies")
    if pl["pbt"] and not books.accounts_with_tag("tax_asset"):
        todo.append("No TDS/advance tax accounts tagged tax_asset - enter tds_tcs and advance_tax manually from Form 26AS/AIS")
    draft = {
        "name": books.company.get("name"), "fy": books.fy, "regime": books.company.get("tax_regime", "115BAA"),
        "turnover_fy_minus_2": books.company.get("turnover_fy_minus_2") or 0,
        "profit_before_tax": pl["pbt"], "add_backs": add_backs, "deductions": deductions,
        "income_other_heads": other_heads, "brought_forward": {"business_loss": 0, "unabsorbed_depreciation": 0},
        "chapter_via": [], "mat_adjustments": [], "mat_credit_bf": 0,
        "tds_tcs": money(tds), "advance_tax": adv, "self_assessment_paid": [],
        "filing_date": None, "cash_payments_over_10000": cash_payments, "todo": todo,
    }
    if draft["regime"] not in {"115BAA", "115BAB", "normal"}:
        draft["regime"] = "115BAA"
    dump_json(draft, args.out)
    print(f"Draft computation input written to {args.out}")
    print(f"Profit before tax {inr(pl['pbt'])}; {len(add_backs)} add-back(s), {len(deductions)} deduction(s) pre-filled.")
    print("Review the 'todo' list in the file, edit amounts, then run: income_tax.py company", args.out)


# --------------------------------------------------------------------------- individuals

def individual_tax(p: dict, regime: str) -> dict:
    fy = p.get("fy", "2025-26")
    r = fy_rules(rules.INDIVIDUAL, fy)[regime]
    age = int(p.get("age", 30))
    resident = p.get("resident", True)
    sal = p.get("salary") or {}
    gross = money(sal.get("gross"))
    salary = ZERO
    if gross:
        salary = gross - P(r["std_deduction"])
        if regime == "old":
            salary -= sum((money(v) for v in (sal.get("exempt_allowances_old") or {}).values()), ZERO)
            salary -= min(money(sal.get("professional_tax")), P(2500))
        salary = max(ZERO, salary)
    hp = ZERO
    for h in p.get("house_property", []):
        if h.get("type") == "self_occupied":
            hp -= ZERO if regime == "new" else min(money(h.get("interest")), P(200000))
        else:
            nav = money(h.get("rent")) - money(h.get("municipal_tax"))
            hp += nav - nav * P(0.30) - money(h.get("interest"))
    hp_setoff = max(hp, P(-200000)) if regime == "old" else max(hp, ZERO)
    business = money(p.get("business_income"))
    os_ = p.get("other_sources") or {}
    fam = money(os_.get("family_pension"))
    fam_ded = min(fam / 3, P(25000 if regime == "new" else 15000))
    other = sum((money(v) for k, v in os_.items() if k != "family_pension"), ZERO) + fam - fam_ded
    cg = {k: money(v) for k, v in (p.get("capital_gains") or {}).items()}
    special = {"stcg_111a": cg.get("stcg_111a", ZERO), "ltcg_112a": cg.get("ltcg_112a", ZERO), "ltcg_112": cg.get("ltcg_112", ZERO)}
    normal_gti = salary + hp_setoff + business + other + cg.get("stcg_other", ZERO)
    ded = ZERO
    if regime == "old":
        d = {k.upper(): money(v) for k, v in (p.get("deductions_old") or {}).items()}
        ded += min(d.get("80C", ZERO), P(150000)) + min(d.get("80CCD1B", ZERO), P(50000)) + d.get("80D", ZERO)
        ded += d.get("80E", ZERO) + d.get("80G", ZERO) + d.get("80EEA", ZERO) + d.get("OTHER", ZERO)
        if age >= 60:
            ded += min(d.get("80TTB", ZERO), P(50000))
        else:
            ded += min(d.get("80TTA", ZERO), P(10000))
    ded += money((p.get("deductions_new") or {}).get("80CCD2", ZERO)) if regime == "new" else money(
        (p.get("deductions_old") or {}).get("80CCD2", ZERO))
    ded = min(ded, max(ZERO, normal_gti))  # Chapter VI-A cannot reduce special-rate capital gains
    normal = max(ZERO, normal_gti - ded)
    total = round_to_10(normal + sum(special.values(), ZERO))
    normal = max(ZERO, total - sum(special.values(), ZERO))
    slabs = r["slabs"] if regime == "new" else r["slabs"]["super_senior" if age >= 80 else "senior" if age >= 60 else "normal"]
    exemption = P(slabs[0][0])
    sp = dict(special)
    if resident and normal < exemption:  # unused basic exemption absorbs special-rate gains
        gap = exemption - normal
        for k in ("stcg_111a", "ltcg_112a", "ltcg_112"):
            use = min(gap, sp[k])
            sp[k] -= use
            gap -= use
    cgr = rules.CG_RATES
    tax_normal = slab_tax(normal, slabs)
    tax_111a = sp["stcg_111a"] * P(cgr["stcg_111a"])
    tax_112a = max(ZERO, sp["ltcg_112a"] - P(cgr["ltcg_112a_exemption"])) * P(cgr["ltcg_112a"])
    tax_112 = sp["ltcg_112"] * P(cgr["ltcg_112"])
    rebate = ZERO
    if resident and total <= P(r["rebate_limit"]):
        eligible = tax_normal if regime == "new" else tax_normal + tax_111a + tax_112
        rebate = min(eligible, P(r["rebate_max"]))
    elif regime == "new" and resident and total > P(r["rebate_limit"]):
        excess = total - P(r["rebate_limit"])
        if tax_normal > excess:
            rebate = tax_normal - excess  # marginal relief on the 12-lakh rebate threshold
    base = tax_normal + tax_111a + tax_112a + tax_112 - rebate
    special_tax = tax_111a + tax_112a + tax_112
    rate = ZERO
    for limit, sr in rules.SURCHARGE_INDIVIDUAL:
        if total > limit:
            rate = P(sr)
    if regime == "new":
        rate = min(rate, P(r["surcharge_cap"]))
    special_rate = min(rate, P(rules.SURCHARGE_SPECIAL_INCOME_CAP))
    surcharge = (base - special_tax) * rate + special_tax * special_rate if rate else ZERO
    relief = ZERO
    if rate:
        threshold = max(P(l) for l, _ in rules.SURCHARGE_INDIVIDUAL if total > l)
        lower_rate = max([P(sr) for l, sr in rules.SURCHARGE_INDIVIDUAL if P(l) < threshold] or [ZERO])
        at_threshold = slab_tax(max(ZERO, threshold - sum(sp.values(), ZERO)), slabs) + special_tax
        cap = at_threshold * (1 + min(lower_rate, rate)) + (total - threshold)
        relief = max(ZERO, base + surcharge - cap)
    cess = (base + surcharge - relief) * P(rules.CESS)
    total_tax = rupee(base + surcharge - relief + cess)
    return {"regime": regime, "salary": salary, "house_property": hp_setoff, "business": business, "other_sources": other,
            "special_income": special, "deductions": ded, "total_income": total, "tax_normal": money(tax_normal),
            "tax_special": money(special_tax), "rebate_87a": money(rebate), "surcharge": money(surcharge),
            "marginal_relief": money(relief), "cess": money(cess), "total_tax": total_tax}


def cmd_individual(args):
    p = load_json(args.input)
    old, new = individual_tax(p, "old"), individual_tax(p, "new")
    tds = money(p.get("tds"))
    adv = sum((a for _, a in payments(p.get("advance_tax"))), ZERO)
    keys = [("Salary (after standard deduction)", "salary"), ("House property", "house_property"), ("Business/profession", "business"),
            ("Other sources", "other_sources"), ("Chapter VI-A deductions", "deductions"), ("Total income", "total_income"),
            ("Tax at slab rates", "tax_normal"), ("Tax on special-rate capital gains", "tax_special"), ("Rebate u/s 87A", "rebate_87a"),
            ("Surcharge", "surcharge"), ("Marginal relief", "marginal_relief"), ("Cess @ 4%", "cess"), ("**Total tax**", "total_tax")]
    rows = [[lab, old[k], new[k]] for lab, k in keys]
    rows.append(["Less: TDS + advance tax", tds + adv, tds + adv])
    rows.append(["**Payable / (refund)**", old["total_tax"] - tds - adv, new["total_tax"] - tds - adv])
    better = "new" if new["total_tax"] <= old["total_tax"] else "old"
    saving = abs(old["total_tax"] - new["total_tax"])
    md = [f"# Income-tax: old vs new regime - {p.get('name', '')} - FY {p.get('fy', '2025-26')}", "",
          md_table(["Particulars", "Old regime", "New regime (default)"], rows, right={1, 2}), "",
          f"**Recommended: {better} regime** (saves Rs {inr(saving)}).",
          "Salaried taxpayers without business income may choose afresh every year in the return. With business income, "
          "opting out of the new regime needs Form 10-IEA before the due date and switching back is allowed only once."]
    args.report_name = "individual_tax"
    emit("\n".join(md), {"old": old, "new": new, "recommended": better, "saving": saving}, args)


# --------------------------------------------------------------------------- ITR form, advance tax, TDS

def cmd_itr_form(args):
    p = load_json(args.input)
    et = (p.get("entity_type") or "individual").lower()
    reasons = []
    ti = money(p.get("total_income"))
    if et in {"company", "opc"}:
        form = "ITR-7" if p.get("claims_section_11") else "ITR-6"
        reasons.append("Companies file ITR-6 (ITR-7 only if claiming exemption u/s 11); must be verified with DSC")
    elif et in {"trust", "political_party", "institution"}:
        form = "ITR-7"
        reasons.append("Trusts/institutions filing u/s 139(4A)-(4D) use ITR-7")
    elif et in {"firm", "llp", "aop", "boi"}:
        if et == "firm" and p.get("presumptive") and ti <= 5000000:
            form = "ITR-4"
            reasons.append("Firm (not LLP) with presumptive income and total income up to Rs 50 lakh")
        else:
            form = "ITR-5"
            reasons.append("Firms, LLPs, AOPs and BOIs file ITR-5")
    else:
        blockers = []
        if not p.get("resident", True) or p.get("rnor"):
            blockers.append("not resident and ordinarily resident")
        if ti > 5000000:
            blockers.append("total income above Rs 50 lakh")
        if p.get("director"):
            blockers.append("director in a company")
        if p.get("unlisted_shares"):
            blockers.append("held unlisted equity shares")
        if p.get("foreign_assets") or p.get("foreign_income"):
            blockers.append("foreign assets/income")
        if money(p.get("agricultural_income")) > 5000:
            blockers.append("agricultural income above Rs 5,000")
        cg = p.get("capital_gains") or {}
        other_cg = any(money(v) for k, v in cg.items() if k != "ltcg_112a")
        if other_cg or money(cg.get("ltcg_112a")) > 125000:
            blockers.append("capital gains beyond LTCG u/s 112A up to Rs 1.25 lakh")
        if p.get("brought_forward_losses") or p.get("esop_tax_deferred"):
            blockers.append("brought-forward losses / deferred ESOP tax")
        if et == "huf":
            blockers.append("HUF (ITR-1 is for individuals only)")
        if p.get("business_income") and not p.get("presumptive"):
            form = "ITR-3"
            reasons.append("Business/profession income computed from books (or partner in a firm)")
        elif p.get("presumptive"):
            if blockers:
                form = "ITR-3"
                reasons.append("Presumptive income, but ITR-4 is barred because: " + "; ".join(blockers))
            else:
                form = "ITR-4"
                reasons.append("Resident with presumptive income u/s 44AD/44ADA/44AE and total income up to Rs 50 lakh")
        elif blockers or int(p.get("house_properties", 0)) > 1 or p.get("lottery_income"):
            form = "ITR-2"
            reasons.append("No business income; ITR-1 not allowed: " + "; ".join(
                blockers + (["more than one house property"] if int(p.get("house_properties", 0)) > 1 else [])
                + (["lottery/racehorse income"] if p.get("lottery_income") else [])))
        else:
            form = "ITR-1"
            reasons.append("Resident individual with salary/pension, one house property, other sources, income up to Rs 50 lakh")
    fy = p.get("fy", "2025-26")
    dd = fy_rules(rules.ITR_DUE_DATES, fy)
    audit = tax_audit_required(p)
    if et in {"company", "opc"} or audit:
        due = dd.get("audit_extended", dd["audit"])
    elif form in {"ITR-3", "ITR-4", "ITR-5"} and (p.get("business_income") or p.get("presumptive")):
        due = dd["non_audit_business"]
    else:
        due = dd["non_audit"]
    md = [f"# ITR form: {form}", "", *[f"- {r}" for r in reasons],
          f"- Tax audit u/s 44AB: {'required - ' + audit if audit else 'not required on the facts given'}",
          f"- Due date for FY {fy}: {due} (belated/revised: {dd['belated']} / {dd['revised']}; late fee u/s 234F up to Rs 5,000)"]
    print("\n".join(md))


def tax_audit_required(p: dict) -> str | None:
    lim = rules.TAX_AUDIT_LIMITS
    turnover = money(p.get("turnover"))
    receipts = money(p.get("gross_receipts_profession"))
    low_cash = p.get("cash_receipts_and_payments_within_5pct")
    if turnover:
        limit = P(lim["business_low_cash"] if low_cash else lim["business"])
        if turnover > limit:
            return f"business turnover {inr(turnover)} exceeds Rs {inr(limit, 0)}"
    if receipts:
        presumptive_ok = p.get("presumptive") and low_cash  # s.44ADA declared at >= 50% of receipts
        limit = P(lim["profession_44ada_low_cash"] if presumptive_ok else lim["profession"])
        if receipts > limit:
            return f"professional receipts {inr(receipts)} exceed Rs {inr(limit, 0)}"
    if p.get("presumptive_opted_out_lower_profit"):
        return "declared profit below presumptive rate while income exceeds the basic exemption (s.44AD(4)/44ADA)"
    return None


def cmd_advance_tax(args):
    tax = money(args.tax)
    start, _ = fy_bounds(args.fy)
    rows, prev = [], ZERO
    for m, d, pct in rules.ADVANCE_TAX_SCHEDULE:
        if args.presumptive and m != 3:
            continue
        due = date(start.year + (1 if m < 4 else 0), m, d)
        cum = rupee(tax * P(pct if not args.presumptive else 1))
        rows.append([due.isoformat(), f"{int((pct if not args.presumptive else 1) * 100)}%", cum, cum - prev])
        prev = cum
    md = [f"# Advance tax schedule - FY {args.fy} on estimated tax (after TDS) of Rs {inr(tax)}", "",
          md_table(["Pay by", "Cumulative", "Cumulative amount", "This instalment"], rows), "",
          f"No advance tax is needed if the net liability is below Rs {inr(rules.ADVANCE_TAX_THRESHOLD, 0)}. "
          "Shortfalls attract interest u/s 234C (1% per month) and u/s 234B if less than 90% is paid by 31 March."]
    print("\n".join(md))


def cmd_tds_rates(args):
    rows = [[t["section"], t["nature"], t["rate"], t["threshold"]] for t in rules.TDS_RATES]
    print(f"# TDS rates for resident payees (rules.py, verified {rules.VERIFIED_ON})\n")
    print(md_table(["Section (1961 Act)", "Nature of payment", "Rate", "Threshold"], rows))
    print("\nUnder the Income-tax Act 2025 (tax year 2026-27 onwards) these are consolidated in section 393 "
          "(salary: s.392). Deposit by the 7th of the next month (30 April for March); quarterly returns "
          "24Q/26Q by 31 Jul, 31 Oct, 31 Jan, 31 May.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("company-draft")
    s.add_argument("folder")
    s.add_argument("--depreciation-json")
    s.add_argument("--out", required=True)
    s.set_defaults(func=cmd_company_draft)
    for name, fn in (("company", cmd_company), ("individual", cmd_individual), ("itr-form", cmd_itr_form)):
        s = sub.add_parser(name)
        s.add_argument("input")
        s.add_argument("--out-dir")
        s.add_argument("--json", action="store_true")
        s.set_defaults(func=fn)
    s = sub.add_parser("advance-tax")
    s.add_argument("--tax", required=True)
    s.add_argument("--fy", required=True)
    s.add_argument("--presumptive", action="store_true")
    s.set_defaults(func=cmd_advance_tax)
    s = sub.add_parser("tds-rates")
    s.set_defaults(func=cmd_tds_rates)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    run_cli(main)
