# Income-tax reference

Contents:
1. Which Act applies
2. Section map (1961 → 2025)
3. Companies
4. Computing business income
5. Depreciation rules
6. Losses
7. Individuals and HUFs
8. Capital gains
9. ITR forms and due dates
10. Advance tax and interest
11. TDS
12. Tax audit and presumptive taxation
13. Script input formats

## 1. Which Act applies

| Income earned in | Law | Return | Terminology |
|---|---|---|---|
| FY 2025-26 or earlier | Income-tax Act, 1961 | filed in 2026 for AY 2026-27 | previous year / assessment year |
| 1-4-2026 onwards (tax year 2026-27) | Income-tax Act, 2025 + Income-tax Rules, 2026 | filed in 2027 | "tax year" only |

Budget 2026 kept slabs and rates unchanged. The main Finance Act 2026 changes were:
- MAT reduced to 14% and made a final tax (no new MAT credit) from tax year 2026-27.
- A 31 August due date for non-audit business returns (ITR-3/ITR-4).
- A revised-return window of 12 months (fee if revised late).
- TCS rationalisation and STT increases on derivatives.

Confirm specific provisions against the enacted text. Form numbers are being renumbered under the 2026
Rules (e.g. Form 3CD, 26AS, 16), so use whatever the e-filing portal shows.

## 2. Section map (old → new), commonly used provisions

Taken from published mapping tables. Verify against the bare Act before citing in a notice reply.

| 1961 | 2025 | Topic |
|---|---|---|
| 2 | 2 | Definitions |
| 4, 5 | 4, 5 | Charge, scope of total income |
| 10 | 11 + Schedules II-VII | Exempt incomes |
| 14 | 13 | Heads of income |
| 15-17 | 15-18 | Salaries, perquisites |
| 16 | 19 | Standard deduction and salary deductions |
| 22-24 | 20-22 | House property |
| 28, 29 | 26, 27 | Business income, computation |
| 30, 31 | 28 | Rent, repairs, insurance |
| 32 | 33 | Depreciation |
| 35 | 45 | Scientific research |
| 36 | 29-32 | Other deductions (bad debts, employee contributions ...) |
| 37 | 34 | General deduction |
| 40 | 36 | Amounts not deductible |
| 43B | 37 | Deduction on actual payment |
| 44AA | 62 | Books of account |
| 44AB | 63 | Tax audit |
| 44AD, 44ADA, 44AE | 58 | Presumptive taxation |
| 45, 48, 50 | 67, 72, 74 | Capital gains, computation, depreciable assets |
| 54, 54EC, 54F | 82, 85, 86 | Capital gains exemptions |
| 56, 57 | 92, 93 | Other sources |
| 70-74, 78-80 | 108-115, 119, 121 | Set-off and carry forward |
| 80C, 80CCD, 80D, 80E, 80G, 80GG | 123, 124, 126, 129, 133, 134 | Deductions |
| 80TTA, 80JJAA | 153, 146 | Deductions |
| 87A | 156 | Rebate |
| 115BAC | 202 | New regime (individuals) |
| 115JB | 206 (reported) | MAT |
| 139, 140A | 263, 266 | Return of income, self-assessment tax |
| 192 / 193-196 | 392 / 393 | TDS (salary / all other payments, consolidated tables) |

## 3. Companies

| Regime | Rate | Surcharge | Effective (with 4% cess) | Notes |
|---|---|---|---|---|
| s.115BAA (domestic) | 22% | 10% flat | 25.168% | no MAT. Gives up specified incentives: additional depreciation, 10AA, 33AB, 35(1)(ii)/(iii), 35(2AB), 35AD, Chapter VI-A except 80JJAA/80M. Opt by Form 10-IC by the due date of the first year; irreversible |
| s.115BAB (new manufacturing) | 15% | 10% | 17.16% | only companies set up after 1-10-2019 that began manufacturing by 31-3-2024 |
| Normal, turnover of FY-2 up to Rs 400 crore | 25% | 7% above Rs 1 crore, 12% above Rs 10 crore | 26.0% / 27.82% / 29.12% | MAT applies |
| Normal, other domestic | 30% | same | 31.2% / 33.38% / 34.94% | MAT applies |
| Foreign company | 35% | 2% / 5% | - | |

