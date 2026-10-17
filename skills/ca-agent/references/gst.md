# GST reference

Contents: 1. Rates (GST 2.0) · 2. Registration and schemes · 3. Tax type and place of supply ·
4. Invoicing, e-invoice, e-way bill · 5. Input tax credit · 6. Reverse charge · 7. Returns and due dates ·
8. GSTR-1 tables · 9. GSTR-3B tables and set-off · 10. Interest, late fee, time bars · 11. IMS and
GSTR-2B reconciliation · 12. Annual return · 13. Register column specifications

Statutory references are to the CGST Act 2017 and CGST Rules 2017 (IGST Act for inter-state rules).
Verify rates for a specific HSN/SAC against the current CBIC rate notification before relying on them.

## 1. Rates (GST 2.0, w.e.f. 22-09-2025)

The 56th GST Council (3 Sep 2025) moved to three main slabs:
- **5%** (merit rate): most items earlier at 12% and many daily-use goods.
- **18%** (standard rate): most goods and services, including most items earlier at 28%.
- **40%** (demerit rate): luxury and sin goods and services, such as pan masala and tobacco products, aerated
  and sugared beverages, larger cars and motorcycles above 350 cc, yachts and private aircraft, and betting,
  gambling and online money gaming.
- Nil/exempt items continue. Special rates continue for specific goods (0.1%, 0.25%, 1.5%, 3%), and some
  services keep 5% without ITC.
- Compensation cess was abolished on most goods; tobacco was the last to move (reported from Feb 2026).

Transition points:
- Invoices dated on or after 22-09-2025 use the new rate. Time-of-supply rules (s.12/13/14) decide which
  rate applies to advances and supplies that straddle the change.
- ITC reversal is needed only where a supply became **exempt**; a rate cut alone needs no reversal.
- `gst.py check` warns when 12% or 28% appears after 22-09-2025. Some items legitimately remain at
  those rates, so confirm the HSN rather than changing the rate blindly.

## 2. Registration and schemes

- **Threshold (aggregate turnover):** Rs 40 lakh for exclusive suppliers of goods (Rs 20 lakh in special
  category states), Rs 20 lakh for services (Rs 10 lakh in special category states).
- **Compulsory registration regardless of turnover (s.24):** inter-state taxable supply of goods, persons
  liable under RCM, e-commerce sellers (services relaxations apply), casual and non-resident taxable
  persons, ISDs and TDS/TCS deductors.
- **Composition (s.10):** aggregate turnover up to Rs 1.5 crore (Rs 75 lakh in special category states).
  Rates are 1% for manufacturers and traders and 5% for restaurants. Composition dealers cannot make
  inter-state outward supplies or collect tax, and get no ITC. They pay through CMP-08 quarterly and file GSTR-4 annually.
  The services composition scheme (s.10(2A)) is 6% up to Rs 50 lakh.
- **QRMP:** available up to Rs 5 crore AATO. The return is quarterly, tax is paid monthly through PMT-06
  (fixed-sum or self-assessment method), and IFF is optional for B2B invoices in months 1-2.

## 3. Tax type and place of supply

- Supplier's state = place of supply → CGST + SGST/UTGST (equal halves).
  Different states → IGST.
- Exports and supplies to SEZ units/developers are always inter-state (zero-rated, s.16 IGST Act). They
  go under LUT without tax, or with IGST and a refund.
- Goods: place of supply is where movement terminates for delivery (bill-to-ship-to: the third party
  on whose instructions goods are delivered).
- Services, general rule: the recipient's location if registered, otherwise the recipient's address on
  record, otherwise the supplier's location. Immovable property, restaurant, events and passenger transport
  have their own rules (s.12/13 IGST Act).
- ITC on supplies where the place of supply is a state where the recipient is not registered (e.g. hotel
  stay in another state) is not available. Report it in GSTR-3B table 4(D)(2) (register `itc` = `pos`).

## 4. Invoicing, e-invoice, e-way bill

- **Tax invoice (rule 46):** consecutive serial number, up to 16 characters (letters, digits, `-`, `/`),
  unique per FY. It needs the supplier and recipient GSTIN, place of supply, HSN (4 digits up to Rs 5 crore
  AATO, 6 digits above), taxable value, rate and tax heads, and a "Reverse charge: Yes/No" note.
- **Time limit:** for goods, at or before removal or delivery; for services, within 30 days of supply
  (45 days for banks and insurers).
- **E-invoice (IRN):** mandatory if AATO in any FY since 2017-18 exceeded Rs 5 crore. It covers B2B, SEZ,
  exports and deemed exports. Taxpayers with AATO of Rs 10 crore or more must report to the IRP within 30 days
  of the invoice date. An invoice without a valid IRN is not a valid invoice, so the recipient cannot claim ITC.
