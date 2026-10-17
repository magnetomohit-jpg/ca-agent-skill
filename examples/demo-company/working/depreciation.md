# Depreciation - Sahyadri Trading Private Limited - FY 2025-26
Book method: WDV (Companies Act Schedule II; intangibles straight-line over useful life). Tax regime: 115BAA - additional depreciation not available.

## Asset-wise book depreciation

| Asset | Description | Method | Life | Opening cost | Additions | Disposals (cost) | Opening acc. dep. | Depreciation | Closing NBV | Gain/(loss) on sale |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| FA-001 | Office furniture and workstations | WDV | 10.00 | 3,00,000.00 | 0.00 | 0.00 | 60,000.00 | 62,127.73 | 1,77,872.27 |  |
| FA-002 | Laptops (5 nos) | WDV | 3.00 | 1,50,000.00 | 0.00 | 0.00 | 90,000.00 | 37,895.81 | 22,104.19 |  |
| FA-003 | Laptops (3 nos) - Infotech IT/301 | WDV | 3.00 | 0.00 | 1,00,000.00 | 0.00 | 0.00 | 23,706.51 | 76,293.49 |  |

## PPE / intangibles note (gross block, depreciation, net block)

| Class | Gross opening | Additions | Disposals | Gross closing | Dep. opening | For the year | On disposals | Dep. closing | Net closing | Net opening |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Computers | 1,50,000.00 | 1,00,000.00 | 0.00 | 2,50,000.00 | 90,000.00 | 61,602.32 | 0.00 | 1,51,602.32 | 98,397.68 | 60,000.00 |
| Furniture and Fixtures | 3,00,000.00 | 0.00 | 0.00 | 3,00,000.00 | 60,000.00 | 62,127.73 | 0.00 | 1,22,127.73 | 1,77,872.27 | 2,40,000.00 |

## Income-tax depreciation (WDV blocks)

| Block | Rate | Opening WDV | Additions >=180 days | Additions <180 days (half rate) | Sale proceeds | Depreciation | Additional dep. | Closing WDV | STCG u/s 50 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| computers | 40% | 54,000.00 | 0.00 | 1,00,000.00 | 0.00 | 41,600.00 | 0.00 | 1,12,400.00 |  |
| furniture | 10% | 2,18,700.00 | 0.00 | 0.00 | 0.00 | 21,870.00 | 0.00 | 1,96,830.00 |  |

## Summary

| Item | Amount |
| --- | ---: |
| Depreciation as per books (add back in tax computation) | 1,23,730.05 |
| Depreciation as per Income-tax Act (deduct) | 63,470.00 |
| Closing net block (books, excluding land) | 2,76,269.95 |
| Closing WDV (tax) | 3,09,230.00 |
| Timing difference (books - tax) | (32,960.05) |
| Deferred tax asset at 25.17% | 8,295.39 |

Deferred tax expense for the year = closing deferred tax above less the opening balance in the books (AS 22). Recognise a deferred tax asset on losses only with virtual certainty.

Depreciation voucher written to working\depreciation_voucher.json - post with: books.py post . --file working\depreciation_voucher.json

Wrote fixed_assets_next_year.csv and it_blocks_next_year.csv (books.py close-year carries them forward).