- **MAT (s.115JB):** 15% of book profit (FY 2025-26). From tax year 2026-27 it is 14% and a final tax with
  no new credit. Use of brought-forward credit is restricted (reportedly only after switching to the
  concessional regime, capped at 25% of tax; verify).
- **Book profit:** net profit per P&L, plus income tax, deferred tax, provisions for unascertained
  liabilities and for diminution in assets, and dividends proposed; less the lower of brought-forward
  loss or unabsorbed depreciation per books, and exempt income.
- **Marginal relief** applies at the surcharge thresholds: tax plus surcharge cannot exceed the tax at the
  threshold plus the income above it. The script applies this.
- **Firms and LLPs:** 30%, with 12% surcharge above Rs 1 crore. Partner remuneration is deductible within
  s.40(b) limits:
  - On book profit up to Rs 6 lakh: higher of Rs 3 lakh or 90%.
  - On the balance: 60%.
  - Interest to partners up to 12%.
  - TDS on partner payments u/s 194T from 1-4-2025.

## 4. Computing business income (Schedule BP add-backs and deductions)

Start from net profit per P&L, then adjust:

- **Add back** depreciation per books and deduct depreciation per the Act (s.32).
- **s.40(a)(i)/(ia):** 100% of payments to non-residents, and 30% of payments to residents, where TDS was not
  deducted or not paid by the ITR due date. Allowed in the year the TDS is paid.
- **s.40(a)(ii):** income tax, interest u/s 234A/B/C, and wealth tax.
- **s.37(1) Explanations:** penalties and fines for offences, and CSR expenditure u/s 135.
- **s.40A(2)(b):** payments to related persons in excess of fair market value.
- **s.40A(3):** cash payments above Rs 10,000 per person per day (Rs 35,000 for transporters), subject to the
  rule 6DD exceptions. `company-draft` lists candidate vouchers.
- **s.40A(7):** gratuity provision unless paid to an approved fund.
- **s.43B:** statutory dues (GST, PF/ESI employer share, bonus, leave encashment, interest to banks and NBFCs)
  are allowed only when paid. Payment on or before the ITR due date counts for the year.
- **s.43B(h):** amounts owed to **micro and small enterprises** are allowed only when paid within the
  MSMED Act s.15 limit: 15 days without a written agreement, 45 days with one. If unpaid by year end beyond
  the limit, they are allowed in the year of payment. The ITR-due-date proviso does not apply.
- **s.36(1)(va):** employees' PF/ESI contributions deposited after the due date under the relevant Act are
  disallowed permanently.
- **s.14A / rule 8D:** expenses relating to exempt income.
- **Capital expenditure** debited to P&L is added back and capitalised (claim depreciation instead).
- **Provisions** (doubtful debts, warranties without a scientific basis, contingent liabilities) are added back.
- **Deductions** include s.35D preliminary expenses (1/5th over 5 years), s.35(1) research, and s.80JJAA
  additional employee cost (30% for 3 years, available under 115BAA).
- **Move income to its own head:** interest and dividends to other sources, rent to house property, and
  sale of capital assets to capital gains (s.50 for depreciable assets).

## 5. Depreciation (s.32 and Appendix I)

- **Block of assets, written down value.** Block rates:
  - Building: residential 5%, others 10%, temporary 40%
  - Furniture 10%
  - Plant and machinery 15%
  - Motor cars 15% (30% for hire vehicles)
  - Computers and software 40%
  - Intangibles 25% (goodwill not depreciable from AY 2021-22)
  - Pollution control and energy saving 40%
- **Half the rate** applies where an asset is put to use for less than 180 days in the year.
- **Additional depreciation** of 20% on new plant and machinery for manufacturers (35% in notified backward
  areas): half in the first year if under 180 days, with the balance next year. Not available under
  115BAA/115BAB/115BAC.
