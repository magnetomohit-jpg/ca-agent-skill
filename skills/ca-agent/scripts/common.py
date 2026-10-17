"""Shared helpers for the CA Agent scripts.

Money is always handled as Decimal (never float) and rounded half-up to paise.
A "books folder" holds one entity's records for one financial year:

    company.json            entity profile (name, PAN, GSTIN, state code, FY ...)
    chart_of_accounts.csv   account -> Schedule III line mapping
    journal.csv             double-entry vouchers (one row per voucher line)
    sales_register.csv      invoice-line GST data for outward supplies
    purchase_register.csv   invoice-line GST data for inward supplies
    fixed_assets.csv        asset register for depreciation

Only the standard library is required; openpyxl is used for .xlsx output when present.
"""
from __future__ import annotations

import csv
import difflib
import json
import re
import sys
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

ZERO = Decimal("0")
PAISA = Decimal("0.01")

# Windows consoles default to cp1252; the reports contain ₹ and other non-ASCII text.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


class BooksError(Exception):
    """Raised for problems the user must fix in their data (shown without a traceback)."""


# --------------------------------------------------------------------------- money

def D(value) -> Decimal:
    """Parse an amount. Accepts 1234.5, '1,23,456.50', '₹ 500', '(250)' (negative) and blanks (zero)."""
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise BooksError(f"Not an amount: {value!r}")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    s = str(value).strip()
    if s in {"", "-", "--"}:
        return ZERO
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    for token in ("₹", "Rs.", "Rs", "INR", ",", " "):
        s = s.replace(token, "")
    if s.startswith("-"):
        negative = not negative
        s = s[1:]
    try:
        amount = Decimal(s)
    except InvalidOperation:
        raise BooksError(f"Not an amount: {value!r}") from None
    return -amount if negative else amount


def money(value) -> Decimal:
    return D(value).quantize(PAISA, rounding=ROUND_HALF_UP)


def rupee(value) -> Decimal:
    """Round to the nearest rupee (GST and income-tax amounts are paid in whole rupees)."""
    return D(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def round_down_100(value) -> Decimal:
    """Interest u/s 234A/B/C is computed on amounts rounded down to the nearest hundred."""
    v = D(value)
    if v <= 0:
        return ZERO
    return (v // 100) * 100


def round_to_10(value) -> Decimal:
    """Total income is rounded off to the nearest multiple of ten rupees (sec 288A / 1961 Act)."""
    v = D(value)
    return (v / 10).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * 10


def inr(value, decimals: int = 2, blank_zero: bool = False) -> str:
    """Format with Indian digit grouping: 12,34,567.00. Negatives shown in brackets."""
    v = money(value)
    if blank_zero and v == 0:
        return "-"
    negative = v < 0
    s = f"{abs(v):.{decimals}f}"
    whole, _, frac = s.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        head = re.sub(r"(\d)(?=(\d{2})+$)", r"\1,", head)
        whole = f"{head},{tail}"
    out = whole + (f".{frac}" if frac else "")
    return f"({out})" if negative else out


def jsonable(obj):
    """Convert Decimals/dates inside nested structures so json.dumps works."""
    if isinstance(obj, Decimal):
        return float(money(obj))
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    return obj


# --------------------------------------------------------------------------- dates

_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d-%b-%Y", "%d-%b-%y",
                 "%d %b %Y", "%d %B %Y", "%Y/%m/%d", "%d/%m/%y", "%d-%m-%y")


def parse_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value or "").strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise BooksError(f"Unrecognised date {value!r} (use YYYY-MM-DD)")


def fy_bounds(fy: str) -> tuple[date, date]:
    """'2025-26' -> (2025-04-01, 2026-03-31)."""
    m = re.fullmatch(r"(\d{4})-(\d{2}|\d{4})", fy.strip())
    if not m:
        raise BooksError(f"Financial year must look like 2025-26, got {fy!r}")
    start = int(m.group(1))
    return date(start, 4, 1), date(start + 1, 3, 31)


