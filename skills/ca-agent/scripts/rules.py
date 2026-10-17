"""Statutory rates, thresholds and due dates used by the CA Agent scripts.

Every number here comes from a Finance Act, a CBDT/CBIC/MCA notification or a rule, and
all of them change. When law changes, update this one file (and VERIFIED_ON) and every
script picks the new value up. Values marked "verify" were taken from secondary sources.

Financial years are written "2025-26" (1 Apr 2025 - 31 Mar 2026).
Income-tax Act, 1961 governs FY 2025-26 and earlier (assessment year 2026-27 = filed in 2026).
Income-tax Act, 2025 governs "tax year" 2026-27 onwards (1 Apr 2026 - 31 Mar 2027): same
slabs and broadly the same rules, renumbered sections (see references/income-tax.md).
"""
from datetime import date

VERIFIED_ON = "2026-10-17"

# ============================================================================ GST

STATE_CODES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh",
    "05": "Uttarakhand", "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur",
    "15": "Mizoram", "16": "Tripura", "17": "Meghalaya", "18": "Assam", "19": "West Bengal",
    "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "25": "Daman and Diu", "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra",
    "28": "Andhra Pradesh (Old)", "29": "Karnataka", "30": "Goa", "31": "Lakshadweep", "32": "Kerala",
    "33": "Tamil Nadu", "34": "Puducherry", "35": "Andaman and Nicobar Islands", "36": "Telangana",
    "37": "Andhra Pradesh", "38": "Ladakh", "96": "Foreign Country", "97": "Other Territory",
}

# QRMP GSTR-3B due date: 22nd for these states/UTs, 24th for the rest.
QRMP_22ND_STATES = {"22", "23", "24", "25", "26", "27", "29", "30", "31", "32", "33", "34", "35", "36", "37"}

# GST 2.0 (56th GST Council): 5% / 18% / 40% slabs w.e.f. 22-Sep-2025; 12% and 28% largely
# abolished. Special rates (0.1%, 0.25%, 1.5%, 3%) continue for specific goods.
GST2_EFFECTIVE = date(2025, 9, 22)
GST_RATES_VALID = {0, 0.1, 0.25, 1, 1.5, 3, 5, 6, 7.5, 12, 18, 28, 40}
GST_RATES_LEGACY_AFTER_GST2 = {12, 28}  # warn if used on supplies after GST2_EFFECTIVE

B2CL_THRESHOLD = 100000  # inter-state B2C invoice value above which GSTR-1 table 5 applies (w.e.f. 1-Aug-2024)

GST_INTEREST_LATE_PAYMENT = 0.18   # p.a. on net cash liability, sec 50(1)
GST_INTEREST_EXCESS_ITC = 0.24     # p.a. on ITC wrongly availed AND utilised, sec 50(3)

# GSTR-3B / GSTR-1 late fee (CGST+SGST combined, per day) and caps by previous-year AATO.
GST_LATE_FEE_PER_DAY = 50
GST_LATE_FEE_PER_DAY_NIL = 20
GST_LATE_FEE_CAPS = [(15000000, 2000), (50000000, 5000), (None, 10000)]  # AATO up to 1.5 cr, 5 cr, above
GST_LATE_FEE_CAP_NIL = 500

GST_DUE_DAY = {
    "gstr1_monthly": 11, "gstr1_qrmp": 13, "iff": 13, "gstr3b_monthly": 20,
    "pmt06": 25, "cmp08": 18, "gstr7": 10, "gstr8": 10,
}
GSTR9_MANDATORY_ABOVE = 20000000   # annual return mandatory above AATO 2 crore
GSTR9C_MANDATORY_ABOVE = 50000000  # reconciliation statement above AATO 5 crore
E_INVOICE_THRESHOLD = 50000000     # e-invoicing mandatory if AATO in any FY since 2017-18 exceeds 5 crore
E_INVOICE_30_DAY_LIMIT_AATO = 100000000  # AATO >= 10 cr: IRN must be generated within 30 days of invoice
E_WAY_BILL_THRESHOLD = 50000       # consignment value
HSN_DIGITS = [(50000000, 4), (None, 6)]  # AATO up to 5 cr: 4-digit HSN in GSTR-1; above: 6-digit

# ============================================================================ Income tax

CESS = 0.04