- **E-way bill:** needed for movement of goods with consignment value over Rs 50,000 (intra-state limits
  vary by state). It needs Part A (invoice details) and Part B (vehicle). Validity is 1 day per 200 km
  (20 km for over-dimensional cargo).
- **Credit note (s.34):** must be issued by 30 November following the end of the FY (or the annual return
  date, if earlier) to reduce output tax. ITC on the original invoice must be reversed by the recipient.

## 5. Input tax credit

Conditions under s.16:
- Tax invoice or debit note held.
- Invoice reported by the supplier in GSTR-1/IFF and appearing in the recipient's **GSTR-2B** (s.16(2)(aa)).
- Goods or services received (bill-to-ship-to and agent deliveries count).
- Tax actually paid by the supplier to the government.
- Recipient has filed GSTR-3B.
- Supplier paid within **180 days** of the invoice date. Otherwise reverse the ITC with interest (rule 37)
  and re-avail it on payment.
- **Time limit (s.16(4)):** 30 November following the end of the FY, or the annual return date if earlier.
  (Relief exists for FY 2017-18 to 2020-21 and revoked-registration cases, s.16(5)/(6).)

**Blocked credits (s.17(5)):** report these in 4(A) and reverse them in 4(B)(1) (register `itc` = `blocked`).
- Motor vehicles for carrying 13 persons or fewer (including the driver), plus their insurance, repair and
  servicing. Exceptions: vehicles used for further supply of vehicles, passenger transport, driving training,
  or goods transport.
- Vessels and aircraft, except for the specified uses.
- Food and beverages, outdoor catering, beauty treatment, health services, cosmetic and plastic surgery,
  life and health insurance, and leasing or renting of motor vehicles. Exceptions: where provided as part of
  the same category of outward supply, or obligatory for an employer under law.
- Membership of a club, health or fitness centre.
- Travel benefits to employees on vacation (LTC, home travel concession).
- Works contract for construction of immovable property, and goods or services used to construct
  immovable property on own account, even when capitalised. Plant and machinery is excluded from this block.
- Tax paid under composition, or on goods lost, stolen, destroyed, written off, or given as gifts or free samples.
- Tax paid on demands under s.74 (fraud) and on detained or confiscated goods.
- Goods or services for personal consumption.

**Partial use (rules 42/43):** where inputs are used partly for exempt supplies or non-business purposes,
reverse the common credit proportionately each month and true it up annually. Pass the amount with
`--reverse-42-43`. Capital goods credit is reversed over 60 months.

## 6. Reverse charge (common cases)

Services (notification 13/2017 as amended). The recipient pays tax in cash and may take ITC if eligible:
- Goods transport agency (GTA) services, unless the GTA has opted to pay under forward charge.
- Legal services by an advocate or firm of advocates to a business entity.
- Services by a director to the company (sitting fees, commission, not salary).
- Security services by a person other than a body corporate to a registered person (other than composition).
- Renting of a motor vehicle by a non-body-corporate to a body corporate (where the 5% no-ITC rate applies).
- Sponsorship services to a body corporate or firm.
- Insurance agents' services to insurers; recovery agents' services to banks and NBFCs.
- Royalties for copyright from authors, music composers and artists (unless the author has registered and opted out).
- Renting of residential dwelling to a registered person.
- **Renting of commercial property by an unregistered person to a registered person** (from 10-10-2024).
- Import of services (IGST Act). The recipient's location decides place of supply.

Goods: cashew nuts, bidi wrapper and tobacco leaves, silk yarn, raw cotton, lottery tickets, used
vehicles and seized goods sold by government, and certain metal scrap (check the current notification).

Report RCM inward supplies in 3.1(d) with ITC in 4(A)(2)/(3). Issue a self-invoice for supplies from
unregistered persons and a payment voucher.

## 7. Returns and due dates

| Return | Who / what | Due |
|---|---|---|
| GSTR-1 | outward supplies, monthly | 11th of next month |
| GSTR-1 (QRMP) / IFF | quarterly return / optional B2B upload in months 1-2 | 13th after quarter / 13th of next month |
| GSTR-3B | summary return + payment, monthly | 20th of next month |
| GSTR-3B (QRMP) | quarterly | 22nd (Category X states incl. MH, GJ, KA, TN, TS, AP, KL, MP, CG, GA) / 24th (others incl. DL, UP, RJ, HR, PB, WB) |
| PMT-06 (QRMP) | tax for months 1 and 2 of the quarter | 25th of next month |
| CMP-08 / GSTR-4 | composition dealers | 18th after quarter / 30 April annually |
| GSTR-7 / GSTR-8 | TDS (government) / TCS (e-commerce operators) | 10th of next month |
| ITC-04 | job work (goods sent to and received from job workers) | 25 October / 25 April (half-yearly, AATO > Rs 5 crore); 25 April annually for others |
| GSTR-9 / GSTR-9C | annual return / reconciliation statement | 31 December after the FY |