def fy_of(d: date) -> str:
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def next_fy(fy: str) -> str:
    start, _ = fy_bounds(fy)
    return f"{start.year + 1}-{str(start.year + 2)[-2:]}"


def month_end(d: date) -> date:
    nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def months_between_inclusive(start: date, end: date) -> int:
    """Months or part of a month from `start` to `end` (as used for interest u/s 234A/B/C)."""
    if end < start:
        return 0
    months = (end.year - start.year) * 12 + (end.month - start.month)
    return months + 1


def parse_period(spec: str) -> tuple[date, date, str]:
    """Accepts '2025-04' (month), '2025-26:Q1' (FY quarter), '2025-26' (FY) or 'YYYY-MM-DD..YYYY-MM-DD'."""
    s = spec.strip()
    if ".." in s:
        a, b = s.split("..", 1)
        return parse_date(a), parse_date(b), s
    m = re.fullmatch(r"(\d{4})-(\d{2})", s)
    if m and 1 <= int(m.group(2)) <= 12:
        first = date(int(m.group(1)), int(m.group(2)), 1)
        return first, month_end(first), first.strftime("%b %Y")
    m = re.fullmatch(r"(\d{4}-\d{2}):?[Qq]([1-4])", s)
    if m:
        fy_start, _ = fy_bounds(m.group(1))
        q = int(m.group(2))
        first = date(fy_start.year + (1 if q == 4 else 0), 4 + 3 * (q - 1) if q < 4 else 1, 1)
        last = month_end(date(first.year, first.month + 2, 1))
        return first, last, f"FY {m.group(1)} Q{q}"
    start, end = fy_bounds(s)
    return start, end, f"FY {s}"


# --------------------------------------------------------------------------- csv / io

def _norm_key(k: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (k or "").strip().lower()).strip("_")


def read_rows(path: Path | str, required: bool = True) -> list[dict]:
    p = Path(path)
    if not p.exists():
        if required:
            raise BooksError(f"File not found: {p}")
        return []
    with p.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        rows = []
        for i, raw in enumerate(reader, start=2):
            row = {_norm_key(k): (v.strip() if isinstance(v, str) else v) for k, v in raw.items() if k}
            if not any(v for v in row.values()):
                continue
            row["_line"] = i
            rows.append(row)
        return rows


def write_rows(path: Path | str, headers: list[str], rows: list[dict | list], append: bool = False) -> None:
    p = Path(path)
    exists = p.exists() and p.stat().st_size > 0
    with p.open("a" if append else "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if not (append and exists):
            w.writerow(headers)
        for r in rows:
            w.writerow([_cell(r.get(h, "")) for h in headers] if isinstance(r, dict) else [_cell(c) for c in r])


def _cell(v):
    if isinstance(v, Decimal):
        return f"{money(v):.2f}"
    if isinstance(v, date):
        return v.isoformat()
    return v


def load_json(path: Path | str) -> dict:
    p = Path(path)
    if str(path) == "-":
        return json.load(sys.stdin)
    if not p.exists():
        raise BooksError(f"File not found: {p}")
    with p.open(encoding="utf-8-sig") as fh:
        return json.load(fh)


def dump_json(obj, path: Path | str | None = None) -> str:
    text = json.dumps(jsonable(obj), indent=2, ensure_ascii=False)
    if path:
        Path(path).write_text(text + "\n", encoding="utf-8")
    return text


def md_table(headers: list[str], rows: list[list], right: set[int] | None = None) -> str:
    """Markdown table. Columns listed in `right` (or holding Decimals) are right-aligned and INR formatted."""
    right = set(right or [])
    for row in rows:
        for i, c in enumerate(row):
            if isinstance(c, Decimal):
                right.add(i)
    fmt_rows = [[inr(c) if isinstance(c, Decimal) else ("" if c is None else str(c)) for c in row] for row in rows]
    sep = ["---:" if i in right else "---" for i in range(len(headers))]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(sep) + " |"]
    lines += ["| " + " | ".join(c.replace("|", "\\|") for c in r) + " |" for r in fmt_rows]
    return "\n".join(lines)