# Slabs as (upper limit or None, rate). "2026-27" = tax year 2026-27 under the 2025 Act
# (Budget 2026 made no slab change).
_NEW_2025 = [(400000, 0.0), (800000, 0.05), (1200000, 0.10), (1600000, 0.15),
             (2000000, 0.20), (2400000, 0.25), (None, 0.30)]
_NEW_2024 = [(300000, 0.0), (700000, 0.05), (1000000, 0.10), (1200000, 0.15),
             (1500000, 0.20), (None, 0.30)]
_OLD = {
    "normal": [(250000, 0.0), (500000, 0.05), (1000000, 0.20), (None, 0.30)],
    "senior": [(300000, 0.0), (500000, 0.05), (1000000, 0.20), (None, 0.30)],        # 60-79 years
    "super_senior": [(500000, 0.0), (1000000, 0.20), (None, 0.30)],                  # 80+ years
}

INDIVIDUAL = {
    "2024-25": {
        "new": {"slabs": _NEW_2024, "std_deduction": 75000, "rebate_limit": 700000, "rebate_max": 25000, "surcharge_cap": 0.25},
        "old": {"slabs": _OLD, "std_deduction": 50000, "rebate_limit": 500000, "rebate_max": 12500},
    },
    "2025-26": {
        "new": {"slabs": _NEW_2025, "std_deduction": 75000, "rebate_limit": 1200000, "rebate_max": 60000, "surcharge_cap": 0.25},
        "old": {"slabs": _OLD, "std_deduction": 50000, "rebate_limit": 500000, "rebate_max": 12500},
    },
    "2026-27": {
        "new": {"slabs": _NEW_2025, "std_deduction": 75000, "rebate_limit": 1200000, "rebate_max": 60000, "surcharge_cap": 0.25},
        "old": {"slabs": _OLD, "std_deduction": 50000, "rebate_limit": 500000, "rebate_max": 12500},
    },
}

# HRA exemption, rule 2A: least of HRA received, rent less 10% of salary, and 50% (metro) / 40% of salary,
# where salary = basic + DA forming part of retirement benefits (+ turnover commission).
HRA_METRO_CITIES = {"2025-26": ["Delhi", "Mumbai", "Kolkata", "Chennai"]}  # later years: verify the rules under the 2025 Act
HRA_METRO_PCT, HRA_OTHER_PCT, HRA_RENT_EXCESS_PCT = 0.50, 0.40, 0.10

# Surcharge for individuals/HUF/AOP: (income above, rate). Capped at 15% on 111A/112A/112/dividend income.
SURCHARGE_INDIVIDUAL = [(5000000, 0.10), (10000000, 0.15), (20000000, 0.25), (50000000, 0.37)]
SURCHARGE_SPECIAL_INCOME_CAP = 0.15

# Capital gains on transfers on/after 23-Jul-2024.
CG_RATES = {"stcg_111a": 0.20, "ltcg_112a": 0.125, "ltcg_112a_exemption": 125000, "ltcg_112": 0.125}

COMPANY = {
    "normal_rate_small": 0.25,             # if turnover/gross receipts of FY-2 <= 400 crore
    "normal_rate": 0.30,
    "small_turnover_limit": 4000000000,
    "surcharge_normal": [(10000000, 0.07), (100000000, 0.12)],   # above 1 cr: 7%, above 10 cr: 12%
    "115BAA": {"rate": 0.22, "surcharge": 0.10},   # no MAT, no specified deductions/additional depreciation
    "115BAB": {"rate": 0.15, "surcharge": 0.10},   # new manufacturing cos. that began production by 31-3-2024
    # MAT on book profit (old/normal regime only). Budget 2026: 14% and MAT becomes a final tax
    # (no new MAT credit) from tax year 2026-27; brought-forward credit set-off capped (verify).
    "mat_rate": {"2024-25": 0.15, "2025-26": 0.15, "2026-27": 0.14},
}

FIRM = {"rate": 0.30, "surcharge": [(10000000, 0.12)]}  # partnership firms and LLPs

# Advance tax instalments (month, day, cumulative share). Sec 44AD/44ADA assessees: 100% by 15 Mar.
ADVANCE_TAX_SCHEDULE = [(6, 15, 0.15), (9, 15, 0.45), (12, 15, 0.75), (3, 15, 1.00)]
ADVANCE_TAX_THRESHOLD = 10000  # no advance tax if net tax liability below this

