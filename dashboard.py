"""
Money Clarity — Professional Dashboard
Run: streamlit run dashboard.py
"""

import asyncio
import base64
import re
from io import BytesIO, StringIO

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ── Auth ──────────────────────────────────────────────────────────────────────
try:
    from streamlit_app.auth_component import (
        handle_auth_callback,
        init_auth_state,
        is_authenticated,
        get_access_token,
        get_user,
        logout,
        render_login_ui,
    )
    from streamlit_app.api_client import ApiClient
    SUPABASE_AUTH_AVAILABLE = True
except ImportError:
    SUPABASE_AUTH_AVAILABLE = False

try:
    from google_auth_oauthlib.flow import Flow
    from googleapiclient.discovery import build
    GOOGLE_LIBS_AVAILABLE = True
except ImportError:
    GOOGLE_LIBS_AVAILABLE = False

try:
    import openai as _openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# ══════════════════════════════════════════════════════════════════════════════
# DESIGN SYSTEM
# ══════════════════════════════════════════════════════════════════════════════

C_INCOME   = "#10B981"
C_EXPENSE  = "#EF4444"
C_SAVINGS  = "#3B82F6"
C_ACCENT   = "#6366F1"
C_AMBER    = "#F59E0B"
C_TEAL     = "#14B8A6"

PALETTE = [C_ACCENT, C_INCOME, C_EXPENSE, C_AMBER, "#8B5CF6",
           C_TEAL, "#EC4899", C_SAVINGS, "#06B6D4", "#84CC16"]

CHART_CONFIG = {"displayModeBar": False, "responsive": True}

BASE_LAYOUT = dict(
    plot_bgcolor="#FFFFFF",
    paper_bgcolor="#FFFFFF",
    font=dict(family="Inter, system-ui, sans-serif", size=11, color="#94A3B8"),
    margin=dict(t=12, b=44, l=0, r=0),
    legend=dict(
        orientation="h", yanchor="bottom", y=-0.28,
        xanchor="center", x=0.5,
        font=dict(size=10.5, color="#64748B"),
        bgcolor="rgba(0,0,0,0)", borderwidth=0,
    ),
    hoverlabel=dict(
        bgcolor="#0F172A", font_color="#FFFFFF",
        font_size=11.5, bordercolor="#0F172A",
    ),
    xaxis=dict(
        showgrid=False, linecolor="#E2E8F0", linewidth=1,
        tickfont=dict(size=10.5, color="#94A3B8"),
    ),
    yaxis=dict(
        gridcolor="#F8FAFC", gridwidth=1,
        linecolor="rgba(0,0,0,0)",
        tickfont=dict(size=10.5, color="#94A3B8"),
    ),
)


