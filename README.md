# CA Agent: a Chartered Accountant skill for Claude

A Claude skill that works like an Indian CA's assistant for companies, LLPs, firms and individuals:

- **Maintains the books:** double-entry vouchers, ledgers, trial balance, day book, bank
  reconciliation, and year-end close and carry-forward.
- **Prepares GST returns:**
  - GSTR-1 tables (B2B/SEZ, B2CL, B2CS, exports, credit/debit notes, HSN B2B/B2C, documents)
  - GSTR-3B with optimal rule 88A ITC set-off, reverse charge, interest and late fee
  - GSTR-2B reconciliation and the GSTR-9 annual working
- **Computes income tax and prepares ITR data:**
  - ITR-6 company computation (115BAA, 115BAB, normal + MAT) with interest u/s 234A/B/C and an
    ITR-6 schedule checklist
  - old vs new regime comparison for individuals
  - ITR form selection, tax-audit check, advance tax and TDS rates
- **Drafts financial statements:**
  - Schedule III (Division I) balance sheet, P&L, cash flow (AS 3) and account-level notes
  - Schedule III ratios with >25% variance flags
  - Excel export and pre-closing checks
- **Party records:** party master (GSTIN, PAN, MSME/Udyam, credit days), debtors and creditors sheets with
  overdue days and Schedule III ageing, party-wise advances (shown under advances in the balance sheet),
  and balance-confirmation letters.
- **Depreciation:** Companies Act Schedule II (WDV/SLM) and Income-tax block WDV (half rate under 180 days),
  plus the deferred tax timing difference.
- **Compliance calendar:** GST, TDS, advance tax, ITR, tax audit, ROC (AOC-4, MGT-7, DPT-3, MSME-1,
  DIR-3 KYC), with `.ics` export.

The skill carries the professional knowledge (Schedule III, GST 2.0, Income-tax Act 1961 → 2025
transition, Finance Act 2026, CARO, ROC) and a set of dependency-free Python scripts that do the
arithmetic deterministically. Claude does the judgment work: classifying transactions, spotting
disallowances, explaining positions. The scripts make sure the numbers add up.

> Rates and due dates were verified on **17 Oct 2026** and live in one file,
> [`skills/ca-agent/scripts/rules.py`](skills/ca-agent/scripts/rules.py). The skill tells Claude to
> re-verify them when they may be stale.

## What it does not do

It never logs in to the GST, income-tax or MCA portals and never asks for passwords, OTPs or DSCs. It
prepares the return data and a filing checklist, and you file. It does not sign or certify anything:
audit reports need a practising CA's UDIN. Treat its output as a well-prepared draft for review, not as
professional advice.

## Install

**Claude Code: as a plugin from GitHub**
```
/plugin marketplace add magnetomohit-jpg/ca-agent-skill
/plugin install ca-agent@ca-agent-skills
```

**Claude Code: as a personal skill**
```
git clone https://github.com/magnetomohit-jpg/ca-agent-skill.git
```
Then copy `ca-agent-skill/skills/ca-agent` into `~/.claude/skills/` (all projects) or into
`<project>/.claude/skills/` (one project).

**Claude.ai / Claude desktop:** download
[`dist/ca-agent.skill`](https://github.com/magnetomohit-jpg/ca-agent-skill/raw/main/dist/ca-agent.skill)
(or zip the `skills/ca-agent` folder) and upload it under *Settings → Capabilities → Skills*.

The scripts need Python 3.10+. `openpyxl` is optional (Excel output).

## Try it

```
python examples/build_demo.py
```

This builds a complete FY 2025-26 for a fictional trading company, *Sahyadri Trading Private Limited*
(Maharashtra, GST monthly, s.115BAA), using the same steps the skill follows:

1. create the books and post 46 vouchers
2. book depreciation and deferred tax
3. compute income tax
4. produce the financial statements, GSTR-1/3B for April, a GSTR-2B reconciliation, a bank reconciliation
   and the compliance calendar

The results are in `examples/demo-company/reports/`.

Then ask Claude things like:
- "Prepare GSTR-3B for April 2025 for the books in examples/demo-company"
- "Here's my HDFC statement for May, post the entries and reconcile"
- "Finalise the accounts for FY 2025-26 and compute the company's tax"
- "I earn 18 lakh salary with 1.5 lakh 80C and a home loan, which regime and which ITR?"
- "What compliances are due for the company in the next 30 days?"

## Repository layout

```
skills/ca-agent/
  SKILL.md                 workflows and ground rules Claude follows
  references/              bookkeeping, GST, income tax, Schedule III, compliance notes
  scripts/                 books.py, parties.py, gst.py, income_tax.py, financials.py, depreciation.py,
                           bank_reco.py, compliance.py, rules.py (all rates), common.py
  assets/                  default chart of accounts mapped to Schedule III, register templates
examples/                  demo source data, statement/GSTR-2B inputs, build_demo.py, built demo books
tests/                     regression tests (python -m unittest discover -s tests)
evals/                     test prompts for skill evaluation
```

## Tests

```
python -m unittest discover -s tests -v
```

The tests rebuild the demo company and check the figures a reviewer would check by hand:
- the trial balance and balance sheet tally, and the cash flow reconciles
- GSTR-3B cash: Rs 19,200 = Rs 9,300 forward charge + Rs 9,900 reverse charge
- s.115BAA tax and 234C interest
- 87A marginal relief at Rs 12.1 lakh, and surcharge marginal relief
- MAT 15% → 14%
- set-off optimality, and the GSTR-2B and bank reconciliations

## Credits

Inspired by [Yogesh4527/FinCA](https://github.com/Yogesh4527/FinCA), a multi-agent design for automating CA
workflows for Indian MSMEs. This project takes the same goal and builds it as a Claude skill with working,
tested computations.

## License

MIT - see [LICENSE](LICENSE). Not professional advice; review outputs before filing.
