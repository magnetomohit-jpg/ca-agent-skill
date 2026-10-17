# Bookkeeping reference

Contents: 1. Voucher JSON · 2. Entry patterns · 3. Schedule III lines and tags · 4. Tally mapping ·
5. Importing data · 6. Month-end and year-end routines

## 1. Voucher JSON (input to `books.py post`)

```json
[{"date": "2025-07-03", "type": "Payment", "ref": "UTR N184250703123", "narration": "Legal fees - Adv. R. Kulkarni",
  "lines": [{"account": "Legal and Professional Fees", "dr": 50000},
            {"account": "TDS Payable - 194J Professional Fees", "cr": 5000},
            {"account": "HDFC Bank Current A/c", "cr": 45000}]}]
```

- `type` is one of: Opening, Journal, Sales, Purchase, Receipt, Payment, Contra, Debit Note, Credit Note, Adjustment.
  Voucher numbers are generated per type and year (`PMT/2025-26/0007`) unless you pass `voucher_no`.
- Each line has exactly one of `dr`/`cr`, and the amounts are positive. Debits must equal credits.
- `ref` is the source document number (invoice, UTR, cheque). Posting refuses a second voucher of
  the same type with the same ref, which stops double posting when the same statement is processed
  twice. Override with `--allow-duplicates` only when the documents really are different.
- Lines can carry their own `narration`.

## 2. Entry patterns

Use these exact account names (default COA) so the scripts' tags line up. "GST" means the
CGST + SGST pair for intra-state transactions, or IGST for inter-state ones.