## 8. GSTR-1 tables (as produced by `gst.py gstr1`)

- **4A/4B/6B/6C (B2B, SEZ, deemed exports):** invoice-wise for registered recipients. RCM invoices are
  flagged, and SEZ with/without payment and deemed exports have their own invoice type.
- **5 (B2CL):** inter-state invoices to unregistered persons with invoice value above Rs 1,00,000
  (Rs 2,50,000 before 1-8-2024). Invoice-wise with place of supply.
- **6A (exports):** with or without payment, with port code and shipping bill number and date (add the
  shipping bill once available, via amendment if needed).
- **7 (B2CS):** all other B2C supplies, aggregated by place of supply and rate, **net** of credit notes
  for those supplies.
- **8:** nil-rated, exempt and non-GST supplies, split inter/intra-state and registered/unregistered.
- **9B (CDNR/CDNUR):** credit and debit notes. Registered recipients go to CDNR; unregistered recipients
  for B2CL invoices or exports go to CDNUR. Other B2C notes are netted in table 7.
- **12 (HSN summary):** separate **B2B and B2C tabs**, HSN + rate + UQC wise. Use 4 digits up to Rs 5 crore
  AATO and 6 above, and choose HSN codes from the portal drop-down.
- **13:** documents issued, giving serial ranges, totals and cancelled documents per document type.
- **11 (advances):** advances received for services where the invoice has not been issued, and their
  adjustment. The script does not compute this; add it by hand if relevant. No GST is payable on advances for goods.

## 9. GSTR-3B tables and set-off

- **3.1(a):** taxable outward supplies (other than zero-rated, nil and exempt), net of credit and debit notes.
- **3.1(b):** zero-rated supplies (exports, SEZ), with IGST where paid.
- **3.1(c):** nil and exempt supplies.
- **3.1(d):** inward supplies liable to RCM.
- **3.1(e):** non-GST outward supplies.
- **3.1.1:** e-commerce supplies u/s 9(5).
- **3.2:** of 3.1(a), inter-state supplies to unregistered persons, composition dealers and UIN holders,
  by place of supply.
- **4(A):** ITC available, split as (1) import of goods, (2) import of services, (3) other RCM, (4) ISD,
  (5) all other. Blocked credits are reported here and then reversed.
- **4(B):** (1) reversals under rules 38/42/43 and s.17(5) (permanent); (2) others, such as rule 37,
  non-receipt or 2B mismatch (reclaimable).
- **4(C):** net ITC.
- **4(D):** (1) reclaimed ITC; (2) ineligible under s.16(4) and place-of-supply restrictions (not claimed).
- **5:** exempt, nil and non-GST inward supplies.
- **5.1:** interest and late fee.
- **6.1:** payment.

**Set-off order (s.49, 49A, 49B; rule 88A):**
- IGST credit is used first against IGST, and the balance against CGST and SGST in any order or
  proportion. All IGST credit must be used before CGST/SGST credit.
- CGST credit is used against CGST, then IGST. SGST credit is used against SGST, then IGST.
- CGST credit can never pay SGST, or the reverse. Cess credit pays only cess.
- RCM liability, interest and late fee are paid in **cash only**.
- `gst.py` allocates IGST credit first to the head whose own credit falls short, which minimises cash.

**Portal checks (verify current behaviour on the portal):**
- GSTR-3B auto-populates from GSTR-1 (table 3) and GSTR-2B (table 4).
- Liability in table 3 is being locked to the GSTR-1/1A values, so corrections go through GSTR-1A
  before 3B is filed.
- Negative balances in the Electronic Credit Reversal and Reclaimed Statement and unpaid RCM block filing.

## 10. Interest, late fee, time bars

- **Interest (s.50):** 18% p.a. on tax paid late, computed on the **cash** portion only (net of ITC),
  for each day of delay. 24% applies to ITC wrongly availed **and** utilised.
- **Late fee for GSTR-3B and GSTR-1:** Rs 50 per day (Rs 25 CGST + Rs 25 SGST), Rs 20 per day for nil
  returns. Caps by previous-year AATO: Rs 2,000 (up to Rs 1.5 crore), Rs 5,000 (up to Rs 5 crore),
  Rs 10,000 (above). The nil-return cap is Rs 500.
- **Late fee for GSTR-9:** AATO up to Rs 5 crore pays Rs 50 per day, capped at 0.04% of turnover.
  Rs 5-20 crore pays Rs 100 per day, capped at 0.04%. Above Rs 20 crore pays Rs 200 per day, capped at
  0.5% (combined CGST + SGST; verify).