def write_xlsx(path: Path | str, sheets: list[tuple[str, list[list]]]) -> bool:
    """Write simple sheets (first row bold). Returns False when openpyxl is not installed."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
        from openpyxl.utils import get_column_letter
    except ImportError:
        return False
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets:
        ws = wb.create_sheet(title=re.sub(r"[\\/*?:\[\]]", "-", name)[:31])
        widths: dict[int, int] = {}
        for r_idx, row in enumerate(rows, start=1):
            for c_idx, val in enumerate(row, start=1):
                if isinstance(val, Decimal):
                    val = float(money(val))
                cell = ws.cell(row=r_idx, column=c_idx, value=val)
                if isinstance(val, float):
                    cell.number_format = "#,##,##0.00;(#,##,##0.00);-"
                if r_idx == 1 or (isinstance(row[0], str) and row[0].isupper() and len(row[0]) > 3):
                    cell.font = Font(bold=True)
                widths[c_idx] = max(widths.get(c_idx, 8), min(len(str(val)) + 2, 70))
        for c_idx, w in widths.items():
            ws.column_dimensions[get_column_letter(c_idx)].width = w
    wb.save(path)
    return True


def emit(markdown: str, data: dict, args) -> None:
    """Common output handling: --json prints JSON; --out-dir writes report.md + report.json."""
    if getattr(args, "json", False):
        print(dump_json(data))
    else:
        print(markdown)
    out_dir = getattr(args, "out_dir", None)
    if out_dir:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        stem = getattr(args, "report_name", None) or "report"
        Path(out_dir, f"{stem}.md").write_text(markdown + "\n", encoding="utf-8")
        dump_json(data, Path(out_dir, f"{stem}.json"))


def run_cli(main) -> None:
    """Run a script's main(), turning BooksError into a clean message and exit code 2."""
    try:
        main()
    except BooksError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)


# --------------------------------------------------------------------------- Schedule III lines