LATE_FILING_FEE = {"default": 5000, "small_income": 1000, "small_income_limit": 500000}  # 234F

# ITR due dates by financial year (the year the income was earned).
ITR_DUE_DATES = {
    "2025-26": {  # AY 2026-27, Income-tax Act 1961
        "non_audit": date(2026, 7, 31),
        "non_audit_business": date(2026, 8, 31),   # ITR-3/ITR-4 without audit (Finance Act 2026; verify)
        "audit": date(2026, 10, 31),
        "audit_extended": date(2026, 11, 21),      # CBDT extension reported Sep-2026 (verify)
        "transfer_pricing": date(2026, 11, 30),
        "tax_audit_report": date(2026, 9, 30),
        "tax_audit_report_extended": date(2026, 10, 21),  # verify
        "belated": date(2026, 12, 31),
        "revised": date(2027, 3, 31),              # 12-month window from Finance Act 2026; fee if late (verify)
    },
    "2026-27": {  # tax year 2026-27, Income-tax Act 2025 (statutory dates; watch for extensions)
        "non_audit": date(2027, 7, 31),
        "non_audit_business": date(2027, 8, 31),
        "audit": date(2027, 10, 31),
        "transfer_pricing": date(2027, 11, 30),
        "tax_audit_report": date(2027, 9, 30),
        "belated": date(2027, 12, 31),
        "revised": date(2028, 3, 31),
    },
}

TAX_AUDIT_LIMITS = {
    "business": 10000000,                # 1 crore
    "business_low_cash": 100000000,      # 10 crore if cash receipts and payments each <= 5%
    "profession": 5000000,               # 50 lakh (s.44AB(b))
    "profession_44ada_low_cash": 7500000,  # presumptive s.44ADA professionals with cash receipts <= 5%
}

PRESUMPTIVE = {
    "44AD": {"limit": 20000000, "limit_low_cash": 30000000, "rate_digital": 0.06, "rate_cash": 0.08},
    "44ADA": {"limit": 5000000, "limit_low_cash": 7500000, "rate": 0.50},
}

# TDS (resident payees). Rates for FY 2025-26 after Budget 2025 thresholds. Under the 2025 Act
# these are consolidated in section 393 (salary: s.392) with the same rates (verify per payment).
TDS_RATES = [
    {"section": "192", "nature": "Salary", "rate": "slab rates", "threshold": "basic exemption limit"},
    {"section": "192A", "nature": "Premature EPF withdrawal", "rate": "10%", "threshold": "50,000"},
    {"section": "193", "nature": "Interest on securities", "rate": "10%", "threshold": "10,000 (debentures)"},
    {"section": "194", "nature": "Dividend", "rate": "10%", "threshold": "10,000 per year"},
    {"section": "194A", "nature": "Interest other than on securities", "rate": "10%",
     "threshold": "Banks/co-op/post office 50,000 (senior citizens 1,00,000); others 10,000"},
    {"section": "194B", "nature": "Lottery / game show winnings", "rate": "30%", "threshold": "10,000 per transaction"},
    {"section": "194C", "nature": "Payment to contractors", "rate": "1% individual/HUF, 2% others",
     "threshold": "30,000 single bill or 1,00,000 in the year"},
    {"section": "194D", "nature": "Insurance commission", "rate": "2% (non-company), 10% (company)", "threshold": "20,000"},
    {"section": "194H", "nature": "Commission or brokerage", "rate": "2%", "threshold": "20,000"},
    {"section": "194I(a)", "nature": "Rent - plant, machinery, equipment", "rate": "2%", "threshold": "50,000 per month or part"},
    {"section": "194I(b)", "nature": "Rent - land, building, furniture", "rate": "10%", "threshold": "50,000 per month or part"},
    {"section": "194IA", "nature": "Purchase of immovable property", "rate": "1%", "threshold": "consideration >= 50 lakh"},
    {"section": "194IB", "nature": "Rent paid by individuals/HUF not under audit", "rate": "2%", "threshold": "50,000 per month"},
    {"section": "194J(a)", "nature": "Fees for technical services, call centre, film royalty", "rate": "2%", "threshold": "50,000"},
    {"section": "194J(b)", "nature": "Professional fees, royalty, non-compete", "rate": "10%",
     "threshold": "50,000 (director sitting fees/commission: no threshold)"},
    {"section": "194K", "nature": "Income from mutual fund units", "rate": "10%", "threshold": "10,000"},
    {"section": "194M", "nature": "Contract/commission/professional paid by individuals not under audit", "rate": "2%", "threshold": "50 lakh"},
    {"section": "194O", "nature": "E-commerce operator payments", "rate": "0.1%", "threshold": "5 lakh (individual/HUF sellers)"},
    {"section": "194Q", "nature": "Purchase of goods (buyer turnover > 10 cr)", "rate": "0.1%", "threshold": "above 50 lakh per seller in the year"},
    {"section": "194R", "nature": "Business perquisites/benefits", "rate": "10%", "threshold": "20,000"},
    {"section": "194S", "nature": "Transfer of virtual digital assets", "rate": "1%", "threshold": "50,000 (specified persons) / 10,000"},
    {"section": "194T", "nature": "Salary, commission, interest etc. paid by firm to partner", "rate": "10%", "threshold": "20,000"},
    {"section": "195", "nature": "Payments to non-residents", "rate": "rates in force or DTAA (with TRC, Form 10F)", "threshold": "none"},
    {"section": "206AA", "nature": "Payee without PAN", "rate": "higher of twice the rate or 20% (5% for 194O/194Q)", "threshold": "-"},
]

