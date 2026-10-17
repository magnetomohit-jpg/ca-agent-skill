# Financial statements reference (Companies Act 2013, Schedule III)

Contents:
1. Which framework
2. Balance sheet and P&L format
3. Mandatory notes
4. Additional regulatory information
5. Accounting standards checklist
6. Small company and OPC relaxations
7. CARO 2020 and audit
8. Approval and filing sequence

## 1. Which framework

- **Division I (AS-based):** used by most private and unlisted companies. This is what `financials.py` produces.
- **Division II (Ind AS):** listed companies or those in the process of listing, and companies with net
  worth of Rs 250 crore or more, together with their holding, subsidiary, JV and associate companies. It uses
  "Other equity", "financial assets" and an OCI section. If the user is on Ind AS, regroup the output rather
  than presenting it as Division I.
- **Division III:** NBFCs.
- **Non-corporate entities (firms, LLPs, proprietors)** have no statutory format. Use the same layout with
  "Partners' capital / Owners' funds" in place of share capital. ICAI's format for non-corporate entities
  is a good guide, and LLPs file Form 8.
- **Rounding:** companies with turnover below Rs 100 crore may round to the nearest hundred, thousand, lakh
  or million (or decimals of these); those with turnover of Rs 100 crore or more round to lakhs, millions or
  crores. Use one unit consistently.

## 2. Balance sheet and P&L format (what `financials.py` produces)

**Balance sheet:**
- I. Equity and liabilities:
  - (1) Shareholders' funds: share capital, reserves and surplus (a debit balance in the P&L surplus is
    shown here as a negative figure, not as an asset)
  - (2) Share application money pending allotment
  - (3) Non-current liabilities: long-term borrowings, DTL (net), other long-term liabilities, long-term provisions
  - (4) Current liabilities: short-term borrowings (including current maturities of long-term debt), trade
    payables (MSE / others), other current liabilities, short-term provisions
- II. Assets:
  - (1) Non-current: PPE and intangibles (PPE, intangibles, CWIP, intangibles under development),
    non-current investments, DTA (net), long-term loans and advances, other non-current assets
  - (2) Current: current investments, inventories, trade receivables, cash and cash equivalents,
    short-term loans and advances, other current assets

**Current vs non-current:** an item is current if it will be realised or settled within 12 months or
the operating cycle, or is held for trading. Split loans and deposits by their repayment schedule.

**Statement of P&L:**
- Revenue from operations and other income
- Expenses: cost of materials consumed, purchases of stock-in-trade, changes in inventories, employee
  benefits, finance costs, depreciation and amortisation, other expenses
- Exceptional and extraordinary items
- Tax (current, deferred)
- Profit for the period
- EPS (basic and diluted, AS 20)

## 3. Mandatory notes (beyond the account-wise notes the script prints)

**Share capital:**
- authorised, issued, subscribed and paid-up capital (number of shares and par value)
- reconciliation of shares at the start and end of the year
- rights and restrictions attached to each class
- shareholders holding more than 5%
- **promoter shareholding** (name, shares, % of total, % change during the year)
- bonus issues, buy-backs and issues for consideration other than cash in the last 5 years
- calls unpaid

**Reserves and surplus:** each reserve separately, with movements (opening, additions, deductions,
closing). Securities premium use. Surplus: opening, profit, appropriations (dividend, transfer to reserves),
closing.

**Borrowings:**
- secured or unsecured, with the nature of security
- terms of repayment and rate of interest
- loans guaranteed by directors
- continuing defaults (period and amount)
- current maturities shown under short-term borrowings

**Trade payables:**
- dues to micro and small enterprises separately, with the MSMED Act s.22 disclosures (principal and
  interest unpaid, interest paid u/s 16, interest due and payable)
- **ageing schedule:** less than 1 year, 1-2 years, 2-3 years, more than 3 years, split into MSME / others /
  disputed MSME / disputed others, counted from the due date of payment

**Trade receivables:**
- secured / unsecured considered good, significant increase in credit risk, credit impaired
- debts due from directors and officers
- **ageing schedule:** less than 6 months, 6 months-1 year, 1-2, 2-3, more than 3 years, split into
  undisputed / disputed and good / doubtful

**PPE and intangibles:**
- reconciliation of gross and net carrying amount per class (opening, additions, disposals, acquisitions
  through business combinations, revaluation, depreciation, closing). `depreciation.py` gives this table.
- **CWIP and intangibles under development ageing** (less than 1 year, 1-2, 2-3, more than 3) and a
  completion schedule for overdue or over-budget projects

**Inventories:** by class (raw materials, WIP, finished goods, stock-in-trade, stores, goods in transit),
with the mode of valuation (AS 2: lower of cost and NRV).

**Cash and cash equivalents:**
- balances with banks, cheques in hand, cash in hand
- earmarked balances (unpaid dividend), margin money
- deposits with maturity of more than 12 months

**Loans and advances:** loans to promoters, directors, KMPs and related parties (repayable on demand or
without terms), with the amount and % of total.

**Contingent liabilities and commitments:** claims not acknowledged as debts, guarantees, other money for
which the company is contingently liable, and capital commitments.

**P&L details:**
- revenue (sale of products, sale of services, other operating revenue)
- other income (interest, dividend, net gain on sale of investments)
- **payments to the auditor** (as auditor, for taxation matters, company law matters, other services,
  reimbursement of expenses)