# key: (statement, nature, label, section, cash-flow class)
LINES: dict[str, tuple[str, str, str, str, str | None]] = {
    "share_capital": ("BS", "equity", "Share capital", "Shareholders' funds", "financing"),
    "other_equity": ("BS", "equity", "Reserves and surplus", "Shareholders' funds", "financing"),
    "share_application_money": ("BS", "equity", "Share application money pending allotment", "Share application money pending allotment", "financing"),
    "lt_borrowings": ("BS", "liability", "Long-term borrowings", "Non-current liabilities", "financing"),
    "deferred_tax_liab": ("BS", "liability", "Deferred tax liabilities (net)", "Non-current liabilities", "deferred"),
    "other_lt_liabilities": ("BS", "liability", "Other long-term liabilities", "Non-current liabilities", "operating"),
    "lt_provisions": ("BS", "liability", "Long-term provisions", "Non-current liabilities", "operating"),
    "st_borrowings": ("BS", "liability", "Short-term borrowings", "Current liabilities", "financing"),
    "trade_payables_msme": ("BS", "liability", "Trade payables - total outstanding dues of micro and small enterprises", "Current liabilities", "operating"),
    "trade_payables_others": ("BS", "liability", "Trade payables - total outstanding dues of creditors other than micro and small enterprises", "Current liabilities", "operating"),
    "other_current_liabilities": ("BS", "liability", "Other current liabilities", "Current liabilities", "operating"),
    "st_provisions": ("BS", "liability", "Short-term provisions", "Current liabilities", "operating"),
    "ppe": ("BS", "asset", "Property, plant and equipment", "Non-current assets", "investing"),
    "intangible_assets": ("BS", "asset", "Intangible assets", "Non-current assets", "investing"),
    "cwip": ("BS", "asset", "Capital work-in-progress", "Non-current assets", "investing"),
    "intangible_under_dev": ("BS", "asset", "Intangible assets under development", "Non-current assets", "investing"),
    "nc_investments": ("BS", "asset", "Non-current investments", "Non-current assets", "investing"),
    "deferred_tax_asset": ("BS", "asset", "Deferred tax assets (net)", "Non-current assets", "deferred"),
    "lt_loans_advances": ("BS", "asset", "Long-term loans and advances", "Non-current assets", "operating"),
    "other_nc_assets": ("BS", "asset", "Other non-current assets", "Non-current assets", "operating"),
    "current_investments": ("BS", "asset", "Current investments", "Current assets", "investing"),
    "inventories": ("BS", "asset", "Inventories", "Current assets", "operating"),
    "trade_receivables": ("BS", "asset", "Trade receivables", "Current assets", "operating"),
    "cash_equivalents": ("BS", "asset", "Cash and cash equivalents", "Current assets", "cash"),
    "st_loans_advances": ("BS", "asset", "Short-term loans and advances", "Current assets", "operating"),
    "other_current_assets": ("BS", "asset", "Other current assets", "Current assets", "operating"),
    "revenue_operations": ("PL", "income", "Revenue from operations", "Income", None),
    "other_income": ("PL", "income", "Other income", "Income", None),
    "cost_materials": ("PL", "expense", "Cost of materials consumed", "Expenses", None),
    "purchases_stock": ("PL", "expense", "Purchases of stock-in-trade", "Expenses", None),
    "changes_inventories": ("PL", "expense", "Changes in inventories of finished goods, work-in-progress and stock-in-trade", "Expenses", None),
    "employee_benefits": ("PL", "expense", "Employee benefits expense", "Expenses", None),
    "finance_costs": ("PL", "expense", "Finance costs", "Expenses", None),
    "depreciation": ("PL", "expense", "Depreciation and amortisation expense", "Expenses", None),
    "other_expenses": ("PL", "expense", "Other expenses", "Expenses", None),
    "exceptional_items": ("PL", "expense", "Exceptional items", "Exceptional items", None),
    "current_tax": ("PL", "tax", "Current tax", "Tax expense", None),
    "deferred_tax": ("PL", "tax", "Deferred tax", "Tax expense", None),
}

VOUCHER_TYPES = {
    "opening": "OPN", "journal": "JV", "sales": "SAL", "purchase": "PUR", "receipt": "RCT",
    "payment": "PMT", "contra": "CON", "debit note": "DN", "credit note": "CN", "adjustment": "ADJ",
}

JOURNAL_HEADERS = ["date", "voucher_no", "voucher_type", "account", "debit", "credit", "narration", "ref"]
COA_HEADERS = ["code", "account", "line", "tag", "description"]


# --------------------------------------------------------------------------- books folder

