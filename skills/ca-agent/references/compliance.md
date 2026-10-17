# Compliance reference

`compliance.py` generates the dated calendar. This file covers what each item is, who must file it,
and what happens if it is missed. These are statutory dates: check for extensions (CBDT/CBIC/MCA
circulars) before advising, because extensions are frequent near deadlines.

## Monthly

| Due | Item | Notes |
|---|---|---|
| 7th | TDS/TCS deposit (challan ITNS 281) | March deductions by 30 April; government deductors on the same day |
| 10th | GSTR-7 / GSTR-8 | GST TDS deductors / e-commerce TCS |
| 11th | GSTR-1 (monthly filers) | 13th for QRMP quarterly / IFF |
| 15th | PF (ECR) and ESI contributions | late PF: damages + interest u/s 7Q; employees' share paid late is disallowed u/s 36(1)(va) |
| 20th | GSTR-3B + payment (monthly) | QRMP: PMT-06 by the 25th; quarterly 3B by the 22nd/24th |
| varies | Professional tax, labour welfare fund | state-specific (e.g. Maharashtra PT monthly/annual returns; Karnataka monthly) |

## Quarterly and half-yearly

| Due | Item |
|---|---|
| 15 Jun, 15 Sep, 15 Dec, 15 Mar | Advance tax (15/45/75/100%) |
| 31 Jul, 31 Oct, 31 Jan, 31 May | TDS returns 24Q (salary), 26Q (residents), 27Q (non-residents) |
| 15 Jul, 15 Oct, 15 Jan, 15 May | TCS return 27EQ |
| 15 days after return due date | Form 16A (non-salary TDS certificates) |
| 18th after quarter | CMP-08 (composition) |
| 30 Apr (Oct-Mar) / 31 Oct (Apr-Sep) | MSME-1: outstanding dues to micro and small enterprises beyond 45 days |
| 25 Apr / 25 Oct | ITC-04 job work (half-yearly if AATO > Rs 5 crore; others annually by 25 Apr) |

## Annual: income tax

| Due | Item |
|---|---|
| 31 May | SFT (Form 61A) for reporting entities; Form 24Q/26Q Q4 |
| 15 Jun | Form 16 to employees |
| 31 Jul | ITR for non-audit individuals (ITR-1/2) |
| 31 Aug | ITR for non-audit business/profession (ITR-3/4) - from AY 2026-27 |
| 30 Sep (extended to 21 Oct 2026 for AY 2026-27) | Tax audit report (3CA/3CB-3CD) |
| 31 Oct (extended to 21 Nov 2026 for AY 2026-27) | ITR for companies and audit cases; Form 3CEB for TP cases |
| 30 Nov | ITR for transfer-pricing cases |
| 31 Dec | Belated return |
| per Act | Form 10-IC (first year of 115BAA, by the return due date); Form 10-IEA (individuals with business income opting for the old regime) |

## Annual: GST

| Due | Item |
|---|---|
| 30 Apr | GSTR-4 (composition annual) |
| 30 Nov | Last date for prior-year ITC, credit notes and amendments (s.16(4), s.34, s.37/39 provisos) |
| 31 Dec | GSTR-9 (mandatory above Rs 2 crore AATO), GSTR-9C (above Rs 5 crore) |

## Annual: Companies Act / MCA

| Due | Form | Notes |
|---|---|---|
| 30 Jun | DPT-3 | return of deposits and of outstanding receipts not treated as deposits (loans from directors etc.), as at 31 March |
| 30 Jun | DIR-3 KYC (web) | **once every 3 financial years** from the 2025 amendment (G.S.R. 943(E)); changes to contact details within 30 days via DIR-6; DIN deactivated if missed (Rs 5,000 fee to reactivate) |
| 30 Sep | AGM | within 6 months of FY end (first AGM: 9 months); OPCs exempt |
| AGM + 15 days | ADT-1 | auditor appointment (5-year term) |
| AGM + 30 days | AOC-4 / AOC-4 XBRL / AOC-4 CFS | financial statements; OPC: within 180 days of FY end; CSR-2 alongside where s.135 applies |
| AGM + 60 days | MGT-7 / MGT-7A | annual return (MGT-7A for small companies and OPCs) |
| 30 days of board resolution | MGT-14 | specified resolutions (private companies are exempt for many board resolutions, including approval of accounts) |
| as events occur | DIR-12 (director change, 30 days), PAS-3 (allotment, 15 days), SH-7 (capital increase, 30 days), CHG-1/CHG-4 (charge creation/satisfaction, 30 days), INC-22 (registered office change, 30 days), BEN-2 (significant beneficial owners, 30 days of declaration), INC-20A (commencement of business, within 180 days of incorporation) | |
| events | Board meetings: first within 30 days of incorporation; at least 4 a year with no more than 120 days between two (small company / OPC: 2 a year, 90 days apart) | |

Penalty for late MCA filings: additional fees of Rs 100 per day per form (no upper cap for AOC-4/MGT-7
delays). Continuing default triggers adjudication penalties under s.92/s.137 and possible director
disqualification u/s 164(2) after 3 years of non-filing.

## Annual: LLP

| Due | Form |
|---|---|
| 30 May | Form 11 (annual return) |
| 30 Oct | Form 8 (statement of account and solvency) |
| 31 Oct (audit) / 31 Jul (non-audit; 31 Aug for business from AY 2026-27) | ITR-5 |

Late fee is Rs 100 per day per form.

## Registrations to check at onboarding

- PAN and TAN (TAN is needed before deducting TDS)
- GSTIN for each state with a place of business, and an LUT (RFD-11) every year for exports without tax
- Udyam (MSME) registration; Shops and Establishments licence; Professional tax registration and enrolment
- PF (20+ employees) and ESI (10+ employees, wages up to Rs 21,000)
- IEC for import and export
- Bank KYC; DSC for directors and authorised signatories (needed for ITR-6, MCA forms and GST if the
  company files with DSC)
