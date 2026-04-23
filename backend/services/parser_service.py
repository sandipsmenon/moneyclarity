"""
Statement parsing logic extracted from dashboard.py.
Handles CSV and XLSX bank statements, auto-detects columns,
categorizes transactions by keyword.
"""

import io
from typing import Optional

import pandas as pd

CATEGORIES: dict[str, list[str]] = {
    "Food & Dining": ["zomato", "swiggy", "blinkit", "zepto", "dunzo", "dominos", "pizza"],
    "Transport": ["uber", "ola", "metro", "irctc", "rapido", "redbus", "petrol", "fuel"],
    "Shopping": ["amazon", "flipkart", "myntra", "ajio", "nykaa", "meesho", "snapdeal"],
    "Utilities": ["electricity", "water", "jio", "airtel", "vi ", "bsnl", "gas bill", "tata power"],
    "Entertainment": ["netflix", "spotify", "hotstar", "prime video", "zee5", "youtube", "pvr", "inox"],
    "Healthcare": ["pharmacy", "hospital", "clinic", "apollo", "medplus", "1mg", "practo", "netmeds"],
    "Rent & Housing": ["rent", "maintenance", "society", "nobroker", "magicbricks"],
    "Investments": ["mutual fund", "sip", "zerodha", "groww", "kuvera", "nps", "ppf", "fd ", "rd "],
    "Salary / Income": ["salary", "payroll", "neft cr", "imps cr", "stipend", "freelance"],
    "UPI / GPay": ["upi", "phonepe", "gpay", "paytm", "bhim", "google pay"],
    "Credit Card Bill": ["hdfc bank credit", "icici credit", "axis bank credit", "sbi card"],
    "Subscriptions": ["adobe", "notion", "github", "aws", "digitalocean", "hostinger"],
}


def categorize(description: str) -> str:
    desc_lower = str(description).lower()
    for cat, keywords in CATEGORIES.items():
        for kw in keywords:
            if kw in desc_lower:
                return cat
    return "Other"


def _infer_columns(df: pd.DataFrame) -> Optional[dict[str, str]]:
    """Map raw column names to canonical {date, description, debit, credit, amount}."""
    cols = {c.lower().strip(): c for c in df.columns}
    mapping: dict[str, str] = {}

    # Date
    for candidate in ["date", "txn date", "transaction date", "value date", "posting date"]:
        if candidate in cols:
            mapping["date"] = cols[candidate]
            break

    # Description
    for candidate in ["description", "narration", "particulars", "remarks", "details", "transaction details"]:
        if candidate in cols:
            mapping["description"] = cols[candidate]
            break

    # Debit / Credit split columns
    for candidate in ["debit", "debit amount", "withdrawal", "withdrawal (dr.)", "dr"]:
        if candidate in cols:
            mapping["debit"] = cols[candidate]
            break

    for candidate in ["credit", "credit amount", "deposit", "deposit (cr.)", "cr"]:
        if candidate in cols:
            mapping["credit"] = cols[candidate]
            break

    # Single amount column
    for candidate in ["amount", "transaction amount", "txn amount"]:
        if candidate in cols:
            mapping["amount"] = cols[candidate]
            break

    if "date" not in mapping or "description" not in mapping:
        return None
    return mapping


def _parse_inr(val) -> float:
    if pd.isna(val) or val == "" or val is None:
        return 0.0
    s = str(val).replace(",", "").replace("₹", "").replace(" ", "").strip()
    try:
        return abs(float(s))
    except ValueError:
        return 0.0


def parse_statement(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """
    Parse a bank statement file (CSV or XLSX) and return a clean DataFrame with columns:
    date, description, debit, credit, category, type, month, source
    """
    ext = filename.lower().rsplit(".", 1)[-1]

    if ext in ("xlsx", "xls"):
        raw = pd.read_excel(io.BytesIO(file_bytes), header=None)
        # Find header row (first row with ≥3 non-null values)
        header_row = 0
        for i, row in raw.iterrows():
            if row.count() >= 3:
                header_row = i
                break
        df = pd.read_excel(io.BytesIO(file_bytes), header=header_row)
    elif ext == "csv":
        # Try multiple encodings
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                df = pd.read_csv(io.BytesIO(file_bytes), encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError("Cannot decode CSV with supported encodings")
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    df.dropna(how="all", inplace=True)
    df.columns = [str(c).strip() for c in df.columns]

    col_map = _infer_columns(df)
    if col_map is None:
        raise ValueError("Could not identify required columns (date, description) in file")

    result = pd.DataFrame()
    result["date"] = pd.to_datetime(df[col_map["date"]], dayfirst=True, errors="coerce")
    result["description"] = df[col_map["description"]].astype(str)
    result.dropna(subset=["date"], inplace=True)

    if "debit" in col_map and "credit" in col_map:
        result["debit"] = df[col_map["debit"]].apply(_parse_inr)
        result["credit"] = df[col_map["credit"]].apply(_parse_inr)
    elif "amount" in col_map:
        raw_amounts = df[col_map["amount"]].astype(str)
        result["debit"] = raw_amounts.apply(
            lambda v: _parse_inr(v) if not str(v).startswith("+") else 0.0
        )
        result["credit"] = raw_amounts.apply(
            lambda v: _parse_inr(v) if str(v).startswith("+") else 0.0
        )
    else:
        result["debit"] = 0.0
        result["credit"] = 0.0

    result["category"] = result["description"].apply(categorize)
    result["type"] = result.apply(
        lambda r: "income" if r["credit"] > r["debit"] else "expense", axis=1
    )
    result["month"] = result["date"].dt.to_period("M").astype(str)
    result["source"] = filename

    return result.reset_index(drop=True)


def compute_monthly_summary(df: pd.DataFrame) -> list[dict]:
    """Aggregate parsed transactions into monthly summaries."""
    summaries = []
    for month, group in df.groupby("month"):
        income = group[group["type"] == "income"]["credit"].sum()
        expense = group[group["type"] == "expense"]["debit"].sum()
        cat_breakdown = (
            group[group["type"] == "expense"]
            .groupby("category")["debit"]
            .sum()
            .round(2)
            .to_dict()
        )
        summaries.append({
            "month": str(month),
            "income": round(float(income), 2),
            "expense": round(float(expense), 2),
            "net": round(float(income - expense), 2),
            "categories": cat_breakdown,
        })
    return sorted(summaries, key=lambda x: x["month"])