class Books:
    """One entity's books for one financial year, loaded from a books folder."""

    def __init__(self, folder: Path | str):
        self.dir = Path(folder)
        if not (self.dir / "company.json").exists():
            raise BooksError(f"{self.dir} is not a books folder (company.json missing). "
                             "Create one with: books.py init <folder> --name ... --fy ...")
        self.company = load_json(self.dir / "company.json")
        self.fy = self.company.get("fy") or ""
        self.fy_start, self.fy_end = fy_bounds(self.fy)
        self.accounts: dict[str, dict] = {}
        for row in read_rows(self.dir / "chart_of_accounts.csv"):
            name = row.get("account", "")
            line = row.get("line", "")
            if not name:
                continue
            if line not in LINES:
                raise BooksError(f"chart_of_accounts.csv line {row['_line']}: account {name!r} has unknown "
                                 f"line {line!r}. Valid lines: {', '.join(LINES)}")
            row["tags"] = {t.strip().lower() for t in (row.get("tag") or "").split(";") if t.strip()}
            self.accounts[name.lower()] = row
        self.journal = self._load_journal()

    # -- accounts
    def account(self, name: str) -> dict:
        acc = self.accounts.get((name or "").strip().lower())
        if acc is None:
            close = difflib.get_close_matches((name or "").lower(), list(self.accounts), n=3, cutoff=0.5)
            hint = f" Did you mean: {', '.join(self.accounts[c]['account'] for c in close)}?" if close else ""
            raise BooksError(f"Account {name!r} is not in chart_of_accounts.csv.{hint} "
                             "Add it with: books.py add-account")
        return acc

    def accounts_with_tag(self, tag: str) -> list[dict]:
        return [a for a in self.accounts.values() if tag in a["tags"]]

    def statement(self, name: str) -> str:
        return LINES[self.account(name)["line"]][0]

    # -- journal
    def _load_journal(self) -> list[dict]:
        lines = []
        for row in read_rows(self.dir / "journal.csv", required=False):
            row["date"] = parse_date(row.get("date"))
            row["debit"] = money(row.get("debit"))
            row["credit"] = money(row.get("credit"))
            row["voucher_type"] = (row.get("voucher_type") or "Journal").strip()
            lines.append(row)
        return lines

    def balances(self, start: date | None = None, end: date | None = None,
                 exclude_types: set[str] | None = None) -> dict[str, Decimal]:
        """Signed (debit-positive) balance per account (canonical name) for entries in [start, end]."""
        out: dict[str, Decimal] = {}
        excl = {t.lower() for t in (exclude_types or set())}
        for ln in self.journal:
            if start and ln["date"] < start:
                continue
            if end and ln["date"] > end:
                continue
            if ln["voucher_type"].lower() in excl:
                continue
            acc = self.accounts.get(ln["account"].lower())
            key = acc["account"] if acc else ln["account"]
            out[key] = out.get(key, ZERO) + ln["debit"] - ln["credit"]
        return out

    def opening_balances(self) -> dict[str, Decimal]:
        """Balances brought forward: the sum of 'Opening' vouchers."""
        return self._sum(lambda ln: ln["voucher_type"].lower() == "opening")

    def _sum(self, pred) -> dict[str, Decimal]:
        out: dict[str, Decimal] = {}
        for ln in self.journal:
            if pred(ln):
                acc = self.accounts.get(ln["account"].lower())
                key = acc["account"] if acc else ln["account"]
                out[key] = out.get(key, ZERO) + ln["debit"] - ln["credit"]
        return out

    def vouchers(self) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for ln in self.journal:
            out.setdefault(ln.get("voucher_no") or f"line-{ln['_line']}", []).append(ln)
        return out

    def registers(self, name: str) -> list[dict]:
        return read_rows(self.dir / f"{name}.csv", required=False)


def state_code_of(value) -> str:
    """'27', '27-Maharashtra', 'Maharashtra' or a GSTIN -> '27'."""
    from rules import STATE_CODES  # local import keeps common.py free of rule data
    s = str(value or "").strip()
    if not s:
        return ""
    m = re.match(r"^(\d{1,2})\b", s)
    if m:
        return m.group(1).zfill(2)
    by_name = {v.lower(): k for k, v in STATE_CODES.items()}
    if s.lower() in by_name:
        return by_name[s.lower()]
    raise BooksError(f"Unknown place of supply / state {value!r}; use the 2-digit GST state code")


_GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_checksum(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14.upper()):
        product = _GSTIN_CHARS.index(ch) * (1 if i % 2 == 0 else 2)
        total += product // 36 + product % 36
    return _GSTIN_CHARS[(36 - total % 36) % 36]


def gstin_problem(gstin: str) -> str | None:
    """Return a reason the GSTIN is malformed, or None if it passes format and checksum."""
    g = (gstin or "").strip().upper()
    if not re.fullmatch(r"\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z][A-Z0-9][0-9A-Z]", g):
        return "does not match the 15-character GSTIN pattern"
    if gstin_checksum(g[:14]) != g[14]:
        return f"checksum digit should be {gstin_checksum(g[:14])}"
    return None


def pan_problem(pan: str) -> str | None:
    if not re.fullmatch(r"[A-Z]{5}\d{4}[A-Z]", (pan or "").strip().upper()):
        return "PAN must be 5 letters, 4 digits, 1 letter"
    return None