- **Sale proceeds** reduce the block. Proceeds above the block's WDV are short-term capital gain (s.50).
  If the block ceases to exist, the balance is a short-term capital loss.
- **Companies Act (Schedule II):** useful lives in `rules.py`, with residual value up to 5% and SLM or WDV
  (WDV rate = 1 − (residual/cost)^(1/life)). Depreciation is pro rata by days. Component accounting applies
  for significant parts.
- **Deferred tax (AS 22):** timing difference × tax rate. Recognise a DTA on unabsorbed losses only with
  virtual certainty.

## 6. Losses

| Loss | Set-off | Carry forward |
|---|---|---|
| Business (non-speculative) | any head except salary in the same year | 8 years, against business income only; the return must be filed by the due date |
| Unabsorbed depreciation | any head except salary | indefinitely |
| Speculation | speculation income only | 4 years |
| Short-term capital loss | STCG or LTCG | 8 years |
| Long-term capital loss | LTCG only | 8 years |
| House property | other heads up to Rs 2 lakh (old regime; nil in new regime) | 8 years, against HP only |

For closely held companies, s.79 lapses losses if beneficial ownership of 51% or more changes (start-up relief applies).

## 7. Individuals and HUFs

**Slabs (FY 2025-26 and tax year 2026-27):**

| New regime (default, s.115BAC / 202) | Old regime (below 60) |
|---|---|
| 0-4 lakh nil; 4-8 lakh 5%; 8-12 lakh 10%; 12-16 lakh 15%; 16-20 lakh 20%; 20-24 lakh 25%; above 24 lakh 30% | 0-2.5 lakh nil; 2.5-5 lakh 5%; 5-10 lakh 20%; above 10 lakh 30% (senior 60+: nil to 3 lakh; super senior 80+: nil to 5 lakh) |
| Standard deduction Rs 75,000; rebate 87A up to Rs 60,000 if total income ≤ Rs 12 lakh (marginal relief just above), not available against special-rate income | Standard deduction Rs 50,000; rebate up to Rs 12,500 if total income ≤ Rs 5 lakh |
| Allowed: 80CCD(2) employer NPS (14% of salary), 80JJAA, family pension deduction (Rs 25,000) | All deductions: 80C 1.5 lakh, 80CCD(1B) 50,000, 80D 25,000/50,000 + parents, 80E, 80G, 80TTA 10,000 / 80TTB 50,000, HRA, LTA, home loan interest Rs 2 lakh (24(b)) |
| Surcharge capped at 25% | Surcharge 10% (> 50 lakh), 15% (> 1 crore), 25% (> 2 crore), 37% (> 5 crore) |

- Surcharge on STCG 111A, LTCG 112A/112 and dividends is capped at 15%. Cess is 4% on tax plus surcharge.
- **Switching regimes:** salaried taxpayers without business income choose each year in the return.
  Those with business income opt out through Form 10-IEA by the due date and can come back only once.

## 8. Capital gains (transfers on/after 23-7-2024)

| Asset | Short-term if held | STCG rate | LTCG rate |
|---|---|---|---|
| Listed equity shares, equity MF units (STT paid) | ≤ 12 months | 20% (s.111A) | 12.5% above Rs 1.25 lakh a year (s.112A) |
| Other listed securities | ≤ 12 months | slab | 12.5% without indexation |
| Unlisted shares, land and building, others | ≤ 24 months | slab | 12.5% without indexation (resident individuals/HUFs may choose 20% with indexation for land/building acquired before 23-7-2024) |
| Debt MF / market-linked debentures (acquired on/after 1-4-2023) | always short-term (s.50AA) | slab | - |

Exemptions:
- s.54 / 54F: reinvestment in a residential house, capped at Rs 10 crore.
- s.54EC: bonds up to Rs 50 lakh within 6 months.
- Unused basic exemption of residents can absorb special-rate gains (the script applies this).

## 9. ITR forms and due dates