TDS_DUE = {
    "deposit_day": 7,                 # of next month; March deductions by 30 April
    "deposit_march": (4, 30),
    "return_quarterly": {"Q1": (7, 31), "Q2": (10, 31), "Q3": (1, 31), "Q4": (5, 31)},  # 24Q/26Q
    "tcs_return_quarterly": {"Q1": (7, 15), "Q2": (10, 15), "Q3": (1, 15), "Q4": (5, 15)},  # 27EQ
    "interest_late_deduction": 0.01,  # per month or part, 201(1A)
    "interest_late_deposit": 0.015,
    "late_fee_per_day": 200,          # 234E, capped at the TDS amount
}

# ============================================================================ Depreciation

# Income-tax Act WDV block rates (Appendix I). Additional depreciation 20% on new P&M for
# manufacturers under the normal regime only (not under 115BAA/115BAB/115BAC).
IT_BLOCK_RATES = {
    "building_residential": 0.05, "building_other": 0.10, "building_temporary": 0.40,
    "furniture": 0.10, "plant_machinery": 0.15, "motor_car": 0.15, "motor_vehicle_hire": 0.30,
    "computers": 0.40, "books": 0.40, "pollution_control": 0.40, "energy_saving": 0.40,
    "aircraft": 0.40, "ships": 0.20, "intangibles": 0.25,
}
ADDITIONAL_DEPRECIATION = 0.20
HALF_RATE_DAYS = 180  # asset put to use for less than 180 days in the year -> half the rate

# Companies Act 2013 Schedule II useful lives (years); residual value up to 5% of cost.
SCHEDULE_II_LIFE = {
    "building_factory": 30, "building_rcc": 60, "building_non_rcc": 30, "fences_wells": 5,
    "building_temporary": 3, "roads_rcc": 10, "roads_other": 5, "roads_non_carpeted": 3,
    "plant_machinery": 15, "plant_continuous_process": 25, "furniture": 10, "furniture_hotel_school": 8,
    "motorcycle": 10, "motor_vehicle": 8, "motor_vehicle_hire": 6, "office_equipment": 5,
    "computer_end_user": 3, "server_network": 6, "electrical_installation": 10, "lab_equipment": 10,
    "ships": 28, "aircraft": 20,
}
RESIDUAL_VALUE_PCT = 0.05

# ============================================================================ Companies Act / ROC

SMALL_COMPANY = {"paid_up_capital": 100000000, "turnover": 1000000000}  # 10 cr / 100 cr w.e.f. 1-Dec-2025
ROC = {
    "agm_months_after_fy": 6,           # AGM by 30 September
    "aoc4_days_after_agm": 30,
    "mgt7_days_after_agm": 60,
    "adt1_days_after_agm": 15,
    "dpt3": (6, 30),                    # return of deposits / outstanding loans, by 30 June
    "msme1": [(4, 30), (10, 31)],       # half-yearly, if dues to micro/small suppliers > 45 days
    "dir3_kyc": (6, 30),                # once every 3 FYs from FY 2025-26 cycle (G.S.R. 943(E))
    "llp_form11": (5, 30), "llp_form8": (10, 30),
}