| Transaction | Voucher | Entry |
|---|---|---|
| Sale of goods/services | Sales | Dr Customer (invoice value) · Cr Sales · Cr Output GST |
| Export under LUT / SEZ without payment | Sales | Dr Customer · Cr Export Sales (no GST; register supply_type EXPWOP/SEZWOP) |
| Export with IGST (refund route) | Sales | Dr Customer · Cr Export Sales · Cr Output IGST |
| Sales return / discount by credit note | Credit Note | Dr Sales · Dr Output GST · Cr Customer |
| Purchase with eligible ITC | Purchase | Dr Purchases / expense / asset · Dr Input GST · Cr Supplier |
| Purchase with blocked ITC (s.17(5)) | Purchase | Dr expense or asset **including** GST · Cr Supplier (register itc = blocked) |
| Purchase return | Debit Note | Dr Supplier · Cr Purchases · Cr Input GST |
| Reverse-charge supply (GTA, advocate, director's sitting fees, unregistered landlord's commercial rent, import of service) | Purchase/Payment + Journal | Expense booked as normal; Journal: Dr Input GST (if eligible) · Cr RCM GST Payable; later Dr RCM GST Payable · Cr Bank (cash only) |
| Import of goods | Purchase + Payment | Dr Purchases (assessable value) · Cr Foreign supplier; customs: Dr Purchases (BCD + SWS) · Dr Input IGST · Cr Bank |
| Expense with TDS | Payment/Journal | Dr Expense · Dr Input GST · Cr TDS Payable - section · Cr Party/Bank. TDS is on the amount **excluding** GST when GST is shown separately |
| TDS deducted by customer | Receipt | Dr Bank · Dr TDS Receivable · Cr Customer |
| TDS deposit | Payment | Dr TDS Payable - section · Cr Bank (challan ITNS 281 by the 7th) |
| Salary | Journal + Payment | Dr Salaries and Wages (gross) · Dr Contribution to Provident and Other Funds (employer PF/ESI) · Cr PF Payable · Cr ESI Payable · Cr Professional Tax Payable · Cr TDS Payable - 192 · Cr Salary Payable; then Dr Salary Payable · Cr Bank |
| GST monthly set-off (from `gst.py gstr3b` table 6.1) | Journal | Dr Output IGST/CGST/SGST · Cr Input IGST/CGST/SGST (as utilised) · Cr Bank (cash) |
| Advance tax / self-assessment tax | Payment | Dr Advance Tax (or Self-Assessment Tax) · Cr Bank |
| Provision for income tax (year end) | Journal | Dr Current Tax · Cr Provision for Income Tax |
| Set provision against prepaid taxes (once the return is filed or assessed) | Journal | Dr Provision for Income Tax · Cr Advance Tax · Cr TDS Receivable · Cr Self-Assessment Tax; difference to Tax of Earlier Years |
| Deferred tax | Journal | Dr Deferred Tax · Cr Deferred Tax Liability (Net), or the reverse |
| Depreciation | Journal | Dr Depreciation / Amortisation · Cr Accumulated Depreciation - class (`depreciation.py --voucher`) |
| Sale of a fixed asset | Sales + Journal | Dr Bank · Cr Output GST (GST on sale of used asset) · Dr Accumulated Depreciation · Cr Asset (cost) · balance to Profit / Loss on Sale of Fixed Assets |
| Closing stock | Journal | Dr Changes in Inventories · Cr Stock-in-Trade (opening); Dr Stock-in-Trade · Cr Changes in Inventories (closing) |
| Expenses outstanding | Journal | Dr Expense · Cr Expenses Payable / Audit Fees Payable |
| Prepaid expense | Journal | Dr Prepaid Expenses · Cr Expense |
| Share issue | Receipt | Dr Bank · Cr Equity Share Capital · Cr Securities Premium (file PAS-3) |
| Loan from director | Receipt | Dr Bank · Cr Unsecured Loans from Directors (get the director's declaration that the money is not borrowed - exempt deposit, disclose in DPT-3) |
| Interest on loans with TDS 194A | Journal | Dr Interest on Unsecured Loans · Cr TDS Payable · Cr Lender |
| Bad debt written off | Journal | Dr Bad Debts Written Off · Cr Customer |
| Cash deposited / withdrawn | Contra | Dr Bank · Cr Cash in Hand (or the reverse) |
| Foreign-currency receivable at year end (AS 11) | Journal | Restate at the closing rate: Dr/Cr Customer · Cr/Dr Foreign Exchange Gain/Loss |

Cash rules worth enforcing as you book. A payment to one person over Rs 10,000 in a day other than
by account-payee cheque, bank transfer or UPI is disallowed u/s 40A(3) (Rs 35,000 for transporters).
Receipts of Rs 2 lakh or more in cash attract a penalty u/s 269ST. Loans or deposits of Rs 20,000
or more cannot be taken or repaid in cash (s.269SS/269T). Flag these when you see them.

## 3. Schedule III lines and tags

`line` keys in `chart_of_accounts.csv`:

- **Equity and liabilities:** share_capital, other_equity, share_application_money, lt_borrowings,
  deferred_tax_liab, other_lt_liabilities, lt_provisions, st_borrowings, trade_payables_msme,
  trade_payables_others, other_current_liabilities, st_provisions
- **Assets:** ppe, intangible_assets, cwip, intangible_under_dev, nc_investments, deferred_tax_asset,
  lt_loans_advances, other_nc_assets, current_investments, inventories, trade_receivables,
  cash_equivalents, st_loans_advances, other_current_assets
- **Profit and loss:** revenue_operations, other_income, cost_materials, purchases_stock,
  changes_inventories, employee_benefits, finance_costs, depreciation, other_expenses,
  exceptional_items, current_tax, deferred_tax

`tag` values (semicolon-separated) that the scripts read:

| Tag | Used by |
|---|---|
| cash, bank | cash never negative check; bank reconciliation; s.40A(3) scan; overdraft reclassification |
| suspense | must be nil before finalising |
| retained_earnings | close-year transfers profit here |
| gst_output_igst/cgst/sgst, gst_input_*, gst_rcm_* | books-vs-register GST cross-check |
| tax_provision, tax_asset (+ advance_tax, tds_receivable, self_assessment) | income taxes paid in the cash flow; TDS and advance tax in the tax draft |
| interest_income, dividend_income, gain_on_sale, loss_on_sale | cash flow investing section; tax draft moves them to other heads |
| accumulated_depreciation, provision_doubtful_debts | contra accounts (no "unusual balance" warning) |
| disallow_37, csr, donation, provision, disallow | add-backs pre-filled in the tax draft |
| statutory_43b, msme, tds_payable, debtor, creditor | reminders and grouping |

## 4. Tally group to Schedule III mapping

| Tally group | Line (tag) |
|---|---|
| Capital Account | share_capital (company) / other_equity |
| Reserves & Surplus | other_equity |
| Secured Loans / Unsecured Loans | lt_borrowings (repayable beyond 12 months), st_borrowings (within 12 months / current maturities) |
| Bank OD A/c | st_borrowings |
| Sundry Creditors | trade_payables_msme (Udyam-registered micro/small) or trade_payables_others |
| Duties & Taxes (credit balances: output GST, TDS payable) | other_current_liabilities with GST/TDS tags |
| Duties & Taxes (debit balances: input GST) | other_current_assets with gst_input tags |
| Provisions | st_provisions / lt_provisions |
| Fixed Assets | ppe / intangible_assets (plus accumulated depreciation accounts) |
| Investments | nc_investments / current_investments |
| Stock-in-Hand | inventories |
| Deposits (Asset) | lt_loans_advances |
| Loans & Advances (Asset) | st_loans_advances / lt_loans_advances |
| Sundry Debtors | trade_receivables (debtor) |
| Cash-in-Hand | cash_equivalents (cash) |
| Bank Accounts | cash_equivalents (bank) |
| Sales Accounts | revenue_operations |
| Purchase Accounts | purchases_stock (trading) / cost_materials (manufacturing) |
| Direct Expenses | cost_materials or other_expenses (power, freight inward, job work) |
| Direct Incomes | revenue_operations (other operating revenue) |
| Indirect Expenses | employee_benefits / finance_costs / depreciation / other_expenses by nature |
| Indirect Incomes | other_income |
| Suspense A/c | other_current_assets (suspense) |
| Misc. Expenses (Asset) | other_current_assets / other_nc_assets |

## 5. Importing data

**Bank statements.** Download the statement as CSV or Excel, keep date/description/ref/withdrawal/
deposit/balance, and classify each line:
1. Match against invoices and open party balances first. NEFT/RTGS/UPI narrations usually name the party.
2. Apply recurring rules: salary batches, GST challans (CPIN), TDS challans (ITNS 281), EMI (split
   principal and interest from the loan schedule), bank charges, interest credits.
3. Anything unexplained goes to Suspense Account, and the list goes to the user.
4. Post as Receipt/Payment/Contra vouchers with the UTR/cheque number as `ref`, then run `bank_reco.py`.

**Tally.** For a full migration export the Day Book to Excel and convert each voucher. For a year-end
only engagement export the ledger-wise Trial Balance as at 31 March. Then:
1. Post last year's audited balance sheet as the Opening voucher.
2. Post one Journal per month per ledger group from the monthly trial balance movement, or the
   year's net movement if monthly detail is not needed.
3. Rebuild the sales and purchase registers from the GSTR-1 and books data so the GST tools work.
Always reconcile the imported trial balance total to Tally's before going further.

**Invoices (PDF or images).** Read the supplier GSTIN, invoice number and date, place of supply, HSN,
taxable value, rate and tax heads. Write one register line per HSN/rate and one voucher per invoice.
Check the GSTIN checksum (`gst.py check`) and the tax maths. Supplier invoices are a frequent source
of rate errors.

## 6. Routines

**Monthly:** post all vouchers → `books.py validate` → bank reconciliation for each account → `gst.py check`,
`gstr1`, `reco`, `gstr3b` → post the set-off/payment → deposit TDS by the 7th → review `tb` for
odd balances (credit balances in debtors, debit balances in creditors, negative stock) → update
`compliance.py --from <today>`.

**Quarterly:** TDS returns, advance tax, MSME-1 half-yearly, debtor and creditor balance confirmations,
review provisions.

**Year end:** follow Workflow 3 in SKILL.md, then `close-year`.