| Form | Who |
|---|---|
| ITR-1 Sahaj | resident individual, income up to Rs 50 lakh from salary/pension, one house property, other sources, LTCG 112A up to Rs 1.25 lakh. Not for directors, holders of unlisted shares, those with foreign assets or income, brought-forward losses, or agricultural income above Rs 5,000 |
| ITR-2 | individuals and HUFs without business income (capital gains, multiple properties, foreign assets, directors) |
| ITR-3 | individuals and HUFs with business or professional income (including partners) |
| ITR-4 Sugam | resident individuals, HUFs and firms (not LLPs) with presumptive income (44AD/44ADA/44AE) and income up to Rs 50 lakh, subject to ITR-1-type conditions |
| ITR-5 | firms, LLPs, AOPs, BOIs |
| ITR-6 | companies (other than those claiming s.11 exemption); verify with DSC |
| ITR-7 | trusts, political parties, institutions (s.139(4A)-(4D)) |

**Due dates for FY 2025-26 (AY 2026-27):**
- Non-audit individuals: 31 July 2026.
- Non-audit business/profession (ITR-3/ITR-4): 31 August 2026.
- Companies and audit cases: 31 October 2026, extended by CBDT to 21 November 2026. The tax audit report
  was extended to 21 October 2026.
- Transfer pricing cases: 30 November 2026.
- Belated return: 31 December 2026 (fee u/s 234F of Rs 5,000, or Rs 1,000 if income is up to Rs 5 lakh;
  losses other than HP and unabsorbed depreciation cannot be carried forward).
- Revised return: up to 31 March 2027 (fee for late revision; verify).
- Updated return (ITR-U): within 48 months, with additional tax of 25%/50%/60%/70% depending on the year.

**Before filing, reconcile with Form 26AS, AIS and TIS:** TDS/TCS credits, SFT-reported transactions,
interest, dividends and securities sales. Mismatches drive automated notices (s.143(1)(a) adjustments).

## 10. Advance tax and interest

- Advance tax is payable if net tax after TDS is Rs 10,000 or more. Instalments: 15% by 15 June, 45% by
  15 September, 75% by 15 December and 100% by 15 March. Presumptive 44AD/44ADA taxpayers pay 100% by 15 March.
  Resident seniors (60+) without business income are exempt.
- **s.234C:** 1% per month for 3 months on the shortfall per instalment (1 month for March). There is no
  interest if at least 12% was paid by June and 36% by September.
- **s.234B:** 1% per month or part from 1 April of the AY to the date of payment or determination,
  if advance tax paid is below 90% of assessed tax.
- **s.234A:** 1% per month or part on unpaid tax from the day after the due date until filing.
- Interest amounts are computed on tax rounded down to the nearest Rs 100. Total income is rounded to the
  nearest Rs 10 (s.288A), and tax payable is rounded to the nearest Rs 10 (s.288B).

## 11. TDS

Run `income_tax.py tds-rates` for the table (FY 2025-26 rates and thresholds from Budget 2025; s.393
under the 2025 Act). Key points:

- **When:** deduct at the time of credit or payment, whichever is earlier. Use the rate on the amount
  excluding GST where GST is shown separately.
- **No PAN:** s.206AA, the higher of twice the rate or 20%. The higher rate for non-filers (s.206AB) was
  removed from 1-4-2025.
- **Deposit:** by the 7th of the next month (30 April for March).
- **Returns:** quarterly, 24Q (salary) and 26Q (others) by 31 Jul, 31 Oct, 31 Jan and 31 May; 27Q for
  non-residents; 27EQ for TCS by the 15th. Certificates: Form 16 by 15 June and Form 16A within 15 days of
  the return due date.
- **Defaults:**
  - interest 1% per month for late deduction and 1.5% per month for late deposit (s.201(1A));
  - fee of Rs 200 per day up to the TDS amount (s.234E);
  - penalty of Rs 10,000 to Rs 1 lakh (s.271H);
  - disallowance u/s 40(a)(ia).