- **Three-year bar:** GSTR-1, GSTR-3B, GSTR-4, GSTR-5, GSTR-6, GSTR-7, GSTR-8 and GSTR-9 cannot be filed
  more than three years after their due date (enforced on the portal).
- **Penalties:** s.122 covers offences, s.125 general penalty (up to Rs 25,000), and s.73 (non-fraud) / s.74
  (fraud) govern demands. From FY 2024-25 a common time limit applies under s.74A.

## 11. IMS and GSTR-2B reconciliation

- In the **Invoice Management System**, each inward document the supplier uploads can be accepted,
  rejected or left pending before GSTR-2B is generated (around the 14th). Unactioned documents are deemed accepted.
  Rejecting a document removes it from your ITC and pushes the supplier to correct their return.
- **Reconcile every month before filing GSTR-3B.** Download GSTR-2B (Excel or JSON) from Returns →
  GSTR-2B. From the B2B sheet (and B2B-CDNR for notes) build a CSV with these columns:

  `gstin,supplier,invoice_no,invoice_date,doc_type,taxable_value,igst,cgst,sgst,cess,itc_availability`

  Portal headers map like this:
  - "GSTIN of supplier" → gstin
  - "Trade/Legal name" → supplier
  - "Invoice number" → invoice_no
  - "Integrated Tax" → igst
  - "Central Tax" → cgst
  - "State/UT Tax" → sgst
  - "ITC Availability" → itc_availability
  - Note type "C" (credit note) → doc_type CN.
- `gst.py reco` matches on GSTIN + normalised invoice number (separators and leading zeros ignored),
  then catches probable matches by supplier and amount. Act on each bucket:
  - *In books, not in 2B*: do not claim yet; ask the supplier to file; claim when it appears
    (within the s.16(4) time limit).
  - *In 2B, not in books*: book the bill if genuine, or reject it in IMS.
  - *Amount mismatch*: get a credit or debit note, or a correction from the supplier.
  - *ITC not available*: usually a place-of-supply issue or a supplier filed after the s.16(4) limit.
  Each row also shows the eligible ITC (nil for bills marked blocked, ineligible or pos in the register's
  `itc` column), and the report ends with a bridge from the 2B total to the 4(C) net ITC that `gstr3b`
  computes: books less 2B per bucket, less blocked/ineligible credit, plus RCM, import and ISD credit
  (never in 2B). `gstr3b` takes register ITC into 4(A)(5), so reverse credit on bills not yet in 2B with
  `--reverse-other` and reclaim it in 4(D)(1) when the supplier files.

## 12. Annual return (GSTR-9 / 9C)

- GSTR-9 is optional up to Rs 2 crore AATO and mandatory above. GSTR-9C (self-certified reconciliation of
  audited accounts with returns) applies above Rs 5 crore.
- Table 4/5 covers outward supplies, table 6 ITC availed, tables 7/8 reversals and the 2B comparison,
  tables 10-14 amendments made in the next FY up to 30 November, and table 17/18 the HSN summaries.
- `gst.py annual` gives the month-wise working from the registers. Reconcile it with:
  - turnover per books (`financials.py` revenue plus GST-exempt items);
  - output tax per returns filed;
  - ITC per books vs GSTR-2B / 3B.
  Differences must be explained in 9C.

## 13. Register column specifications

**sales_register.csv:** `date, invoice_no, doc_type (INV/CN/DN), original_invoice_no (for notes),
customer, gstin (blank for unregistered), place_of_supply (2-digit state code; 96 = foreign),
supply_type, hsn, description, uqc, qty, taxable_value, gst_rate, igst, cgst, sgst, cess,
reverse_charge (Y/N), port_code, shipping_bill_no`

- `supply_type` values: TAX, EXPWP, EXPWOP, SEZWP, SEZWOP, DE, NIL, EXEMPT, NONGST.

**purchase_register.csv:** `date, invoice_no, doc_type, original_invoice_no, supplier, gstin,
place_of_supply (your state for local supplies), supply_type, hsn, description, uqc, qty,
taxable_value, gst_rate, igst, cgst, sgst, cess, reverse_charge, itc, boe_no`

- `supply_type` values: TAX, IMPG (imports of goods with bill of entry), IMPS (import of services), ISD,
  NIL, EXEMPT, NONGST, COMP (from a composition dealer).
- `itc` values: eligible, blocked (s.17(5)), pos (place-of-supply restriction), 16_4 (time-barred), none.

General rules for both registers:
- One row per invoice per HSN/rate. Enter credit notes with positive amounts and doc_type CN.
- If the tax columns are blank, tax is computed from the rate; if filled, they are checked against it
  (±Rs 1 tolerance).
- Amounts are in rupees. Dates use YYYY-MM-DD or DD-MM-YYYY.