- CSR expenditure (s.135: amount required, amount spent, shortfall, reasons, related-party contributions,
  unspent amount transferred)
- prior-period items (AS 5)

**Related parties (AS 18):** names and relationships (holding, subsidiaries, KMP and their relatives,
enterprises with significant influence), transactions by nature, and year-end balances.

**Events after the balance sheet date (AS 4)** and **proposed dividend** (disclosed, not provided).

## 4. Additional regulatory information (Schedule III, from FY 2021-22)

Disclose (or state "not applicable / nil") for each of these:
1. Title deeds of immovable property not held in the company's name.
2. Revaluation of PPE and whether it was done by a registered valuer.
3. Loans to promoters, directors, KMPs and related parties without terms or repayable on demand.
4. CWIP and intangibles-under-development ageing.
5. Benami property proceedings.
6. Borrowings secured by current assets: whether quarterly returns to banks agree with the books (reconcile
   the differences).
7. Wilful defaulter status.
8. Transactions with companies struck off.
9. Charges or satisfaction not yet registered with the ROC.
10. Compliance with the number of layers of companies.
11. Analytical **ratios**, with explanations for any change above 25%. `financials.py` computes current
    ratio, debt-equity, ROE, inventory turnover, receivables turnover, payables turnover, net capital
    turnover, net profit ratio and ROCE. Add DSCR and return on investment where relevant.
12. Schemes of arrangement.
13. Utilisation of borrowed funds and share premium (intermediary or ultimate beneficiary declarations).
14. Undisclosed income surrendered in tax assessments.
15. CSR details.
16. Crypto or virtual currency held or traded.

## 5. Accounting standards checklist (AS, Companies (Accounting Standards) Rules 2021)

| Standard | What to check |
|---|---|
| AS 1 | Accounting policies note (Note 1); going concern, accrual, consistency |
| AS 2 | Inventory at the lower of cost and NRV; cost formula (FIFO/weighted average); exclude GST if ITC is available |
| AS 3 | Cash flow statement, indirect method (not required for small companies or OPCs) |
| AS 4 | Contingencies and events after the reporting date |
| AS 5 | Prior-period items and changes in estimates or policies |
| AS 7 / AS 9 | Construction contracts / revenue recognition (transfer of risks, services by proportionate completion) |
| AS 10 | PPE: capitalisation, components, subsequent costs, disposals |
| AS 11 | Foreign exchange: monetary items restated at the closing rate |
| AS 12 / 13 | Government grants / investments (current at the lower of cost and fair value; long-term at cost less permanent decline) |
| AS 15 | Employee benefits: gratuity and leave by actuarial valuation (SMCs may use simpler methods) |
| AS 16 | Borrowing costs capitalised on qualifying assets |
| AS 17 | Segment reporting (not for SMCs) |
| AS 18 | Related-party disclosures |
| AS 19 | Leases (operating lease rent straight-lined) |
| AS 20 | EPS (diluted EPS not mandatory for SMCs) |
| AS 22 | Current tax and deferred tax; DTA on losses only with virtual certainty |
| AS 26 / AS 28 | Intangibles (amortisation, R&D) / impairment |
| AS 29 | Provisions and contingent liabilities |

## 6. Small company and OPC relaxations

A **small company** (s.2(85)) is a private company with paid-up capital up to Rs 10 crore **and** turnover
up to Rs 100 crore (thresholds from 1-12-2025), and is not a holding or subsidiary company, s.8 company,
or company governed by a special Act. Small companies and OPCs:
- need not prepare a cash flow statement (s.2(40));
- file an abridged annual return (MGT-7A);
- need only 2 board meetings a year, with at least 90 days between them;
- have lower filing fees and penalties;
- are exempt from auditor rotation and from reporting on internal financial controls;
- are exempt from CARO.

## 7. CARO 2020 and audit

- **Every company** must be audited (s.143). The first auditor is appointed by the board within 30 days of
  incorporation. After that the AGM appoints the auditor for 5 years (ADT-1 within 15 days of the AGM).
- **CARO 2020** applies except to banking companies, insurance companies, s.8 companies, OPCs, small
  companies, and private companies that are not holding or subsidiary of a public company and have:
  - paid-up capital plus reserves of Rs 1 crore or less;
  - borrowings of Rs 1 crore or less from banks or financial institutions; and
  - revenue of Rs 10 crore or less.
- **Internal financial controls reporting** is exempt for OPCs, small companies, and private companies with
  turnover below Rs 50 crore or borrowings below Rs 25 crore.
- **Audit trail:** accounting software must keep an edit log (rule 3(1) of the Accounts Rules), and the
  auditor reports on it. Our CSV books are append-only by design (corrections are posted as new vouchers),
  but advise companies to use compliant software for statutory books.

## 8. Approval and filing sequence

1. Finalise the books, then the draft financial statements, then the auditor's review and audit report
   (UDIN).
2. The board meeting approves the financial statements and the board's report (s.134). Signatures:
   chairperson (if authorised), or two directors (one of them the MD if any), and the CEO, CFO and CS where
   appointed. An OPC needs one director.
3. AGM within 6 months of year end (by 30 September), with the first AGM within 9 months of the first year
   end. OPCs are exempt from AGMs.
4. File AOC-4 within 30 days of the AGM (OPC: within 180 days of the year end) and MGT-7/7A within 60 days.
5. File the tax audit report (if applicable) and then ITR-6 by the income-tax due date.