- **Lower deduction:** payees can apply for a lower-deduction certificate (s.197). Payees with no tax
  liability can give Form 15G/15H for interest and dividends.

## 12. Tax audit and presumptive taxation

**Tax audit (s.44AB):**
- Business turnover above Rs 1 crore, or Rs 10 crore if cash receipts and cash payments are each 5% or less.
- Professional receipts above Rs 50 lakh.
- Presumptive taxpayers who declare a lower profit when income exceeds the basic exemption.
- Report in Form 3CA-3CD (entity already audited, e.g. a company) or 3CB-3CD, one month before the ITR due date.
- Penalty u/s 271B: 0.5% of turnover, up to Rs 1.5 lakh.

**s.44AD:** resident individuals, HUFs and firms (not LLPs) with turnover up to Rs 2 crore (Rs 3 crore if
cash receipts are 5% or less). Deemed profit is 8% (6% on digital receipts). Opting out bars re-entry for
5 years.

**s.44ADA:** specified professionals with receipts up to Rs 50 lakh (Rs 75 lakh if cash receipts are 5%
or less). Deemed profit is 50%.

**s.44AE:** goods carriers (up to 10 vehicles). Rs 1,000 per ton per month for heavy vehicles, Rs 7,500
per month for others.

## 13. Script input formats

**Company (`income_tax.py company`).** `company-draft` produces this; edit it before running:

```json
{"name": "X Pvt Ltd", "fy": "2025-26", "regime": "115BAA", "turnover_fy_minus_2": 45000000,
 "profit_before_tax": 959269.95,
 "add_backs": [{"item": "Depreciation as per books", "amount": 123730.05, "ref": "s.32"}],
 "deductions": [{"item": "Depreciation as per Income-tax Act", "amount": 63470, "ref": "s.32"}],
 "income_other_heads": {"interest": 8000, "stcg_111a": 0, "ltcg_112a": 0},
 "brought_forward": {"business_loss": 0, "unabsorbed_depreciation": 0},
 "chapter_via": [{"section": "80JJAA", "amount": 0}],
 "mat_adjustments": [{"item": "Provision for diminution", "amount": 0}], "mat_credit_bf": 0, "mat_credit_usable": false,
 "tds_tcs": 0, "advance_tax": [{"date": "2025-06-14", "amount": 30000}],
 "self_assessment_paid": [], "filing_date": "2026-10-31", "due_date": null}
```

`income_other_heads` amounts must already be inside `profit_before_tax`. They are taken out of business
income and taxed under their own head; keys `stcg_111a`, `ltcg_112a` and `ltcg_112` get special rates.

**Individual (`income_tax.py individual`):**

```json
{"name": "A. Sharma", "fy": "2025-26", "age": 34, "resident": true,
 "salary": {"gross": 1800000, "exempt_allowances_old": {"hra": 180000}, "professional_tax": 2500},
 "house_property": [{"type": "self_occupied", "interest": 150000},
                    {"type": "let_out", "rent": 240000, "municipal_tax": 12000, "interest": 90000}],
 "business_income": 0,
 "capital_gains": {"stcg_111a": 0, "ltcg_112a": 200000, "stcg_other": 0, "ltcg_112": 0},
 "other_sources": {"savings_interest": 12000, "fd_interest": 40000, "dividend": 5000, "family_pension": 0},
 "deductions_old": {"80C": 150000, "80CCD1B": 50000, "80D": 25000, "80TTA": 10000, "80CCD2": 0},
 "deductions_new": {"80CCD2": 0},
 "tds": 150000, "advance_tax": []}
```

**ITR form (`income_tax.py itr-form`):**

```json
{"entity_type": "individual", "fy": "2025-26", "resident": true, "total_income": 1800000,
 "business_income": false, "presumptive": false, "director": false, "unlisted_shares": false,
 "foreign_assets": false, "house_properties": 1, "agricultural_income": 0,
 "capital_gains": {"ltcg_112a": 0}, "turnover": 0, "gross_receipts_profession": 0,
 "cash_receipts_and_payments_within_5pct": true}
```