def apply_theme(fig, height=320, show_legend=True, yprefix="₹"):
    layout = {**BASE_LAYOUT, "height": height}
    if not show_legend:
        layout["legend"] = dict(visible=False)
    if yprefix:
        layout["yaxis"] = {**BASE_LAYOUT["yaxis"], "tickprefix": yprefix}
    fig.update_layout(**layout)
    return fig


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* ── Global ─────────────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, system-ui, sans-serif !important;
}
.stApp { background: #F8FAFC !important; }
.block-container {
    padding-top: 2rem !important;
    padding-left: 2.25rem !important;
    padding-right: 2.25rem !important;
    padding-bottom: 4rem !important;
    max-width: 1400px !important;
}

/* ── Sidebar ────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: #0F172A !important;
    border-right: none !important;
    min-width: 230px !important;
}
[data-testid="stSidebar"] .block-container {
    padding: 1.75rem 1.25rem !important;
}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] div { color: #94A3B8 !important; }
[data-testid="stSidebar"] strong { color: #E2E8F0 !important; font-weight: 600; }
[data-testid="stSidebar"] .stButton > button {
    background: rgba(99,102,241,0.12) !important;
    color: #A5B4FC !important;
    border: 1px solid rgba(99,102,241,0.25) !important;
    border-radius: 8px !important;
    font-size: 0.8rem !important; font-weight: 500 !important;
    padding: 0.45rem 0.75rem !important;
    width: 100% !important;
    transition: all 0.15s !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(99,102,241,0.22) !important;
    border-color: rgba(99,102,241,0.45) !important;
    color: #C7D2FE !important;
}

/* ── Buttons ─────────────────────────────────────────────── */
.stButton > button {
    font-family: 'Inter', system-ui, sans-serif !important;
    font-size: 0.875rem !important; font-weight: 500 !important;
    border-radius: 8px !important;
    padding: 0.5rem 1.25rem !important;
    border: 1px solid #E2E8F0 !important;
    background: #FFFFFF !important;
    color: #475569 !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.05) !important;
    transition: all 0.15s ease !important;
}
.stButton > button:hover {
    border-color: #CBD5E1 !important;
    box-shadow: 0 2px 4px rgba(0,0,0,0.08) !important;
    color: #0F172A !important;
}
.stButton > button[kind="primary"] {
    background: #6366F1 !important;
    border-color: #6366F1 !important;
    color: white !important;
    box-shadow: 0 1px 3px rgba(99,102,241,0.35) !important;
}
.stButton > button[kind="primary"]:hover {
    background: #4F46E5 !important;
    border-color: #4F46E5 !important;
    box-shadow: 0 4px 12px rgba(99,102,241,0.35) !important;
    transform: translateY(-1px);
}

/* ── Text inputs ──────────────────────────────────────────── */
.stTextInput > div > input, .stTextArea > div > textarea {
    font-family: 'Inter', system-ui, sans-serif !important;
    font-size: 0.875rem !important;
    border-radius: 8px !important;
    border: 1px solid #E2E8F0 !important;
    background: #FFFFFF !important;
    color: #0F172A !important;
}
.stTextInput > div > input:focus {
    border-color: #6366F1 !important;
    box-shadow: 0 0 0 3px rgba(99,102,241,0.1) !important;
}
.stTextInput label, .stTextArea label { color: #475569 !important; font-size: 0.82rem !important; font-weight: 500 !important; }

/* ── Tabs ────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 2px solid #E2E8F0 !important;
    gap: 0 !important; padding: 0 !important;
}
.stTabs [data-baseweb="tab"] {
    font-family: 'Inter', system-ui, sans-serif !important;
    font-size: 0.875rem !important; font-weight: 500 !important;
    color: #94A3B8 !important;
    padding: 0.625rem 1rem !important;
    border-bottom: 2px solid transparent !important;
    margin-bottom: -2px !important; background: transparent !important;
}
.stTabs [aria-selected="true"] {
    color: #0F172A !important;
    border-bottom-color: #6366F1 !important;
    font-weight: 600 !important;
}

/* ── Expander ────────────────────────────────────────────── */
.stExpander {
    border: 1px solid #E2E8F0 !important;
    border-radius: 12px !important;
    background: #FFFFFF !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
    overflow: hidden !important;
}
.stExpander summary { padding: 1rem 1.25rem !important; }
.stExpander summary p { font-weight: 500 !important; color: #0F172A !important; font-size: 0.9rem !important; }

/* ── File uploader ──────────────────────────────────────── */
[data-testid="stFileUploaderDropzone"] {
    border: 2px dashed #CBD5E1 !important;
    border-radius: 10px !important;
    background: #F8FAFC !important;
    transition: border-color 0.15s, background 0.15s !important;
}
[data-testid="stFileUploaderDropzone"]:hover {
    border-color: #6366F1 !important;
    background: #EEF2FF !important;
}

/* ── Alerts ─────────────────────────────────────────────── */
.stAlert { border-radius: 10px !important; border: 1px solid #E2E8F0 !important; }

/* ── Multiselect ─────────────────────────────────────────── */
[data-baseweb="select"] > div:first-child {
    border-radius: 8px !important;
    border-color: #E2E8F0 !important;
    font-size: 0.85rem !important;
}

/* ── Dataframe ──────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border-radius: 10px !important;
    border: 1px solid #E2E8F0 !important;
    overflow: hidden !important;
}
[data-testid="stDataFrame"] thead th {
    background: #F8FAFC !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    color: #64748B !important;
    letter-spacing: 0.04em !important;
}

/* ── Chart containers ────────────────────────────────────── */
[data-testid="stPlotlyChart"] {
    background: #FFFFFF;
    border-radius: 12px;
    border: 1px solid #E2E8F0;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    overflow: hidden;
    padding: 0 !important;
    margin-bottom: 1rem;
}

/* ── Download button ─────────────────────────────────────── */
.stDownloadButton > button {
    font-size: 0.82rem !important;
    padding: 0.4rem 1rem !important;
    border-radius: 8px !important;
}

/* ── Caption ─────────────────────────────────────────────── */
.stCaptionContainer p { font-size: 0.75rem !important; color: #94A3B8 !important; }

/* ── Mobile ──────────────────────────────────────────────── */
@media (max-width: 768px) {
    .block-container { padding-left: 1rem !important; padding-right: 1rem !important; }
    .kpi-grid { grid-template-columns: repeat(2, 1fr) !important; }
    [data-testid="stColumns"] { flex-direction: column !important; }
    [data-testid="stColumn"]  { width: 100% !important; flex: 1 1 100% !important; min-width: 100% !important; }
    [data-testid="stPlotlyChart"] { border-radius: 10px; }
    .modebar { display: none !important; }
}
</style>
"""

# ══════════════════════════════════════════════════════════════════════════════
# PAGE CONFIG & AUTH
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Money Clarity",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(CSS, unsafe_allow_html=True)

if SUPABASE_AUTH_AVAILABLE:
    init_auth_state()
    handle_auth_callback()

    if not is_authenticated():
        # ── Login page ──────────────────────────────────────────────────────
        st.html("""
        <div style="max-width:420px;margin:5rem auto 0;text-align:center;">
            <div style="width:52px;height:52px;background:linear-gradient(135deg,#6366F1,#818CF8);
                        border-radius:14px;display:flex;align-items:center;justify-content:center;
                        font-size:1.5rem;margin:0 auto 1.25rem;">💰</div>
            <h1 style="font-size:1.6rem;font-weight:700;color:#0F172A;letter-spacing:-0.03em;margin-bottom:0.4rem;">
                Money Clarity
            </h1>
            <p style="color:#64748B;font-size:0.9rem;margin-bottom:2rem;">
                Your personal finance dashboard
            </p>
        </div>
        """)
        render_login_ui()
        st.stop()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    if SUPABASE_AUTH_AVAILABLE:
        user = get_user()
        email = user.email if user else "User"
    else:
        email = "demo@example.com"

    initial = email[0].upper()
    name_part = email.split("@")[0].replace(".", " ").title()

    st.html(f"""
    <div style="margin-bottom:2rem;">
        <div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:1.5rem;">
            <div style="width:34px;height:34px;background:linear-gradient(135deg,#6366F1,#818CF8);
                        border-radius:9px;display:flex;align-items:center;justify-content:center;
                        font-size:0.9rem;font-weight:700;color:white;flex-shrink:0;">💰</div>
            <div>
                <div style="font-size:1rem;font-weight:700;color:#F1F5F9;letter-spacing:-0.02em;">Money Clarity</div>
            </div>
        </div>

        <div style="height:1px;background:rgba(255,255,255,0.07);margin-bottom:1.5rem;"></div>

        <div style="display:flex;align-items:center;gap:0.75rem;padding:0.75rem;
                    background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.07);
                    border-radius:10px;margin-bottom:1rem;">
            <div style="width:36px;height:36px;background:linear-gradient(135deg,#6366F1,#A78BFA);
                        border-radius:50%;display:flex;align-items:center;justify-content:center;
                        font-size:0.9rem;font-weight:700;color:white;flex-shrink:0;">{initial}</div>
            <div style="min-width:0;">
                <div style="font-size:0.82rem;font-weight:600;color:#E2E8F0;white-space:nowrap;
                            overflow:hidden;text-overflow:ellipsis;">{name_part}</div>
                <div style="font-size:0.7rem;color:#475569;white-space:nowrap;overflow:hidden;
                            text-overflow:ellipsis;">{email}</div>
            </div>
        </div>
    </div>
    """)

    if SUPABASE_AUTH_AVAILABLE and st.button("Sign out", use_container_width=True):
        logout()

    st.html("""
    <div style="height:1px;background:rgba(255,255,255,0.07);margin:1.5rem 0;"></div>
    <div style="font-size:0.65rem;font-weight:600;letter-spacing:0.1em;text-transform:uppercase;
                color:#334155;margin-bottom:0.6rem;">Security</div>
    <div style="font-size:0.72rem;color:#334155;line-height:1.6;">
        🔒 Files encrypted with AES-256-GCM before storage. Your data is never shared.
    </div>
    """)

# ── Backend API client helper ─────────────────────────────────────────────────
def _api():
    return ApiClient(access_token=get_access_token()) if SUPABASE_AUTH_AVAILABLE else None

# ── Legacy Gmail OAuth callback ───────────────────────────────────────────────
_params = st.query_params
if "code" in _params and "gmail_flow" in st.session_state and GOOGLE_LIBS_AVAILABLE:
    try:
        _flow = st.session_state["gmail_flow"]
        _flow.fetch_token(code=_params["code"])
        st.session_state["gmail_creds"] = _flow.credentials
        del st.session_state["gmail_flow"]
        st.query_params.clear()
        st.rerun()
    except Exception as _e:
        st.error(f"OAuth error: {_e}")
        st.query_params.clear()


# ══════════════════════════════════════════════════════════════════════════════
# DATA HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def fmt(v): return f"₹{abs(v):,.0f}"

def parse_inr(val):
    if isinstance(val, (int, float)):
        return float(val) if not pd.isna(val) else 0.0
    v = re.sub(r"[₹,\s]", "", str(val))
    if v.startswith("(") and v.endswith(")"): v = "-" + v[1:-1]
    try: return float(v)
    except ValueError: return 0.0

CATEGORIES = {
    "Food & Dining":    ["zomato","swiggy","blinkit","restaurant","cafe","coffee","food","pizza","burger","kfc","mcdonalds","dominos"],
    "Transport":        ["uber","ola","rapido","metro","irctc","redbus","petrol","fuel","parking","makemytrip","goibibo"],
    "Shopping":         ["amazon","flipkart","myntra","ajio","nykaa","meesho","reliance","big bazaar","dmart"],
    "Utilities":        ["electricity","water","broadband","jio","airtel","vi ","bsnl","gas","wifi","tata power"],
    "Entertainment":    ["netflix","spotify","prime","hotstar","zee5","apple","bookmyshow","pvr","inox"],
    "Healthcare":       ["pharmacy","hospital","clinic","doctor","medical","apollo","medplus","1mg","pharmeasy"],
    "Rent & Housing":   ["rent","maintenance","housing","society","landlord"],
    "Investments":      ["mutual fund","sip","zerodha","groww","kuvera","lic","insurance premium","rd","recurring"],
    "Salary / Income":  ["salary","sal cr","neft cr","payroll","stipend"],
    "UPI / GPay":       ["upi","phonepe","gpay","google pay","paytm","bhim","neft","imps","rtgs"],
    "Credit Card Bill": ["hdfc bank credit","icici credit","axis bank credit","millenia","swiggy card","rupay"],
    "Subscriptions":    ["adobe","notion","zoom","microsoft","google one","icloud","dropbox","linkedin"],
}

def categorize(desc):
    if not isinstance(desc, str): return "Others"
    d = desc.lower()
    for cat, kws in CATEGORIES.items():
        if any(kw in d for kw in kws): return cat
    return "Others"

def detect_and_load(f):
    name = f.name.lower()
    try:
        if name.endswith((".xlsx", ".xls")):
            raw = pd.read_excel(f, dtype=str)
        else:
            content = f.read().decode("utf-8", errors="replace")
            lines = content.splitlines()
            hi = 0
            for i, l in enumerate(lines):
                if re.search(r"(date|narration|description|debit|credit|amount)", l, re.I):
                    hi = i; break
            raw = pd.read_csv(StringIO("\n".join(lines[hi:])), dtype=str)
    except Exception as e:
        return None, str(e)
    raw.columns = raw.columns.str.strip().str.lower().str.replace(r"\s+", " ", regex=True)
    date_col   = next((c for c in raw.columns if re.search(r"\bdate\b", c)), None)
    desc_col   = next((c for c in raw.columns if re.search(r"narration|description|particular|details|remark|txn", c)), None)
    debit_col  = next((c for c in raw.columns if re.search(r"debit|withdrawal|dr\b", c)), None)
    credit_col = next((c for c in raw.columns if re.search(r"credit|deposit|cr\b", c)), None)
    amt_col    = next((c for c in raw.columns if re.search(r"^amount$", c)), None)
    if not date_col:   return None, "No Date column found."
    if not desc_col:   return None, "No Description/Narration column found."
    if not debit_col and not credit_col and not amt_col:
        return None, "No Amount/Debit/Credit columns found."
    df = pd.DataFrame()
    df["Date"]        = pd.to_datetime(raw[date_col], errors="coerce", dayfirst=True)
    df["Description"] = raw[desc_col].astype(str).str.strip()
    if debit_col and credit_col:
        df["Debit"]  = raw[debit_col].apply(parse_inr)
        df["Credit"] = raw[credit_col].apply(parse_inr)
        df["Amount"] = df["Credit"] - df["Debit"]
    elif amt_col:
        df["Amount"] = raw[amt_col].apply(parse_inr)
        df["Debit"]  = df["Amount"].apply(lambda x: abs(x) if x < 0 else 0.0)
        df["Credit"] = df["Amount"].apply(lambda x: x if x > 0 else 0.0)
    else:
        return None, "Cannot parse amounts."
    df["Type"]     = df["Amount"].apply(lambda x: "Income" if x >= 0 else "Expense")
    df["Category"] = df["Description"].apply(categorize)
    df["Source"]   = f.name
    df = df.dropna(subset=["Date"]).copy()
    df["Date"]  = df["Date"].dt.normalize()
    df["Month"] = df["Date"].dt.to_period("M").astype(str)
    return df.sort_values("Date").reset_index(drop=True), ""

def parse_mf_notifications(text):
    results = []
    amount_pat = re.compile(r"(?:rs\.?|₹|inr)\s*([\d,]+)", re.I)
    date_pat   = re.compile(r"(\d{1,2}[-/]\w{3,9}[-/]\d{2,4}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\w+ \d{4})", re.I)
    for line in text.strip().splitlines():
        line = line.strip()
        if not line: continue
        amounts = amount_pat.findall(line)
        if not amounts: continue
        amount = float(amounts[-1].replace(",", ""))
        date_match = date_pat.search(line)
        try:
            dt = pd.to_datetime(date_match.group(1), dayfirst=True) if date_match else pd.Timestamp.now()
        except Exception:
            dt = pd.Timestamp.now()
        results.append({"month": dt.to_period("M").strftime("%b %Y"), "amount": amount})
    return results

def compute_monthly_summary(stmt_df, mf_rows=None, rd_rows=None):
    months = sorted(stmt_df["Month"].unique())
    mf_by_month: dict = {}
    for r in (mf_rows or []):
        mf_by_month[r["month"]] = mf_by_month.get(r["month"], 0) + r["amount"]
    rd_by_month: dict = {}
    for r in (rd_rows or []):
        rd_by_month[r["month"]] = rd_by_month.get(r["month"], 0) + r["amount"]
    rows = []
    for month in months:
        m   = stmt_df[stmt_df["Month"] == month]
        exp = m[m["Type"] == "Expense"]
        inc = m[m["Type"] == "Income"]
        salary   = inc[inc["Category"] == "Salary / Income"]["Credit"].sum()
        outgoing = exp["Debit"].sum()
        incoming = inc["Credit"].sum()
        net_cash = incoming - outgoing
        fixed    = exp[exp["Category"] == "Rent & Housing"]["Debit"].sum()
        cc_bill  = exp[exp["Category"] == "Credit Card Bill"]["Debit"].sum()
        swiggy_cc= exp[exp["Description"].str.contains("swiggy", case=False, na=False)]["Debit"].sum()
        rupay_cc = exp[exp["Description"].str.contains("rupay",  case=False, na=False)]["Debit"].sum()
        upi      = exp[exp["Category"] == "UPI / GPay"]["Debit"].sum()
        inv      = exp[exp["Category"] == "Investments"]
        mf_stmt  = inv[inv["Description"].str.contains(r"sip|mutual|mf\b|nfo|lumpsum", case=False, na=False)]["Debit"].sum()
        rd_stmt  = inv[inv["Description"].str.contains(r"\brd\b|recurring deposit", case=False, na=False)]["Debit"].sum()
        stocks   = inv[inv["Description"].str.contains(r"stock|espp|nsdl|cdsl|zerodha|groww|kuvera", case=False, na=False)]["Debit"].sum()
        mf_p     = mf_by_month.get(month, mf_stmt)
        rd_a     = rd_by_month.get(month, rd_stmt)
        rows.append({
            "Month": month, "Salary": round(salary),
            "Outgoing (Debits)": round(outgoing), "Incoming (Credits)": round(incoming),
            "Net Cash": round(net_cash), "Fixed (Home+Child+HH)": round(fixed),
            "Credit Card": round(cc_bill), "Swiggy Credit Card": round(swiggy_cc),
            "Rupay Credit Card": round(rupay_cc), "GPay / UPI Sent": round(upi),
            "Total Spent": round(outgoing), "MF Principal": round(mf_p),
            "MF with Interest": round(mf_p), "Recurring Deposit (RD)": round(rd_a),
            "Stocks / ESPP": round(stocks), "Total Savings": round(mf_p + rd_a + stocks),
        })
    return pd.DataFrame(rows)


def _tx_rows_to_df(rows: list[dict]) -> pd.DataFrame:
    """Normalize API transaction rows into the standard stmt_df column schema."""
    df = pd.DataFrame(rows)
    df["Date"]        = pd.to_datetime(df["date"], errors="coerce")
    df["Description"] = df["description"].astype(str)
    df["Debit"]       = df["debit"].astype(float)
    df["Credit"]      = df["credit"].astype(float)
    df["Amount"]      = df["Credit"] - df["Debit"]
    df["Type"]        = df["type"].str.capitalize()
    df["Category"]    = df["category"].astype(str)
    df["Source"]      = df["source"].astype(str)
    df["Month"]       = df["month"].astype(str)
    return df[
        ["Date", "Description", "Debit", "Credit", "Amount", "Type", "Category", "Source", "Month"]
    ].sort_values("Date").reset_index(drop=True)


# ── Load stored data on first session ────────────────────────────────────────
if SUPABASE_AUTH_AVAILABLE and "backend_summaries_loaded" not in st.session_state:
    _load_error: str | None = None
    with st.spinner("Loading your data…"):
        try:
            client = _api()
            async def _startup():
                return await asyncio.gather(
                    client.get_transactions(),
                    client.get_gmail_status(),
                )
            tx_rows, gmail_status = asyncio.run(_startup())
            if tx_rows:
                st.session_state["stmt_df"] = _tx_rows_to_df(tx_rows)
                st.session_state["summary_df"] = compute_monthly_summary(st.session_state["stmt_df"])
            st.session_state["backend_summaries_loaded"] = True
            st.session_state["gmail_connected_backend"] = gmail_status.get("connected", False)
        except Exception as _e:
            _load_error = str(_e)
    if _load_error:
        col_err, col_retry = st.columns([4, 1])
        col_err.warning(f"Could not load your saved data: {_load_error}")
        if col_retry.button("Retry", key="_retry_load"):
            st.rerun()


AI_PROMPT = """You are a financial data parser. Convert the pasted bank statement into clean CSV.
Output STRICTLY in CSV format with headers: Date,Description,Debit,Credit
Rules:
- No extra text, no markdown, no code fences
- Dates in DD-MM-YYYY format
- Debit = money out (positive number), Credit = money in (positive number)
- Remove or replace: names, account numbers, PAN details, employer names
- Keep only transaction rows"""

def anonymize_statement(raw_text):
    api_key = st.secrets.get("OPENAI_API_KEY", "")
    if not api_key:
        return None, "OpenAI API key not configured."
    try:
        client = _openai.OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini", max_tokens=4096,
            messages=[{"role": "system", "content": AI_PROMPT},
                      {"role": "user", "content": raw_text[:12000]}],
        )
        return resp.choices[0].message.content.strip(), None
    except Exception as e:
        return None, str(e)

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
GMAIL_QUERY  = ("has:attachment (from:statements@hdfcbank.net OR from:alerts@icicibank.com OR "
                "from:statements@axisbank.com OR from:alerts@kotakbank.com OR "
                "subject:statement OR subject:e-statement OR subject:transaction)")

def _get_oauth_config():
    try:
        cid  = st.secrets["GOOGLE_CLIENT_ID"]
        csec = st.secrets["GOOGLE_CLIENT_SECRET"]
        ruri = st.secrets.get("REDIRECT_URI", "http://localhost:8501")
        return cid, csec, ruri, None
    except Exception:
        return None, None, None, "Google OAuth not configured in secrets.toml"

def build_oauth_flow():
    cid, csec, ruri, err = _get_oauth_config()
    if err: return None, err
    flow = Flow.from_client_config(
        {"web": {"client_id": cid, "client_secret": csec,
                 "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                 "token_uri": "https://oauth2.googleapis.com/token",
                 "redirect_uris": [ruri]}},
        scopes=GMAIL_SCOPES, redirect_uri=ruri,
    )
    return flow, None

def fetch_gmail_attachments_oauth(creds, max_results=50):
    attachments, errors = [], []
    try:
        service  = build("gmail", "v1", credentials=creds)
        response = service.users().messages().list(userId="me", q=GMAIL_QUERY, maxResults=max_results).execute()
        messages = response.get("messages", [])
        def _extract(parts, mid):
            for part in parts:
                if part.get("parts"): _extract(part["parts"], mid)
                fname = part.get("filename", "")
                if fname and any(fname.lower().endswith(e) for e in [".csv",".xlsx",".xls"]):
                    att_id = part["body"].get("attachmentId")
                    if att_id:
                        att  = service.users().messages().attachments().get(userId="me", messageId=mid, id=att_id).execute()
                        data = base64.urlsafe_b64decode(att["data"] + "==")
                        attachments.append((fname, BytesIO(data)))
        for ref in messages:
            msg = service.users().messages().get(userId="me", id=ref["id"], format="full").execute()
            _extract(msg.get("payload", {}).get("parts", []), ref["id"])
    except Exception as e:
        errors.append(str(e))
    return attachments, errors


# ══════════════════════════════════════════════════════════════════════════════
# UI HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def section_header(title, badge=None, margin_top="2rem"):
    badge_html = f'<span style="font-size:0.63rem;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;padding:0.2rem 0.65rem;border-radius:20px;background:#EEF2FF;color:#6366F1;">{badge}</span>' if badge else ""
    st.html(f"""
    <div style="display:flex;align-items:center;gap:0.75rem;margin:{margin_top} 0 1.1rem;
                padding-bottom:0.75rem;border-bottom:1px solid #E2E8F0;">
        <h2 style="margin:0;font-size:1rem;font-weight:600;color:#0F172A;letter-spacing:-0.01em;">{title}</h2>
        {badge_html}
    </div>
    """)

def chart_label(title, subtitle=None):
    sub = f'<div style="font-size:0.73rem;color:#94A3B8;margin-top:0.15rem;">{subtitle}</div>' if subtitle else ""
    st.html(f"""
    <div style="padding:1rem 1rem 0.5rem;border-bottom:1px solid #F1F5F9;">
        <div style="font-size:0.875rem;font-weight:600;color:#0F172A;">{title}</div>
        {sub}
    </div>
    """)



# ══════════════════════════════════════════════════════════════════════════════
# PAGE HEADER
# ══════════════════════════════════════════════════════════════════════════════
data_loaded   = "stmt_df"   in st.session_state
summary_ready = "summary_df" in st.session_state

st.markdown(f"""
<div style="display:flex;align-items:flex-end;justify-content:space-between;
            padding-bottom:1.25rem;border-bottom:2px solid #E2E8F0;margin-bottom:1.75rem;">
    <div>
        <h1 style="margin:0 0 0.2rem;font-size:1.45rem;font-weight:700;color:#0F172A;letter-spacing:-0.025em;">
            Financial Dashboard
        </h1>
        <p style="margin:0;font-size:0.85rem;color:#94A3B8;">
            Track income, expenses, and savings across all your accounts
        </p>
    </div>
    <div style="font-size:0.72rem;color:#CBD5E1;display:flex;align-items:center;gap:0.4rem;">
        <span style="width:6px;height:6px;background:#10B981;border-radius:50%;display:inline-block;"></span>
        Live
    </div>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADER
# ══════════════════════════════════════════════════════════════════════════════
if not summary_ready:
    st.html("""
    <div style="background:linear-gradient(135deg,#0F172A 0%,#1E293B 100%);border-radius:16px;
                padding:2.5rem 2rem;text-align:center;margin-bottom:1.75rem;position:relative;overflow:hidden;">
        <div style="position:absolute;top:-40%;left:-20%;width:60%;height:200%;
                    background:radial-gradient(circle,rgba(99,102,241,0.12),transparent 70%);pointer-events:none;"></div>
        <div style="position:absolute;top:-40%;right:-20%;width:60%;height:200%;
                    background:radial-gradient(circle,rgba(16,185,129,0.08),transparent 70%);pointer-events:none;"></div>
        <div style="position:relative;">
            <h2 style="font-size:1.55rem;font-weight:700;color:#F8FAFC;letter-spacing:-0.03em;margin:0 0 0.5rem;">
                Welcome to Money Clarity
            </h2>
            <p style="color:#64748B;font-size:0.88rem;margin:0 0 2rem;">
                Upload your bank statement to get a full picture of your finances in seconds.
            </p>
            <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;max-width:560px;margin:0 auto;">
                <div style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.09);
                            border-radius:10px;padding:1rem 0.75rem;">
                    <div style="font-size:1.3rem;margin-bottom:0.4rem;">📁</div>
                    <div style="font-size:0.78rem;font-weight:600;color:#E2E8F0;margin-bottom:0.2rem;">Upload</div>
                    <div style="font-size:0.7rem;color:#475569;line-height:1.4;">CSV or XLSX from your bank</div>
                </div>
                <div style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.09);
                            border-radius:10px;padding:1rem 0.75rem;">
                    <div style="font-size:1.3rem;margin-bottom:0.4rem;">✨</div>
                    <div style="font-size:0.78rem;font-weight:600;color:#E2E8F0;margin-bottom:0.2rem;">Auto-categorise</div>
                    <div style="font-size:0.7rem;color:#475569;line-height:1.4;">Transactions sorted instantly</div>
                </div>
                <div style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.09);
                            border-radius:10px;padding:1rem 0.75rem;">
                    <div style="font-size:1.3rem;margin-bottom:0.4rem;">📊</div>
                    <div style="font-size:0.78rem;font-weight:600;color:#E2E8F0;margin-bottom:0.2rem;">Insights</div>
                    <div style="font-size:0.7rem;color:#475569;line-height:1.4;">Full monthly breakdown</div>
                </div>
            </div>
        </div>
    </div>
    """)

_exp_label = "✅ Data loaded — click to reload or add more" if data_loaded else "📂 Load your bank statements"
with st.expander(_exp_label, expanded=not data_loaded):
    s1, s2, s3 = st.columns([2, 1.5, 1.2])
    frames, load_errors = [], []

    with s1:
        st.markdown(f'<p style="font-size:0.82rem;font-weight:600;color:#0F172A;margin-bottom:0.6rem;">{"✅" if data_loaded else "① &nbsp;"} Upload Statement</p>', unsafe_allow_html=True)
        uploads = st.file_uploader(
            "Drop your bank statement here",
            type=["csv","xlsx","xls"],
            accept_multiple_files=True, key="stmt_upload",
            help="Export as CSV or XLSX from your bank's net-banking portal",
        )
        if uploads:
            for f in uploads:
                dff, err = detect_and_load(f)
                if err:
                    load_errors.append(f"**{f.name}:** {err}")
                else:
                    frames.append(dff)
                    if SUPABASE_AUTH_AVAILABLE:
                        try:
                            api = _api()
                            file_bytes = f.getvalue()
                            up_result    = asyncio.run(api.upload_file(file_bytes, f.name))
                            parse_result = asyncio.run(api.parse_upload(up_result["upload_id"]))
                            st.caption(f"✅ {parse_result['inserted']} transactions saved to your account")
                            st.session_state.pop("backend_summaries_loaded", None)
                        except Exception as _be:
                            st.caption(f"⚠️ Could not persist to backend: {_be}")

        st.markdown(f'<p style="font-size:0.75rem;color:#94A3B8;margin-top:0.25rem;">🔒 Remove personal info first? Use this prompt in ChatGPT:</p>', unsafe_allow_html=True)
        st.code('Convert this bank statement to CSV: Date, Description, Debit, Credit. Anonymise names and account numbers.', language=None)

        # Gmail section
        st.markdown(f'<div style="display:flex;align-items:center;gap:0.5rem;margin:0.75rem 0 0.5rem;"><hr style="flex:1;border:none;border-top:1px solid #E2E8F0;margin:0;"><span style="font-size:0.72rem;color:#CBD5E1;white-space:nowrap;">or connect Gmail</span><hr style="flex:1;border:none;border-top:1px solid #E2E8F0;margin:0;"></div>', unsafe_allow_html=True)

        if SUPABASE_AUTH_AVAILABLE and st.session_state.get("gmail_connected_backend"):
            gc1, gc2 = st.columns([3, 1])
            with gc1: st.success("📧 Gmail connected")
            with gc2:
                if st.button("Sync", key="backend_sync_btn"):
                    try:
                        result = asyncio.run(_api().sync_gmail())
                        st.success(f"Synced: {result['new_files']} new files")
                        st.session_state.pop("backend_summaries_loaded", None)
                    except Exception as e:
                        st.error(f"Sync failed: {e}")
        elif SUPABASE_AUTH_AVAILABLE:
            if st.button("🔗 Connect Gmail (server-side)", use_container_width=True):
                try:
                    auth_url = asyncio.run(_api().get_gmail_connect_url())
                    st.markdown(f'<a href="{auth_url}" target="_blank" style="color:#6366F1;font-size:0.82rem;">→ Authorize Gmail access</a>', unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Could not initiate: {e}")
        elif "gmail_creds" in st.session_state:
            gc1, gc2 = st.columns([3, 1])
            with gc1: st.success("📧 Gmail connected")
            with gc2:
                fetch_clicked = st.button("Fetch", key="fetch_btn")
            if st.button("Disconnect", key="disc_btn"):
                del st.session_state["gmail_creds"]; st.rerun()
            if fetch_clicked:
                with st.spinner("Scanning Gmail…"):
                    attachments, errs = fetch_gmail_attachments_oauth(st.session_state["gmail_creds"])
                for err in errs: st.error(err)
                if attachments:
                    for fname, bio in attachments:
                        bio.name = fname
                        dff, err = detect_and_load(bio)
                        if err: load_errors.append(f"**{fname}:** {err}")
                        else:   frames.append(dff)
                elif not errs:
                    st.warning("No CSV/XLSX attachments found.")
        elif GOOGLE_LIBS_AVAILABLE:
            flow, err = build_oauth_flow()
            if not err:
                auth_url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent")
                st.session_state["gmail_flow"] = flow
                st.markdown(f'<a href="{auth_url}" target="_self" style="display:inline-block;padding:0.55rem 1.1rem;background:#fff;border:1px solid #E2E8F0;border-radius:8px;font-size:0.82rem;font-weight:500;color:#0F172A;text-decoration:none;box-shadow:0 1px 2px rgba(0,0,0,0.05);">📧 Connect Gmail</a>', unsafe_allow_html=True)

        for e in load_errors: st.warning(e)
        if frames:
            st.session_state.stmt_df = pd.concat(frames, ignore_index=True)
            st.success(f"{len(st.session_state.stmt_df):,} transactions loaded.")

    with s2:
        st.markdown(f'<p style="font-size:0.82rem;font-weight:500;color:#64748B;margin-bottom:0.4rem;">{"✅" if summary_ready else "② &nbsp;"} Investment Details <em style="font-weight:400;color:#94A3B8;">— optional</em></p>', unsafe_allow_html=True)
        st.caption("Paste MF / SIP / RD SMS alerts — one per line")
        mf_text = st.text_area("MF / SIP alerts", height=88, key="mf_notif",
            placeholder="Your SIP of ₹10,000 towards Axis Bluechip debited on 05-Jan-2025")
        rd_text = st.text_area("RD alerts", height=68, key="rd_notif",
            placeholder="Your RD of ₹10,000 debited on 01-Jan-2025")

    with s3:
        st.markdown(f'<p style="font-size:0.95rem;font-weight:600;color:#6366F1;margin-bottom:0.4rem;">{"✅" if summary_ready else "③ &nbsp;"} Generate</p>', unsafe_allow_html=True)
        st.write("")
        if "stmt_df" in st.session_state:
            if st.button("✨ Build Dashboard", type="primary", key="gen_btn", use_container_width=True):
                _mf = parse_mf_notifications(st.session_state.get("mf_notif",""))
                _rd = parse_mf_notifications(st.session_state.get("rd_notif",""))
                st.session_state.summary_df = compute_monthly_summary(st.session_state.stmt_df, _mf, _rd)
                st.rerun()
        else:
            st.button("✨ Build Dashboard", disabled=True, use_container_width=True,
                      help="Load statements first")
        st.caption("🔒 Processed locally")

        if summary_ready and not data_loaded:
            if st.button("Clear data", use_container_width=True):
                for k in ["stmt_df","summary_df"]: st.session_state.pop(k, None)
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# SELECT DATASET
# ══════════════════════════════════════════════════════════════════════════════
data_loaded   = "stmt_df"   in st.session_state
summary_ready = "summary_df" in st.session_state

if not summary_ready:
    st.stop()

use_df = st.session_state.summary_df.copy()

num_cols = [c for c in use_df.columns if c != "Month"]
for c in num_cols:
    use_df[c] = use_df[c].apply(parse_inr)

if use_df.empty or use_df["Salary"].sum() == 0:
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# KPI STRIP
# ══════════════════════════════════════════════════════════════════════════════
last = use_df.iloc[-1]
prev = use_df.iloc[-2] if len(use_df) > 1 else last

def _trend(curr, prev_val, invert=False):
    if prev_val == 0: return '<span style="font-size:0.72rem;color:#94A3B8;">— no prior data</span>'
    pct = ((curr - prev_val) / abs(prev_val)) * 100
    up  = pct >= 0
    good = (up and not invert) or (not up and invert)
    color = "#10B981" if good else "#EF4444"
    arrow = "↑" if up else "↓"
    return f'<span style="font-size:0.72rem;font-weight:500;color:{color};">{arrow} {abs(pct):.1f}% vs last month</span>'

income   = last["Incoming (Credits)"]
expenses = last["Outgoing (Debits)"]
savings  = last["Total Savings"]
net      = last["Net Cash"]
sav_rate = (savings / income * 100) if income > 0 else 0

kpis = [
    ("Total Income",    fmt(income),   _trend(income,   prev["Incoming (Credits)"],  invert=False), C_INCOME),
    ("Total Expenses",  fmt(expenses), _trend(expenses, prev["Outgoing (Debits)"],   invert=True),  C_EXPENSE),
    ("Net Cash",        fmt(net),      _trend(net,      prev["Net Cash"],             invert=False), C_ACCENT),
    ("Total Savings",   fmt(savings),  _trend(savings,  prev["Total Savings"],        invert=False), C_SAVINGS),
    ("Savings Rate",    f"{sav_rate:.1f}%", _trend(sav_rate, (prev["Total Savings"]/prev["Incoming (Credits)"]*100) if prev["Incoming (Credits)"] > 0 else 0, invert=False), C_AMBER),
]

kpi_html = '<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:1rem;margin-bottom:1.75rem;" class="kpi-grid">'
for label, value, trend, color in kpis:
    kpi_html += f"""
    <div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;padding:1.25rem 1rem;
                box-shadow:0 1px 2px rgba(0,0,0,0.04);position:relative;overflow:hidden;
                transition:box-shadow 0.15s;">
        <div style="position:absolute;top:0;left:0;right:0;height:3px;background:{color};
                    border-radius:12px 12px 0 0;"></div>
        <div style="font-size:0.67rem;font-weight:600;letter-spacing:0.09em;text-transform:uppercase;
                    color:#94A3B8;margin-bottom:0.55rem;">{label}</div>
        <div style="font-size:1.45rem;font-weight:700;letter-spacing:-0.025em;color:#0F172A;
                    line-height:1;margin-bottom:0.4rem;">{value}</div>
        {trend}
    </div>"""
kpi_html += "</div>"
st.markdown(kpi_html, unsafe_allow_html=True)


# ── Auto-insights banner ───────────────────────────────────────────────────────
if len(use_df) > 1:
    max_spend_row = use_df.loc[use_df["Total Spent"].idxmax()]
    max_save_row  = use_df.loc[use_df["Total Savings"].idxmax()]
    avg_save      = use_df["Total Savings"].mean()
    last_save     = use_df["Total Savings"].iloc[-1]
    trend_txt = f"↑ above average ({fmt(avg_save)})" if last_save > avg_save else f"↓ below average ({fmt(avg_save)})"
    trend_col = "#10B981" if last_save > avg_save else "#EF4444"
    st.html(f"""
    <div style="background:linear-gradient(135deg,#EEF2FF,#EFF6FF);border:1px solid #C7D2FE;
                border-radius:10px;padding:0.9rem 1.25rem;margin-bottom:1.5rem;
                display:flex;align-items:flex-start;gap:0.75rem;">
        <span style="font-size:1rem;flex-shrink:0;margin-top:0.05rem;">💡</span>
        <div style="font-size:0.83rem;color:#1E3A8A;line-height:1.65;">
            <strong>Insights:</strong>
            Highest spend in <strong>{max_spend_row['Month']}</strong> at {fmt(max_spend_row['Total Spent'])} &nbsp;·&nbsp;
            Best savings in <strong>{max_save_row['Month']}</strong> at {fmt(max_save_row['Total Savings'])} &nbsp;·&nbsp;
            <span style="color:{trend_col};font-weight:500;">This month savings {trend_txt}</span>
        </div>
    </div>
    """)


# ══════════════════════════════════════════════════════════════════════════════
# TRENDS SECTION
# ══════════════════════════════════════════════════════════════════════════════
section_header("Trends", "6 MONTHS")

ca, cb = st.columns(2)

with ca:
    chart_label("Income vs Expenses", "Monthly comparison")
    trend_df = use_df[["Month","Incoming (Credits)","Outgoing (Debits)"]].rename(
        columns={"Incoming (Credits)": "Income", "Outgoing (Debits)": "Expenses"})
    melted = trend_df.melt(id_vars="Month", var_name="Type", value_name="Amount")
    fig = px.bar(melted, x="Month", y="Amount", color="Type", barmode="group",
                 color_discrete_map={"Income": C_INCOME, "Expenses": C_EXPENSE},
                 labels={"Amount": "₹", "Month": ""})
    fig.update_traces(marker_cornerradius=3)
    apply_theme(fig, height=300)
    st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

with cb:
    chart_label("Monthly Spend Breakdown", "Stacked by category")
    EXP_COLS = {
        "Fixed (Home+Child+HH)": "Fixed",
        "Credit Card":           "Credit Card",
        "GPay / UPI Sent":       "UPI / GPay",
        "Swiggy Credit Card":    "Swiggy CC",
        "Rupay Credit Card":     "Rupay CC",
    }
    avail = {k: v for k, v in EXP_COLS.items() if k in use_df.columns}
    if avail:
        stack_df = use_df[["Month"] + list(avail.keys())].rename(columns=avail)
        melted2  = stack_df.melt(id_vars="Month", var_name="Category", value_name="Amount")
        melted2  = melted2[melted2["Amount"] > 0]
        fig2 = px.bar(melted2, x="Month", y="Amount", color="Category",
                      barmode="stack", color_discrete_sequence=PALETTE,
                      labels={"Amount": "₹", "Month": ""})
        fig2.update_traces(marker_cornerradius=2)
        apply_theme(fig2, height=300)
        st.plotly_chart(fig2, use_container_width=True, config=CHART_CONFIG)


# ══════════════════════════════════════════════════════════════════════════════
# SAVINGS & POSITION
# ══════════════════════════════════════════════════════════════════════════════
section_header("Savings & Net Position")

sa, sb = st.columns(2)

with sa:
    chart_label("Savings Growth", "MF + RD + Stocks over time")
    sav_cols = [c for c in ["Month","MF Principal","Recurring Deposit (RD)","Stocks / ESPP"] if c in use_df.columns]
    if len(sav_cols) > 1:
        melted_s = use_df[sav_cols].melt(id_vars="Month", var_name="Type", value_name="Value")
        melted_s = melted_s[melted_s["Value"] > 0]
        fig_s = px.area(melted_s, x="Month", y="Value", color="Type",
                        color_discrete_sequence=[C_SAVINGS, C_TEAL, C_ACCENT],
                        labels={"Value": "₹", "Month": ""})
        fig_s.update_traces(line_width=2)
        apply_theme(fig_s, height=300)
        st.plotly_chart(fig_s, use_container_width=True, config=CHART_CONFIG)

with sb:
    chart_label("Net Cash by Month", "Green = surplus · Red = deficit")
    if "Net Cash" in use_df.columns:
        net_df = use_df[["Month","Net Cash"]].copy()
        net_df["color"] = net_df["Net Cash"].apply(lambda x: C_INCOME if x >= 0 else C_EXPENSE)
        fig_net = go.Figure(go.Bar(
            x=net_df["Month"], y=net_df["Net Cash"],
            marker_color=net_df["color"],
            text=[fmt(v) for v in net_df["Net Cash"]],
            textposition="outside",
            textfont=dict(size=10.5, color="#64748B"),
        ))
        fig_net.update_traces(marker_cornerradius=3)
        fig_net.add_hline(y=0, line_dash="dot", line_color="#E2E8F0", line_width=1.5)
        apply_theme(fig_net, height=300, show_legend=False)
        st.plotly_chart(fig_net, use_container_width=True, config=CHART_CONFIG)


# ══════════════════════════════════════════════════════════════════════════════
# EDITABLE TRACKER
# ══════════════════════════════════════════════════════════════════════════════
with st.expander("📋 Monthly Tracker — view & edit", expanded=False):
    edited = st.data_editor(use_df, use_container_width=True, num_rows="dynamic", key="summary_editor")
    st.session_state.summary_df = edited
    c1, _ = st.columns([1, 5])
    with c1:
        st.download_button("⬇️ Export CSV", edited.to_csv(index=False).encode(),
                           "money_clarity_summary.csv", "text/csv")


# ══════════════════════════════════════════════════════════════════════════════
# SPEND ANALYSIS (from raw transactions)
# ══════════════════════════════════════════════════════════════════════════════
if data_loaded:
    section_header("Spend Analysis", "TRANSACTIONS")

    df_raw = st.session_state.stmt_df.copy()

    fa, fb, fc = st.columns(3)
    with fa:
        months = sorted(df_raw["Month"].unique())
        sel_m  = st.multiselect("Month", months, default=months, key="f_month")
    with fb:
        cats  = sorted(df_raw["Category"].unique())
        sel_c = st.multiselect("Category", cats, default=cats, key="f_cat")
    with fc:
        sel_t = st.multiselect("Type", ["Income","Expense"], default=["Income","Expense"], key="f_type")

    df = df_raw[df_raw["Month"].isin(sel_m) & df_raw["Category"].isin(sel_c) & df_raw["Type"].isin(sel_t)]

    if df.empty:
        st.info("No transactions match the current filters.")
    else:
        total_in  = df[df["Type"]=="Income"]["Credit"].sum()
        total_out = df[df["Type"]=="Expense"]["Debit"].sum()
        net_val   = total_in - total_out

        k1, k2, k3, k4 = st.columns(4)
        for col, label, val, color in [
            (k1, "Total Income",   total_in,       C_INCOME),
            (k2, "Total Expenses", total_out,       C_EXPENSE),
            (k3, "Net",            net_val,         C_ACCENT if net_val >= 0 else C_EXPENSE),
            (k4, "Transactions",   None,            "#94A3B8"),
        ]:
            with col:
                if val is not None:
                    st.html(f"""
                    <div style="background:#fff;border:1px solid #E2E8F0;border-radius:10px;
                                padding:1rem;box-shadow:0 1px 2px rgba(0,0,0,0.04);text-align:center;">
                        <div style="font-size:0.67rem;font-weight:600;letter-spacing:0.09em;text-transform:uppercase;color:#94A3B8;margin-bottom:0.35rem;">{label}</div>
                        <div style="font-size:1.25rem;font-weight:700;color:{color};">{fmt(val)}</div>
                    </div>""")
                else:
                    st.html(f"""
                    <div style="background:#fff;border:1px solid #E2E8F0;border-radius:10px;
                                padding:1rem;box-shadow:0 1px 2px rgba(0,0,0,0.04);text-align:center;">
                        <div style="font-size:0.67rem;font-weight:600;letter-spacing:0.09em;text-transform:uppercase;color:#94A3B8;margin-bottom:0.35rem;">{label}</div>
                        <div style="font-size:1.25rem;font-weight:700;color:{color};">{len(df):,}</div>
                    </div>""")

        st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)
        expenses = df[df["Type"] == "Expense"].copy()

        r1, r2 = st.columns(2)
        with r1:
            chart_label("Where did my money go?", "Spending by category")
            ec = expenses.groupby("Category")["Debit"].sum().reset_index().sort_values("Debit", ascending=False)
            if not ec.empty:
                ec["pct"] = (ec["Debit"] / ec["Debit"].sum() * 100).round(1)
                fig_tree = px.treemap(
                    ec, path=["Category"], values="Debit",
                    color="Debit",
                    color_continuous_scale=["#EEF2FF","#818CF8","#4338CA"],
                    custom_data=["pct"],
                )
                fig_tree.update_traces(
                    texttemplate="<b>%{label}</b><br>₹%{value:,.0f}<br>%{customdata[0]}%",
                    textfont_size=11.5,
                    marker_line_width=2,
                    marker_line_color="#F8FAFC",
                )
                fig_tree.update_layout(
                    height=340, margin=dict(t=8,b=0,l=0,r=0),
                    coloraxis_showscale=False,
                    paper_bgcolor="#FFFFFF",
                )
                st.plotly_chart(fig_tree, use_container_width=True, config=CHART_CONFIG)

        with r2:
            chart_label("Spend by Month", "🔴 = highest")
            mo_exp = expenses.groupby("Month")["Debit"].sum().reset_index()
            mo_exp["color"] = [C_EXPENSE if v == mo_exp["Debit"].max() else C_ACCENT for v in mo_exp["Debit"]]
            fig_mo = go.Figure(go.Bar(
                x=mo_exp["Month"], y=mo_exp["Debit"],
                marker_color=mo_exp["color"],
                text=[fmt(v) for v in mo_exp["Debit"]],
                textposition="outside",
                textfont=dict(size=10.5, color="#64748B"),
            ))
            fig_mo.update_traces(marker_cornerradius=3)
            apply_theme(fig_mo, height=340, show_legend=False)
            st.plotly_chart(fig_mo, use_container_width=True, config=CHART_CONFIG)

        r3, r4 = st.columns(2)
        with r3:
            chart_label("Top 10 Merchants", "By total spend")
            merchants = (expenses.groupby("Description")["Debit"].sum()
                         .sort_values(ascending=False).head(10).reset_index())
            merchants["Description"] = merchants["Description"].str[:40]
            fig_m = px.bar(
                merchants, x="Debit", y="Description", orientation="h",
                color="Debit",
                color_continuous_scale=["#C7D2FE","#4338CA"],
                text=[fmt(v) for v in merchants["Debit"]],
                labels={"Debit":"₹","Description":""},
            )
            fig_m.update_traces(textposition="outside", textfont_size=10.5,
                                 marker_cornerradius=3)
            fig_m.update_layout(
                height=340, margin=dict(t=8,b=8,l=0,r=50),
                yaxis=dict(autorange="reversed"),
                coloraxis_showscale=False,
                plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
                xaxis=dict(showgrid=False),
                font=dict(size=10.5, color="#94A3B8"),
            )
            st.plotly_chart(fig_m, use_container_width=True, config=CHART_CONFIG)

        with r4:
            chart_label("Spending by Day of Week", "🔴 = peak day")
            exp_dow = expenses.copy()
            exp_dow["DayOfWeek"] = exp_dow["Date"].dt.day_name()
            dow_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
            dow = exp_dow.groupby("DayOfWeek")["Debit"].sum().reindex(dow_order).fillna(0).reset_index()
            dow["color"] = [C_EXPENSE if v == dow["Debit"].max() else C_ACCENT for v in dow["Debit"]]
            fig_dow = go.Figure(go.Bar(
                x=dow["DayOfWeek"], y=dow["Debit"],
                marker_color=dow["color"],
                text=[fmt(v) for v in dow["Debit"]],
                textposition="outside",
                textfont=dict(size=10.5, color="#64748B"),
            ))
            fig_dow.update_traces(marker_cornerradius=3)
            apply_theme(fig_dow, height=340, show_legend=False)
            st.plotly_chart(fig_dow, use_container_width=True, config=CHART_CONFIG)

        # Heatmap
        section_header("Spend Heatmap", "CATEGORY × MONTH", margin_top="1.5rem")
        st.caption("Darker = higher spend. Spot patterns across months at a glance.")
        pivot = expenses.groupby(["Category","Month"])["Debit"].sum().unstack(fill_value=0)
        if not pivot.empty:
            fig_heat = px.imshow(
                pivot,
                color_continuous_scale=["#F8FAFC","#A5B4FC","#312E81"],
                aspect="auto", text_auto=".0f",
                labels=dict(x="Month", y="Category", color="₹"),
            )
            fig_heat.update_traces(textfont_size=10)
            fig_heat.update_layout(
                height=max(260, len(pivot) * 34),
                margin=dict(t=8,b=8,l=0,r=0),
                paper_bgcolor="#FFFFFF",
                coloraxis_showscale=False,
            )
            st.plotly_chart(fig_heat, use_container_width=True, config=CHART_CONFIG)

        # Daily pattern
        r5, r6 = st.columns(2)
        with r5:
            chart_label("Daily Spending Pattern")
            daily = expenses.groupby("Date")["Debit"].sum().reset_index()
            fig_d = px.area(daily, x="Date", y="Debit",
                            color_discrete_sequence=[C_EXPENSE],
                            labels={"Debit":"₹","Date":""})
            fig_d.update_traces(fillcolor="rgba(239,68,68,0.1)", line_width=1.5)
            apply_theme(fig_d, height=260)
            st.plotly_chart(fig_d, use_container_width=True, config=CHART_CONFIG)

        with r6:
            chart_label("Income vs Expense by Month")
            mo_both = df.groupby(["Month","Type"]).agg(D=("Debit","sum"),C=("Credit","sum")).reset_index()
            mo_both["Val"] = mo_both.apply(lambda r: r["C"] if r["Type"]=="Income" else r["D"], axis=1)
            fig_mo2 = px.bar(mo_both, x="Month", y="Val", color="Type", barmode="group",
                             color_discrete_map={"Income": C_INCOME, "Expense": C_EXPENSE},
                             labels={"Val":"₹","Month":""})
            fig_mo2.update_traces(marker_cornerradius=3)
            apply_theme(fig_mo2, height=260)
            st.plotly_chart(fig_mo2, use_container_width=True, config=CHART_CONFIG)

        # Transactions table
        section_header("Transactions", "DRILL DOWN", margin_top="1.5rem")
        search = st.text_input("🔍 Search by merchant, category, or amount",
                               placeholder="e.g. Zomato, Food, 500", key="txn_search")
        disp = df[["Date","Description","Type","Category","Debit","Credit","Source"]].copy()
        disp["Date"] = disp["Date"].dt.strftime("%d %b %Y")
        if search:
            disp = disp[disp["Description"].str.contains(search, case=False, na=False)]

        st.dataframe(
            disp, use_container_width=True, height=380,
            column_config={
                "Debit":  st.column_config.NumberColumn("Debit ₹",  format="₹%.0f"),
                "Credit": st.column_config.NumberColumn("Credit ₹", format="₹%.0f"),
                "Type":   st.column_config.TextColumn("Type"),
            },
        )
        c1, _ = st.columns([1, 6])
        with c1:
            st.download_button(
                "⬇️ Export CSV",
                disp.to_csv(index=False).encode(),
                "transactions.csv", "text/csv",
            )
