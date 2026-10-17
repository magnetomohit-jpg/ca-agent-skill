# Purchase register vs GSTR-2B - Apr 2025

| Status | Count | Tax as per books | Eligible ITC (books) | Tax as per 2B |
| --- | --- | ---: | ---: | ---: |
| Matched | 3 | 97,000.00 | 96,000.00 | 97,000.00 |
| In GSTR-2B, not in books | 1 | 0.00 | 0.00 | 900.00 |

ITC per books 97,000.00 | ITC per GSTR-2B 97,900.00

## Detail

| Status | GSTIN | Supplier | Invoice | Books tax | Eligible ITC | 2B tax | Difference | ITC flag |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| Matched | 24AAGCR9012M1Z6 | Rathod Components Pvt Ltd | RC/101 | 90,000.00 | 90,000.00 | 90,000.00 | 0.00 |  |
| Matched | 27AACFM3456N1ZX | Mehta Packaging | MP/55 | 6,000.00 | 6,000.00 | 6,000.00 | 0.00 |  |
| Matched | 27AAFCA2468B1ZZ | Annapurna Caterers | AC/77 | 1,000.00 | 0.00 | 1,000.00 | 0.00 | blocked |
| In GSTR-2B, not in books | 27AAJFS1357K1ZU | Speedy Couriers | SC/0009 | 0.00 | 0.00 | 900.00 | (900.00) |  |

_Matching ignores eligibility: a bill blocked u/s 17(5) can be 'Matched' and still give no ITC. The Eligible ITC column is what reaches 4(C)._

## Bridge: GSTR-2B to GSTR-3B table 4(C)

| Particulars | Rs |
| --- | ---: |
| ITC as per GSTR-2B (B2B bills) | 97,900.00 |
| Add/(less): books less 2B on 'In GSTR-2B, not in books' | (900.00) |
| **Tax on B2B forward-charge bills in the purchase register** | 97,000.00 |
| Less: blocked u/s 17(5), ineligible or PoS-restricted on those bills | (1,000.00) |
| Add: ITC on other register lines (RCM incl. import of services, import of goods, ISD, bills without GSTIN) | 9,900.00 |
| **= 4(C) net ITC per gstr3b (before --reverse-42-43 / --reverse-other)** | 1,05,900.00 |

- RCM ITC of 9,900.00 (4(A)(2)/(3)) is not in GSTR-2B: it is self-assessed and claimable once the reverse-charge tax is paid in cash.

Action points: chase suppliers for 'In books, not in GSTR-2B' (ITC cannot be claimed until it appears - sec 16(2)(aa)); book or reject in IMS the 'In GSTR-2B, not in books' items; correct amount mismatches with the supplier.
