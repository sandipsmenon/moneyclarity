"""
Money Clarity Dashboard
Run: streamlit run dashboard.py

Auth flow:
  - Uses Supabase Auth (supabase-py) with email OTP or Google OAuth
  - Access token stored in st.session_state["sb_session"]
  - All API calls to FastAPI backend include Authorization: Bearer <token>
  - Logout invalidates session both client-side and server-side
"""

import asyncio

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from io import StringIO, BytesIO
import re
import base64

# Supabase Auth integration
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

# Google OAuth / Gmail API
try:
    from google_auth_oauthlib.flow import Flow
    from googleapiclient.discovery import build
    GOOGLE_LIBS_AVAILABLE = True
except ImportError:
    GOOGLE_LIBS_AVAILABLE = False

# Anthropic
try:
    import anthropic as _anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

st.set_page_config(page_title="Money Clarity OS", page_icon="💰", layout="wide")

# ── Auth: handle OAuth callback & gate the app ────────────────────────────────
if SUPABASE_AUTH_AVAILABLE:
    init_auth_state()
    handle_auth_callback()  # processes ?code= param from Supabase OAuth redirect

    if not is_authenticated():
        render_login_ui()
        st.stop()  # everything below only renders for authenticated users

    # Render logout button in sidebar
    with st.sidebar:
        user = get_user()
        email = user.email if user else "User"
        st.markdown(f"**Signed in as:** {email}")
        if st.button("Sign out", use_container_width=True):
            logout()

    # Build API client with current token (auto-refreshes on 401)
    def _get_api_client() -> "ApiClient":
        token = get_access_token()
        return ApiClient(access_token=token)

# ── Core palette ──────────────────────────────────────────────────────────────
C_GREEN  = "#16a34a"   # positive — savings, surplus, growth
C_RED    = "#dc2626"   # negative — expenses, deficit
C_BLUE   = "#4a72a8"   # neutral  — income, baseline
C_GREY   = "#6b7280"   # secondary / background elements
C_ACCENT = C_BLUE      # single accent for interactive elements

C_GREEN_BG = "#f0fdf4"
C_RED_BG   = "#fff1f2"
C_BLUE_BG  = "#f0f4fa"
C_GREY_BG  = "#f9fafb"

# Multi-series chart palette — green, blue, grey shades, then muted variants
PALETTE = [C_BLUE, C_GREEN, C_GREY, "#7ba3cc", "#4ade80", "#94a3b8", "#8aaed6", "#86efac"]

st.markdown(f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
  html, body, [class*="css"] {{ font-family: 'Inter', system-ui, sans-serif; }}
  .block-container {{ padding-top: 1.5rem; padding-bottom: 3rem; background: #ffffff;
                      padding-left: 1rem !important; padding-right: 1rem !important; }}
  /* KPI cards */
  .kpi {{
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 1rem 0.75rem;
    text-align: center;
    transition: box-shadow 0.15s;
    margin-bottom: 0.5rem;
  }}
  .kpi:hover {{ box-shadow: 0 4px 12px rgba(0,0,0,0.06); }}
  .kpi-label {{ font-size: 0.65rem; color: {C_GREY}; text-transform: uppercase;
               letter-spacing: 0.1em; margin-bottom: 0.25rem; }}
  .kpi-val   {{ font-size: 1.35rem; font-weight: 700; color: #111; line-height: 1; }}
  .kpi-delta {{ font-size: 0.7rem; margin-top: 0.25rem; font-weight: 500; }}
  .green {{ color: {C_GREEN}; }}
  .red   {{ color: {C_RED}; }}
  .blue  {{ color: {C_BLUE}; }}
  .muted {{ color: {C_GREY}; }}

  /* KPI grid — 2 cols on mobile, 5 on desktop */
  .kpi-grid {{
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 0.75rem;
    margin-bottom: 1rem;
  }}

  /* Insight banner */
  .insight-box {{
    background: {C_BLUE_BG};
    border-left: 4px solid {C_BLUE};
    border-radius: 0 10px 10px 0;
    padding: 0.85rem 1.1rem;
    margin-bottom: 1.2rem;
    font-size: 0.85rem;
    color: #1e3a5f;
    line-height: 1.6;
  }}

  /* Section header */
  .section-header {{
    display: flex; align-items: center; gap: 0.6rem;
    margin: 2rem 0 1rem;
    border-bottom: 1px solid #e5e7eb;
    padding-bottom: 0.5rem;
  }}
  .section-header h3 {{ margin: 0; font-size: 0.95rem; font-weight: 600; color: #111; }}
  .section-header .pill {{
    background: {C_BLUE_BG}; color: {C_BLUE};
    font-size: 0.65rem; font-weight: 600;
    padding: 0.15rem 0.6rem; border-radius: 20px; letter-spacing: 0.06em;
  }}

  /* Welcome card */
  .welcome {{
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 16px;
    padding: 2rem 1.5rem;
    text-align: center;
    margin-bottom: 1.5rem;
  }}
  .welcome h2 {{ font-size: 1.3rem; color: #111; margin-bottom: 0.5rem; font-weight: 700; }}
  .welcome p  {{ color: {C_GREY}; font-size: 0.88rem; margin-bottom: 1rem; }}
  .steps-row  {{ display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap; margin-top: 1rem; }}
  .step-card  {{
    background: {C_GREY_BG}; border: 1px solid #e5e7eb; border-radius: 12px;
    padding: 1rem; width: 160px; text-align: center;
  }}
  .step-num   {{ font-size: 1.4rem; margin-bottom: 0.3rem; }}
  .step-title {{ font-weight: 600; font-size: 0.8rem; color: #111; margin-bottom: 0.2rem; }}
  .step-desc  {{ font-size: 0.73rem; color: {C_GREY}; }}

  /* ── Mobile overrides ── */
  @media (max-width: 768px) {{
    .block-container {{ padding-top: 0.75rem !important; padding-left: 0.75rem !important;
                        padding-right: 0.75rem !important; }}

    /* KPI grid → 2 columns */
    .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
    .kpi-val  {{ font-size: 1.15rem; }}
    .kpi-label {{ font-size: 0.6rem; }}

    /* Welcome */
    .welcome {{ padding: 1.5rem 1rem; }}
    .welcome h2 {{ font-size: 1.1rem; }}
    .step-card {{ width: 140px; padding: 0.85rem; }}

    /* Insight → stack insights vertically */
    .insight-box {{ font-size: 0.78rem; }}

    /* Section header */
    .section-header {{ margin: 1.5rem 0 0.75rem; }}
    .section-header h3 {{ font-size: 0.85rem; }}
    .section-header .pill {{ display: none; }}

    /* Plotly charts — enforce full width */
    .stPlotlyChart {{ width: 100% !important; }}

    /* Stack Streamlit columns vertically on mobile */
    [data-testid="stColumns"] {{ flex-direction: column !important; }}
    [data-testid="stColumn"]  {{ width: 100% !important; flex: 1 1 100% !important;
                                  min-width: 100% !important; }}

    /* Hide chart mode bar on mobile */
    .modebar {{ display: none !important; }}

    /* Dataframe → horizontal scroll */
    [data-testid="stDataFrame"] {{ overflow-x: auto; }}

    /* Buttons full width */
    .stButton > button {{ width: 100%; }}

    /* Text inputs full width */
    .stTextInput {{ width: 100% !important; }}
  }}

  @media (max-width: 480px) {{
    .kpi-grid {{ grid-template-columns: repeat(2, 1fr); gap: 0.5rem; }}
    .kpi {{ padding: 0.75rem 0.5rem; }}
    .kpi-val {{ font-size: 1rem; }}
    .steps-row {{ gap: 0.75rem; }}
    .step-card {{ width: 100%; max-width: 100%; }}
  }}
</style>
""", unsafe_allow_html=True)

PALETTE = ["#4a72a8","#dc2626","#16a34a","#e8a838","#a36eba","#5bbfbf","#e87b5b","#c4b49a"]

# ── Helpers ───────────────────────────────────────────────────────────────────
def fmt(v):
    return f"₹{abs(v):,.0f}"

def parse_inr(val):
    if isinstance(val, (int, float)):
        return float(val) if not pd.isna(val) else 0.0
    v = re.sub(r"[₹,\s]", "", str(val))
    if v.startswith("(") and v.endswith(")"):
        v = "-" + v[1:-1]
    try:
        return float(v)
    except ValueError:
        return 0.0

def delta_html(curr, prev):
    if prev == 0:
        return ""
    pct = ((curr - prev) / prev) * 100
    arrow = "↑" if pct > 0 else "↓"
    cls = "green" if pct < 0 else "red"   # spending ↑ is bad, ↓ is good
    return f'<div class="kpi-delta {cls}">{arrow} {abs(pct):.1f}% vs prev month</div>'

def savings_delta_html(curr, prev):
    if prev == 0:
        return ""
    pct = ((curr - prev) / prev) * 100
    arrow = "↑" if pct > 0 else "↓"
    cls = "green" if pct > 0 else "red"
    return f'<div class="kpi-delta {cls}">{arrow} {abs(pct):.1f}% vs prev month</div>'

def kpi_card(col, label, value, delta_html_str="", color=""):
    with col:
        st.markdown(f"""
        <div class="kpi">
          <div class="kpi-label">{label}</div>
          <div class="kpi-val {color}">{fmt(value)}</div>
          {delta_html_str}
        </div>""", unsafe_allow_html=True)


# ── Sample data ───────────────────────────────────────────────────────────────
SAMPLE_DATA = pd.DataFrame({
    "Month":                  ["Nov 2024","Dec 2024","Jan 2025","Feb 2025","Mar 2025","Apr 2025"],
    "Salary":                 [185000,185000,192000,192000,192000,192000],
    "Outgoing (Debits)":      [112000,138000, 98000,105000,121000, 95000],
    "Incoming (Credits)":     [191000,185000,195000,192000,198000,192000],
    "Net Cash":               [ 79000, 47000, 97000, 87000, 77000, 97000],
    "Fixed (Home+Child+HH)":  [ 42000, 42000, 42000, 42000, 42000, 42000],
    "Credit Card":            [ 28000, 45000, 18000, 22000, 31000, 16000],
    "Swiggy Credit Card":     [  6500,  9200,  4800,  5500,  7100,  4200],
    "Rupay Credit Card":      [  8200, 11500,  6400,  7800,  9300,  5900],
    "GPay / UPI Sent":        [ 17500, 23000, 14200, 16800, 21000, 13800],
    "Total Spent":            [102200,130700, 85400, 94100,110400, 81900],
    "MF Principal":           [ 25000, 25000, 30000, 30000, 30000, 30000],
    "MF with Interest":       [ 26800, 27500, 32200, 33100, 34500, 35800],
    "Recurring Deposit (RD)": [ 10000, 10000, 10000, 10000, 10000, 10000],
    "Stocks / ESPP":          [ 18500, 12000, 22000, 19500, 16800, 24000],
    "Total Savings":          [ 55300, 49500, 64200, 62600, 61300, 69800],
})


# ── MF notification parser ────────────────────────────────────────────────────
def parse_mf_notifications(text):
    results = []
    amount_pat = re.compile(r"(?:rs\.?|₹|inr)\s*([\d,]+)", re.I)
    date_pat   = re.compile(
        r"(\d{1,2}[-/]\w{3,9}[-/]\d{2,4}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\w+ \d{4})", re.I)
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        amounts = amount_pat.findall(line)
        if not amounts:
            continue
        amount = float(amounts[-1].replace(",", ""))
        date_match = date_pat.search(line)
        try:
            dt = pd.to_datetime(date_match.group(1), dayfirst=True) if date_match else pd.Timestamp.now()
        except Exception:
            dt = pd.Timestamp.now()
        results.append({"month": dt.to_period("M").strftime("%b %Y"), "amount": amount})
    return results


# ── Auto-compute monthly summary from transactions ───────────────────────────
def compute_monthly_summary(stmt_df, mf_rows=None, rd_rows=None):
    months = sorted(stmt_df["Month"].unique())
    mf_by_month = {}
    rd_by_month = {}
    if mf_rows:
        for r in mf_rows:
            mf_by_month[r["month"]] = mf_by_month.get(r["month"], 0) + r["amount"]
    if rd_rows:
        for r in rd_rows:
            rd_by_month[r["month"]] = rd_by_month.get(r["month"], 0) + r["amount"]
    rows = []
    for month in months:
        m   = stmt_df[stmt_df["Month"] == month]
        exp = m[m["Type"] == "Expense"]
        inc = m[m["Type"] == "Income"]
        salary    = inc[inc["Category"] == "Salary / Income"]["Credit"].sum()
        outgoing  = exp["Debit"].sum()
        incoming  = inc["Credit"].sum()
        net_cash  = incoming - outgoing
        fixed     = exp[exp["Category"] == "Rent & Housing"]["Debit"].sum()
        cc_bill   = exp[exp["Category"] == "Credit Card Bill"]["Debit"].sum()
        swiggy_cc = exp[exp["Description"].str.contains("swiggy", case=False, na=False)]["Debit"].sum()
        rupay_cc  = exp[exp["Description"].str.contains("rupay",  case=False, na=False)]["Debit"].sum()
        upi       = exp[exp["Category"] == "UPI / GPay"]["Debit"].sum()
        total_spent = outgoing
        inv = exp[exp["Category"] == "Investments"]
        mf_stmt  = inv[inv["Description"].str.contains(r"sip|mutual|mf\b|nfo|lumpsum", case=False, na=False)]["Debit"].sum()
        rd_stmt  = inv[inv["Description"].str.contains(r"\brd\b|recurring deposit", case=False, na=False)]["Debit"].sum()
        stocks   = inv[inv["Description"].str.contains(r"stock|espp|nsdl|cdsl|zerodha|groww|kuvera", case=False, na=False)]["Debit"].sum()
        mf_principal = mf_by_month.get(month, mf_stmt)
        rd_amount    = rd_by_month.get(month, rd_stmt)
        total_savings = mf_principal + rd_amount + stocks
        rows.append({
            "Month":                  month,
            "Salary":                 round(salary),
            "Outgoing (Debits)":      round(outgoing),
            "Incoming (Credits)":     round(incoming),
            "Net Cash":               round(net_cash),
            "Fixed (Home+Child+HH)":  round(fixed),
            "Credit Card":            round(cc_bill),
            "Swiggy Credit Card":     round(swiggy_cc),
            "Rupay Credit Card":      round(rupay_cc),
            "GPay / UPI Sent":        round(upi),
            "Total Spent":            round(total_spent),
            "MF Principal":           round(mf_principal),
            "MF with Interest":       round(mf_principal),
            "Recurring Deposit (RD)": round(rd_amount),
            "Stocks / ESPP":          round(stocks),
            "Total Savings":          round(total_savings),
        })
    return pd.DataFrame(rows)


# ── Bank statement helpers ────────────────────────────────────────────────────
CATEGORIES = {
    "Food & Dining":    ["zomato","swiggy","blinkit","restaurant","cafe","coffee",
                         "food","pizza","burger","kfc","mcdonalds","dominos"],
    "Transport":        ["uber","ola","rapido","metro","irctc","redbus","petrol",
                         "fuel","parking","makemytrip","goibibo"],
    "Shopping":         ["amazon","flipkart","myntra","ajio","nykaa","meesho",
                         "reliance","big bazaar","dmart"],
    "Utilities":        ["electricity","water","broadband","jio","airtel","vi ",
                         "bsnl","gas","wifi","tata power"],
    "Entertainment":    ["netflix","spotify","prime","hotstar","zee5","apple",
                         "bookmyshow","pvr","inox"],
    "Healthcare":       ["pharmacy","hospital","clinic","doctor","medical","apollo",
                         "medplus","1mg","pharmeasy"],
    "Rent & Housing":   ["rent","maintenance","housing","society","landlord"],
    "Investments":      ["mutual fund","sip","zerodha","groww","kuvera","lic",
                         "insurance premium","rd","recurring"],
    "Salary / Income":  ["salary","sal cr","neft cr","payroll","stipend"],
    "UPI / GPay":       ["upi","phonepe","gpay","google pay","paytm","bhim",
                         "neft","imps","rtgs"],
    "Credit Card Bill": ["hdfc bank credit","icici credit","axis bank credit",
                         "millenia","swiggy card","rupay"],
    "Subscriptions":    ["adobe","notion","zoom","microsoft","google one",
                         "icloud","dropbox","linkedin"],
}

def categorize(desc):
    if not isinstance(desc, str):
        return "Others"
    d = desc.lower()
    for cat, kws in CATEGORIES.items():
        if any(kw in d for kw in kws):
            return cat
    return "Others"

def detect_and_load(f):
    name = f.name.lower()
    try:
        if name.endswith((".xlsx",".xls")):
            raw = pd.read_excel(f, dtype=str)
        else:
            content = f.read().decode("utf-8", errors="replace")
            lines = content.splitlines()
            hi = 0
            for i, l in enumerate(lines):
                if re.search(r"(date|narration|description|debit|credit|amount)", l, re.I):
                    hi = i
                    break
            raw = pd.read_csv(StringIO("\n".join(lines[hi:])), dtype=str)
    except Exception as e:
        return None, str(e)
    raw.columns = raw.columns.str.strip().str.lower().str.replace(r"\s+", " ", regex=True)
    date_col   = next((c for c in raw.columns if re.search(r"\bdate\b", c)), None)
    desc_col   = next((c for c in raw.columns if re.search(r"narration|description|particular|details|remark|txn", c)), None)
    debit_col  = next((c for c in raw.columns if re.search(r"debit|withdrawal|dr\b", c)), None)
    credit_col = next((c for c in raw.columns if re.search(r"credit|deposit|cr\b", c)), None)
    amt_col    = next((c for c in raw.columns if re.search(r"^amount$", c)), None)
    if not date_col:
        return None, "No Date column found."
    if not desc_col:
        return None, "No Description/Narration column found."
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

# ── AI anonymizer ────────────────────────────────────────────────────────────
AI_PROMPT = """You are a financial data parser. Convert the pasted bank statement into clean CSV.

Output STRICTLY in CSV format with headers:
Date,Description,Debit,Credit

Rules:
- No extra text, no markdown, no code fences
- Dates in DD-MM-YYYY format
- Debit = money out (positive number), Credit = money in (positive number)
- Remove or replace: names, account numbers, PAN details, employer names
- Keep only transaction rows"""

def anonymize_statement(raw_text):
    api_key = st.secrets.get("CLAUDE_API_KEY", "")
    if not api_key:
        return None, "Anthropic API key not configured. Add `CLAUDE_API_KEY` to Streamlit secrets."
    try:
        client = _anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            system=AI_PROMPT,
            messages=[{"role": "user", "content": raw_text[:12000]}],
        )
        return msg.content[0].text.strip(), None
    except Exception as e:
        return None, str(e)


# ── Google OAuth helpers ──────────────────────────────────────────────────────
GMAIL_SCOPES   = ["https://www.googleapis.com/auth/gmail.readonly"]
GMAIL_QUERY    = ("has:attachment ("
                  "from:statements@hdfcbank.net OR from:alerts@icicibank.com OR "
                  "from:statements@axisbank.com OR from:alerts@kotakbank.com OR "
                  "subject:statement OR subject:e-statement OR subject:transaction)")

def _get_oauth_config():
    """Read client credentials from Streamlit secrets."""
    try:
        client_id     = st.secrets["GOOGLE_CLIENT_ID"]
        client_secret = st.secrets["GOOGLE_CLIENT_SECRET"]
        redirect_uri  = st.secrets.get("REDIRECT_URI", "http://localhost:8501")
        return client_id, client_secret, redirect_uri, None
    except Exception:
        return None, None, None, (
            "Google OAuth not configured. "
            "Add `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `REDIRECT_URI` "
            "to `.streamlit/secrets.toml`."
        )

def build_oauth_flow():
    client_id, client_secret, redirect_uri, err = _get_oauth_config()
    if err:
        return None, err
    flow = Flow.from_client_config(
        {"web": {
            "client_id":     client_id,
            "client_secret": client_secret,
            "auth_uri":      "https://accounts.google.com/o/oauth2/auth",
            "token_uri":     "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }},
        scopes=GMAIL_SCOPES,
        redirect_uri=redirect_uri,
    )
    return flow, None

def fetch_gmail_attachments_oauth(creds, max_results=50):
    """Fetch bank statement attachments via Gmail API using OAuth credentials."""
    attachments, errors = [], []
    try:
        service  = build("gmail", "v1", credentials=creds)
        response = service.users().messages().list(
            userId="me", q=GMAIL_QUERY, maxResults=max_results
        ).execute()
        messages = response.get("messages", [])

        def _extract_parts(parts, msg_id):
            for part in parts:
                if part.get("parts"):
                    _extract_parts(part["parts"], msg_id)
                fname = part.get("filename", "")
                if fname and any(fname.lower().endswith(e) for e in [".csv",".xlsx",".xls"]):
                    att_id = part["body"].get("attachmentId")
                    if att_id:
                        att  = service.users().messages().attachments().get(
                            userId="me", messageId=msg_id, id=att_id
                        ).execute()
                        data = base64.urlsafe_b64decode(att["data"] + "==")
                        attachments.append((fname, BytesIO(data)))

        for ref in messages:
            msg = service.users().messages().get(
                userId="me", id=ref["id"], format="full"
            ).execute()
            _extract_parts(msg.get("payload", {}).get("parts", []), ref["id"])

    except Exception as e:
        errors.append(str(e))
    return attachments, errors


# ══════════════════════════════════════════════════════════════════════════════
# PERSISTENT DATA: Load stored summaries from backend on each session start
# This answers the product question: data uploaded/connected in past sessions
# is immediately visible on the next login.
# ══════════════════════════════════════════════════════════════════════════════
if SUPABASE_AUTH_AVAILABLE and "backend_summaries_loaded" not in st.session_state:
    try:
        client = _get_api_client()
        summaries = asyncio.run(client.get_summary())
        if summaries:
            st.session_state["backend_summaries"] = summaries
        st.session_state["backend_summaries_loaded"] = True

        # Also check Gmail status
        gmail_status = asyncio.run(client.get_gmail_status())
        st.session_state["gmail_connected_backend"] = gmail_status.get("connected", False)
    except Exception:
        st.session_state["backend_summaries_loaded"] = True


# ══════════════════════════════════════════════════════════════════════════════
# OAUTH CALLBACK — must run before any UI is rendered (legacy local Gmail flow)
# ══════════════════════════════════════════════════════════════════════════════
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
# HEADER
# ══════════════════════════════════════════════════════════════════════════════
st.markdown(f"""
<div style="display:flex;align-items:center;justify-content:space-between;
            padding:0.5rem 0 1rem;border-bottom:2px solid #e5e7eb;margin-bottom:1.25rem;">
  <div>
    <span style="font-size:1.5rem;font-weight:700;color:#111;">💰 Money Clarity OS</span>
    <span style="font-size:0.82rem;color:{C_GREY};margin-left:0.75rem;">Personal Finance Dashboard</span>
  </div>
  <span style="font-size:0.75rem;color:{C_GREY};">🔒 Your data never leaves your device</span>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADING — 3 steps inline
# ══════════════════════════════════════════════════════════════════════════════
data_loaded   = "stmt_df" in st.session_state
summary_ready = "summary_df" in st.session_state

# Keep mf/rd text accessible even when expander is collapsed
mf_text = st.session_state.get("mf_notif", "")
rd_text = st.session_state.get("rd_notif", "")

# ── Welcome tile — shown above loader when no data yet ───────────────────────
if not summary_ready:
    st.markdown("""
    <div class="welcome">
      <h2>Welcome to Money Clarity OS 👋</h2>
      <p>Your personal finance dashboard — get a clear picture of where your money goes, automatically.</p>
      <div class="steps-row">
        <div class="step-card">
          <div class="step-num">📁</div>
          <div class="step-title">Step 1 — Load</div>
          <div class="step-desc">Upload your bank or credit card statement CSV</div>
        </div>
        <div class="step-card">
          <div class="step-num">📲</div>
          <div class="step-title">Step 2 — Enrich</div>
          <div class="step-desc">Paste MF/SIP alerts for investment tracking</div>
        </div>
        <div class="step-card">
          <div class="step-num">✨</div>
          <div class="step-title">Step 3 — Generate</div>
          <div class="step-desc">Your monthly dashboard appears instantly</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)


_exp_label = "✅ Data loaded — expand to reload or update" if data_loaded else "📂 Get started — load your statements below"
with st.expander(_exp_label, expanded=not data_loaded):
    s1, s2, s3 = st.columns([2, 1.5, 1.2])

    # ── Step 1: Load — PRIMARY ───────────────────────────────────────────────
    with s1:
        st.markdown(f'<p style="font-size:1rem;font-weight:700;color:#111;margin-bottom:0.4rem;">'
                    f'{"✅" if data_loaded else "①"}&nbsp; Load Your Statements</p>',
                    unsafe_allow_html=True)

        frames, load_errors = [], []

        # 🟢 Option A — direct upload (primary)
        uploads = st.file_uploader(
            "Upload your bank statement (CSV or XLSX)",
            type=["csv","xlsx","xls"],
            accept_multiple_files=True, key="stmt_upload",
            help="Export your statement as CSV from your bank's net banking portal"
        )
        if uploads:
            for f in uploads:
                dff, err = detect_and_load(f)
                if err:
                    load_errors.append(f"**{f.name}:** {err}")
                else:
                    frames.append(dff)
                    # If backend is available, persist to Supabase
                    if SUPABASE_AUTH_AVAILABLE:
                        try:
                            api = _get_api_client()
                            file_bytes = f.getvalue()
                            up_result = asyncio.run(api.upload_file(file_bytes, f.name))
                            parse_result = asyncio.run(api.parse_upload(up_result["upload_id"]))
                            st.caption(f"✅ Saved {parse_result['inserted']} transactions to your account")
                            # Invalidate cached summaries so they reload
                            st.session_state.pop("backend_summaries_loaded", None)
                        except Exception as _be:
                            st.caption(f"⚠️ Could not persist to backend: {_be}")

        # 🟡 Inline privacy helper — sits right below the uploader
        st.markdown(f'<p style="font-size:0.78rem;color:{C_GREY};margin-top:0.25rem;">'
                    f'🔒 Prefer to remove personal details first? Use this prompt in ChatGPT or Claude, then upload the result:</p>',
                    unsafe_allow_html=True)
        st.code("""Convert this bank statement into a CSV with columns: Date, Description, Debit, Credit.
Remove or anonymize: names, account numbers, PAN details, employer info.
Output CSV only — no extra text.""", language=None)

        # 📧 Gmail — clean inline option
        st.markdown(f'<div style="display:flex;align-items:center;gap:0.5rem;margin:0.75rem 0 0.5rem;">'
                    f'<hr style="flex:1;border:none;border-top:1px solid #e5e7eb;margin:0;">'
                    f'<span style="font-size:0.75rem;color:{C_GREY};white-space:nowrap;">or</span>'
                    f'<hr style="flex:1;border:none;border-top:1px solid #e5e7eb;margin:0;">'
                    f'</div>', unsafe_allow_html=True)

        # Backend-powered Gmail connect (preferred when auth available)
        if SUPABASE_AUTH_AVAILABLE and st.session_state.get("gmail_connected_backend"):
            gc1, gc2, gc3 = st.columns([2, 1, 1])
            with gc1:
                st.success("📧 Gmail connected (server-side)")
            with gc2:
                if st.button("Sync now", key="backend_sync_btn", use_container_width=True):
                    try:
                        api = _get_api_client()
                        result = asyncio.run(api.sync_gmail())
                        st.success(f"Synced: {result['new_files']} new files, {result['transactions_imported']} transactions")
                        st.session_state.pop("backend_summaries_loaded", None)
                    except Exception as e:
                        st.error(f"Sync failed: {e}")
            with gc3:
                st.caption(f"Last synced")
        elif SUPABASE_AUTH_AVAILABLE:
            if st.button("🔗 Connect Gmail (secure server-side)", use_container_width=True):
                try:
                    api = _get_api_client()
                    auth_url = asyncio.run(api.get_gmail_connect_url())
                    st.markdown(
                        f'<a href="{auth_url}" target="_blank">Click here to authorize Gmail access</a>',
                        unsafe_allow_html=True
                    )
                    st.info("After authorizing, return here and refresh the page to sync.")
                except Exception as e:
                    st.error(f"Could not initiate Gmail connect: {e}")
        elif "gmail_creds" in st.session_state:
            gc1, gc2, gc3 = st.columns([2, 1, 1])
            with gc1:
                st.success("📧 Gmail connected", icon=None)
            with gc2:
                fetch_clicked = st.button("Fetch", key="fetch_btn", use_container_width=True)
            with gc3:
                if st.button("Disconnect", key="disc_btn", use_container_width=True):
                    del st.session_state["gmail_creds"]
                    st.rerun()
            if fetch_clicked:
                max_emails = 50
                with st.spinner("Scanning Gmail for bank statements…"):
                    attachments, errs = fetch_gmail_attachments_oauth(
                        st.session_state["gmail_creds"], max_results=max_emails)
                for err in errs:
                    st.error(err)
                if attachments:
                    for fname, bio in attachments:
                        bio.name = fname
                        dff, err = detect_and_load(bio)
                        if err:
                            load_errors.append(f"**{fname}:** {err}")
                        else:
                            frames.append(dff)
                elif not errs:
                    st.warning("No CSV/XLSX attachments found in matching emails.")
        elif GOOGLE_LIBS_AVAILABLE:
            flow, err = build_oauth_flow()
            if not err:
                auth_url, _ = flow.authorization_url(
                    access_type="offline",
                    include_granted_scopes="true",
                    prompt="consent",
                )
                st.session_state["gmail_flow"] = flow
                st.markdown(f'''
                    <a href="{auth_url}" target="_self" style="
                        display:flex;align-items:center;justify-content:center;gap:0.6rem;
                        padding:0.65rem 1.25rem;
                        background:#ffffff;color:#3c4043;
                        border:1px solid #dadce0;border-radius:0.5rem;
                        text-decoration:none;font-weight:500;font-size:0.92rem;
                        box-shadow:0 1px 3px rgba(0,0,0,0.08);
                        width:100%;box-sizing:border-box;
                        transition:box-shadow 0.2s;">
                        <svg width="18" height="18" viewBox="0 0 48 48">
                          <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
                          <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
                          <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
                          <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.18 1.48-4.97 2.31-8.16 2.31-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
                        </svg>
                        Connect Gmail
                    </a>
                    <p style="font-size:0.72rem;color:{C_GREY};margin:0.4rem 0 0;text-align:center;">
                        🔒 Your password is never seen by this app
                    </p>
                    ''', unsafe_allow_html=True)

        for e in load_errors:
            st.warning(e)
        if frames:
            new_df = pd.concat(frames, ignore_index=True)
            st.session_state.stmt_df = new_df
            st.success(f"{len(new_df):,} transactions loaded.")

    # ── Step 2: Enrich — SECONDARY ───────────────────────────────────────────
    with s2:
        st.markdown(f'<p style="font-size:0.82rem;font-weight:500;color:{C_GREY};margin-bottom:0.2rem;">'
                    f'{"✅" if summary_ready else "②"}&nbsp; Investment Details'
                    f'&nbsp;<em style="font-weight:400;">— optional, add later</em></p>',
                    unsafe_allow_html=True)
        st.caption("Paste MF / SIP / RD SMS alerts — one per line")
        mf_text = st.text_area("MF / SIP alerts", height=85, key="mf_notif",
            placeholder="Your SIP of ₹10,000 towards Axis Bluechip debited on 05-Jan-2025")
        rd_text = st.text_area("RD alerts", height=65, key="rd_notif",
            placeholder="Your RD of ₹10,000 debited on 01-Jan-2025")

    # ── Step 3: Generate — ACTION ────────────────────────────────────────────
    with s3:
        st.markdown(f'<p style="font-size:0.95rem;font-weight:600;color:{C_BLUE};margin-bottom:0.4rem;">'
                    f'{"✅" if summary_ready else "③"}&nbsp; Generate Dashboard</p>',
                    unsafe_allow_html=True)
        st.write("")
        _data_now = "stmt_df" in st.session_state
        if _data_now:
            if st.button("✨ Generate Monthly Summary", type="primary",
                         key="gen_btn", use_container_width=True):
                _mf = parse_mf_notifications(mf_text) if mf_text.strip() else []
                _rd = parse_mf_notifications(rd_text)  if rd_text.strip() else []
                computed = compute_monthly_summary(st.session_state.stmt_df, _mf, _rd)
                st.session_state.summary_df = computed
                st.success(f"Done! {len(computed)} months generated.")
                st.rerun()
        else:
            st.button("✨ Generate Monthly Summary", disabled=True,
                      use_container_width=True,
                      help="Load your statements first (Step 1)")
        st.caption("🔒 Data stays on your device")

data_loaded   = "stmt_df" in st.session_state
summary_ready = "summary_df" in st.session_state

# ── Welcome / empty state ─────────────────────────────────────────────────────
if not summary_ready:



    st.markdown("#### Preview — what your dashboard will look like")
    df_preview = SAMPLE_DATA.copy()
    use_df = df_preview
    is_preview = True
else:
    use_df = st.session_state.summary_df.copy()
    is_preview = False

# ── Mockup banner ─────────────────────────────────────────────────────────────
if is_preview:
    st.markdown("""
    <div style="background:#eff6ff;border:1.5px solid #93c5fd;border-radius:0.6rem;
                padding:0.65rem 1rem;margin-bottom:1rem;display:flex;
                align-items:center;gap:0.6rem;">
      <span style="font-size:1.1rem;">🔵</span>
      <span style="color:#1d4ed8;font-size:0.85rem;">
        <b>This is sample/mockup data.</b> Your real numbers will appear here once you
        upload your bank statements from the sidebar.
      </span>
    </div>
    """, unsafe_allow_html=True)

# ── Parse numeric columns ─────────────────────────────────────────────────────
num_cols = [c for c in use_df.columns if c != "Month"]
for c in num_cols:
    use_df[c] = use_df[c].apply(parse_inr)

if use_df.empty or use_df["Salary"].sum() == 0:
    st.stop()

# ── Auto-insights ─────────────────────────────────────────────────────────────
if not is_preview and len(use_df) > 1:
    insights = []
    max_spend_row = use_df.loc[use_df["Total Spent"].idxmax()]
    min_spend_row = use_df.loc[use_df["Total Spent"].idxmin()]
    max_save_row  = use_df.loc[use_df["Total Savings"].idxmax()]
    avg_save = use_df["Total Savings"].mean()
    last_save = use_df["Total Savings"].iloc[-1]
    insights.append(f"🔴 Highest spend month: <b>{max_spend_row['Month']}</b> at {fmt(max_spend_row['Total Spent'])}")
    insights.append(f"🟢 Best savings month: <b>{max_save_row['Month']}</b> at {fmt(max_save_row['Total Savings'])}")
    if last_save > avg_save:
        insights.append(f"📈 Your latest month savings ({fmt(last_save)}) are above your average ({fmt(avg_save)}) — keep it up!")
    else:
        insights.append(f"📉 Your latest month savings ({fmt(last_save)}) are below your average ({fmt(avg_save)}) — room to improve.")

    st.markdown(
        '<div class="insight-box">💡 <b>Quick Insights</b><br>' +
        " &nbsp;|&nbsp; ".join(insights) + "</div>",
        unsafe_allow_html=True
    )

# ── KPI cards with delta ──────────────────────────────────────────────────────
st.markdown('<div class="section-header"><h3>Monthly Overview</h3><span class="pill">SUMMARY</span></div>', unsafe_allow_html=True)

last  = use_df.iloc[-1]
prev  = use_df.iloc[-2] if len(use_df) > 1 else last

c1, c2, c3, c4, c5 = st.columns(5)
kpi_card(c1, "Salary",        last["Salary"],        savings_delta_html(last["Salary"], prev["Salary"]),       "green")
kpi_card(c2, "Total Incoming",last["Incoming (Credits)"], savings_delta_html(last["Incoming (Credits)"], prev["Incoming (Credits)"]), "green")
kpi_card(c3, "Total Outgoing",last["Outgoing (Debits)"],  delta_html(last["Outgoing (Debits)"], prev["Outgoing (Debits)"]),          "red")
kpi_card(c4, "Total Spent",   last["Total Spent"],   delta_html(last["Total Spent"], prev["Total Spent"]),     "red")
kpi_card(c5, "Total Savings", last["Total Savings"],  savings_delta_html(last["Total Savings"], prev["Total Savings"]), "green")

st.markdown("<br>", unsafe_allow_html=True)

# ── Editable tracker table ────────────────────────────────────────────────────
if not is_preview:
    with st.expander("📋 View & Edit Monthly Tracker", expanded=False):
        edited = st.data_editor(use_df, width="stretch", num_rows="dynamic", key="summary_editor")
        st.session_state.summary_df = edited
        col_dl, _ = st.columns([1, 4])
        with col_dl:
            st.download_button("⬇️ Export CSV", edited.to_csv(index=False).encode("utf-8"),
                               "money_clarity.csv", "text/csv")

# ── Spend Breakdown chart (stacked) ──────────────────────────────────────────
st.markdown('<div class="section-header"><h3>Monthly Spend Breakdown</h3><span class="pill">WHERE IT GOES</span></div>', unsafe_allow_html=True)

EXP_COLS = {
    "Fixed (Home+Child+HH)": "Fixed",
    "Credit Card":            "Credit Card",
    "Swiggy Credit Card":     "Swiggy CC",
    "Rupay Credit Card":      "Rupay CC",
    "GPay / UPI Sent":        "GPay / UPI",
}
avail_exp = {k: v for k, v in EXP_COLS.items() if k in use_df.columns}
if avail_exp:
    stack_df = use_df[["Month"] + list(avail_exp.keys())].rename(columns=avail_exp)
    melted   = stack_df.melt(id_vars="Month", var_name="Category", value_name="Amount")
    melted   = melted[melted["Amount"] > 0]
    fig_stack = px.bar(melted, x="Month", y="Amount", color="Category",
                       barmode="stack", color_discrete_sequence=PALETTE,
                       labels={"Amount":"₹","Month":""})
    if "Total Spent" in use_df.columns:
        fig_stack.add_scatter(
            x=use_df["Month"], y=use_df["Total Spent"],
            mode="lines+markers+text", name="Total Spent",
            text=[f"₹{v:,.0f}" for v in use_df["Total Spent"]],
            textposition="top center",
            line=dict(color="#111", width=2, dash="dot"),
            marker=dict(size=7, color="#111"),
        )
    fig_stack.update_layout(height=360, margin=dict(t=20,b=10),
                            legend=dict(orientation="h", y=-0.18),
                            plot_bgcolor="#ffffff", paper_bgcolor="#ffffff")
    st.plotly_chart(fig_stack, width="stretch", config={"displayModeBar": False, "responsive": True})

# ── Savings & Net Cash ────────────────────────────────────────────────────────
st.markdown('<div class="section-header"><h3>Savings & Net Position</h3><span class="pill">FINANCIAL HEALTH</span></div>', unsafe_allow_html=True)

sa, sb = st.columns(2)

with sa:
    sav_cols = ["Month","MF Principal","MF with Interest","Recurring Deposit (RD)","Stocks / ESPP"]
    avail_s  = [c for c in sav_cols if c in use_df.columns]
    if len(avail_s) > 1:
        melted_s = use_df[avail_s].melt(id_vars="Month", var_name="Type", value_name="Value")
        melted_s = melted_s[melted_s["Value"] > 0]
        fig_sav = px.line(melted_s, x="Month", y="Value", color="Type",
                          markers=True, color_discrete_sequence=PALETTE,
                          labels={"Value":"₹","Month":""},
                          title="Savings Growth Over Time")
        fig_sav.update_layout(height=300, margin=dict(t=40,b=10),
                               legend=dict(orientation="h", y=-0.2),
                               plot_bgcolor="#ffffff", paper_bgcolor="#ffffff")
        st.plotly_chart(fig_sav, width="stretch", config={"displayModeBar": False, "responsive": True})

with sb:
    if "Net Cash" in use_df.columns:
        net_df = use_df[["Month","Net Cash"]].copy()
        net_df["colour"] = net_df["Net Cash"].apply(lambda x: "#16a34a" if x >= 0 else "#dc2626")
        fig_net = go.Figure(go.Bar(
            x=net_df["Month"], y=net_df["Net Cash"],
            marker_color=net_df["colour"],
            text=[fmt(v) for v in net_df["Net Cash"]],
            textposition="outside",
        ))
        fig_net.add_hline(y=0, line_dash="dot", line_color="#aaa")
        fig_net.update_layout(height=300, margin=dict(t=40,b=10),
                               title="Net Cash by Month (green = surplus)",
                               yaxis_title="₹", xaxis_title="",
                               plot_bgcolor="#ffffff", paper_bgcolor="#ffffff")
        st.plotly_chart(fig_net, width="stretch", config={"displayModeBar": False, "responsive": True})

# ── Salary vs Outgoing ────────────────────────────────────────────────────────
trend_cols = ["Month","Salary","Outgoing (Debits)","Incoming (Credits)"]
avail_t    = [c for c in trend_cols if c in use_df.columns]
melted_t   = use_df[avail_t].melt(id_vars="Month", var_name="Type", value_name="Amount")
fig_trend  = px.bar(melted_t, x="Month", y="Amount", color="Type", barmode="group",
                    color_discrete_sequence=["#16a34a","#dc2626","#4a72a8"],
                    labels={"Amount":"₹","Month":""},
                    title="Salary vs Outgoing vs Incoming")
fig_trend.update_layout(height=300, margin=dict(t=40,b=10),
                         legend=dict(orientation="h", y=-0.2),
                         plot_bgcolor="#ffffff", paper_bgcolor="#ffffff")
st.plotly_chart(fig_trend, width="stretch", config={"displayModeBar": False, "responsive": True})


# ══════════════════════════════════════════════════════════════════════════════
# SPEND ANALYSIS — from bank statements
# ══════════════════════════════════════════════════════════════════════════════
if data_loaded:
    st.markdown('<div class="section-header"><h3>Spend Analysis</h3><span class="pill">FROM YOUR STATEMENTS</span></div>', unsafe_allow_html=True)

    df_raw = st.session_state.stmt_df.copy()

    fa, fb, fc = st.columns(3)
    with fa:
        months = sorted(df_raw["Month"].unique())
        sel_m  = st.multiselect("Filter by Month", months, default=months, key="f_month")
    with fb:
        cats   = sorted(df_raw["Category"].unique())
        sel_c  = st.multiselect("Filter by Category", cats, default=cats, key="f_cat")
    with fc:
        sel_t  = st.multiselect("Filter by Type", ["Income","Expense"],
                                default=["Income","Expense"], key="f_type")

    df = df_raw[
        df_raw["Month"].isin(sel_m) &
        df_raw["Category"].isin(sel_c) &
        df_raw["Type"].isin(sel_t)
    ]

    if df.empty:
        st.info("No transactions match your filters.")
    else:
        total_in  = df[df["Type"]=="Income"]["Credit"].sum()
        total_out = df[df["Type"]=="Expense"]["Debit"].sum()
        net       = total_in - total_out

        k1, k2, k3, k4 = st.columns(4)
        kpi_card(k1, "Total Income",     total_in,  "", "green")
        kpi_card(k2, "Total Expenses",   total_out, "", "red")
        kpi_card(k3, "Net",              net,       "", "green" if net >= 0 else "red")
        with k4:
            st.markdown(f'<div class="kpi"><div class="kpi-label">Transactions</div>'
                        f'<div class="kpi-val">{len(df):,}</div></div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        expenses = df[df["Type"]=="Expense"].copy()

        r1a, r1b = st.columns(2)
        with r1a:
            ec = expenses.groupby("Category")["Debit"].sum().reset_index().sort_values("Debit", ascending=False)
            if not ec.empty:
                ec["pct"] = (ec["Debit"]/ec["Debit"].sum()*100).round(1)
                fig_tree = px.treemap(ec, path=["Category"], values="Debit",
                                      color="Debit",
                                      color_continuous_scale=["#f0f4fa","#8aaed6","#4a72a8"],
                                      custom_data=["pct"],
                                      title="Where did my money go?")
                fig_tree.update_traces(
                    texttemplate="<b>%{label}</b><br>₹%{value:,.0f}<br>%{customdata[0]}%",
                    textfont_size=12)
                fig_tree.update_layout(height=340, margin=dict(t=40,b=5), coloraxis_showscale=False)
                st.plotly_chart(fig_tree, width="stretch", config={"displayModeBar": False, "responsive": True})

        with r1b:
            mo_exp = expenses.groupby("Month")["Debit"].sum().reset_index()
            mo_exp["colour"] = ["#dc2626" if v==mo_exp["Debit"].max() else "#4a72a8" for v in mo_exp["Debit"]]
            fig_mo = go.Figure(go.Bar(
                x=mo_exp["Month"], y=mo_exp["Debit"],
                marker_color=mo_exp["colour"],
                text=[fmt(v) for v in mo_exp["Debit"]],
                textposition="outside",
            ))
            fig_mo.update_layout(height=340, margin=dict(t=40,b=5),
                                  title="Spend by Month  🔴 = highest",
                                  yaxis_title="₹", xaxis_title="",
                                  plot_bgcolor="#ffffff", paper_bgcolor="#ffffff")
            st.plotly_chart(fig_mo, width="stretch", config={"displayModeBar": False, "responsive": True})

        r2a, r2b = st.columns(2)
        with r2a:
            merchants = (expenses.groupby("Description")["Debit"].sum()
                         .sort_values(ascending=False).head(10).reset_index())
            merchants["Description"] = merchants["Description"].str[:35]
            fig_m = px.bar(merchants, x="Debit", y="Description", orientation="h",
                           color="Debit", color_continuous_scale=["#c8d8ee","#4a72a8"],
                           text=[fmt(v) for v in merchants["Debit"]],
                           labels={"Debit":"₹","Description":""},
                           title="Top 10 Merchants")
            fig_m.update_traces(textposition="outside")
            fig_m.update_layout(height=340, margin=dict(t=40,b=5),
                                 yaxis=dict(autorange="reversed"),
                                 coloraxis_showscale=False,
                                 plot_bgcolor="#ffffff", paper_bgcolor="#ffffff")
            st.plotly_chart(fig_m, width="stretch", config={"displayModeBar": False, "responsive": True})

        with r2b:
            exp_dow = expenses.copy()
            exp_dow["DayOfWeek"] = exp_dow["Date"].dt.day_name()
            dow_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
            dow = exp_dow.groupby("DayOfWeek")["Debit"].sum().reindex(dow_order).fillna(0).reset_index()
            dow["colour"] = ["#dc2626" if v==dow["Debit"].max() else "#4a72a8" for v in dow["Debit"]]
            fig_dow = go.Figure(go.Bar(
                x=dow["DayOfWeek"], y=dow["Debit"],
                marker_color=dow["colour"],
                text=[fmt(v) for v in dow["Debit"]],
                textposition="outside",
            ))
            fig_dow.update_layout(height=340, margin=dict(t=40,b=5),
                                   title="When do I spend most?  🔴 = peak day",
                                   yaxis_title="₹", xaxis_title="",
                                   plot_bgcolor="#ffffff", paper_bgcolor="#ffffff")
            st.plotly_chart(fig_dow, width="stretch", config={"displayModeBar": False, "responsive": True})

        # Heatmap
        st.markdown("**Spend Heatmap — Category × Month**")
        st.caption("Darker = higher spend. Spot patterns at a glance.")
        pivot = expenses.groupby(["Category","Month"])["Debit"].sum().unstack(fill_value=0)
        if not pivot.empty:
            fig_heat = px.imshow(pivot,
                                  color_continuous_scale=["#f9fafb","#94a3b8","#111827"],
                                  aspect="auto", text_auto=".0f",
                                  labels=dict(x="Month", y="Category", color="₹"))
            fig_heat.update_traces(textfont_size=11)
            fig_heat.update_layout(height=max(280, len(pivot)*36), margin=dict(t=10,b=10))
            st.plotly_chart(fig_heat, width="stretch", config={"displayModeBar": False, "responsive": True})

        r4a, r4b = st.columns(2)
        with r4a:
            daily = expenses.groupby("Date")["Debit"].sum().reset_index()
            fig_daily = px.area(daily, x="Date", y="Debit",
                                color_discrete_sequence=["#dc2626"],
                                labels={"Debit":"₹","Date":""},
                                title="Daily Spending Pattern")
            fig_daily.update_layout(height=260, margin=dict(t=40,b=5),
                                     plot_bgcolor="#ffffff", paper_bgcolor="#ffffff")
            st.plotly_chart(fig_daily, width="stretch", config={"displayModeBar": False, "responsive": True})

        with r4b:
            mo_both = df.groupby(["Month","Type"]).agg(D=("Debit","sum"),C=("Credit","sum")).reset_index()
            mo_both["Val"] = mo_both.apply(lambda r: r["C"] if r["Type"]=="Income" else r["D"], axis=1)
            fig_mo2 = px.bar(mo_both, x="Month", y="Val", color="Type", barmode="group",
                             color_discrete_map={"Income":"#16a34a","Expense":"#dc2626"},
                             labels={"Val":"₹","Month":""},
                             title="Income vs Expense by Month")
            fig_mo2.update_layout(height=260, margin=dict(t=40,b=5),
                                   legend=dict(orientation="h",y=-0.25),
                                   plot_bgcolor="#ffffff", paper_bgcolor="#ffffff")
            st.plotly_chart(fig_mo2, width="stretch", config={"displayModeBar": False, "responsive": True})

        # Transactions
        st.markdown('<div class="section-header"><h3>Transactions</h3><span class="pill">DRILL DOWN</span></div>', unsafe_allow_html=True)
        search = st.text_input("🔍 Search transactions",
                               placeholder="Type merchant, category or amount…", key="txn_search")
        disp = df[["Date","Description","Type","Category","Debit","Credit","Source"]].copy()
        disp["Date"] = disp["Date"].dt.strftime("%d %b %Y")
        if search:
            disp = disp[disp["Description"].str.contains(search, case=False, na=False)]
        st.dataframe(disp, width="stretch", height=360,
                     column_config={
                         "Debit":  st.column_config.NumberColumn("Debit ₹",  format="₹%.0f"),
                         "Credit": st.column_config.NumberColumn("Credit ₹", format="₹%.0f"),
                     })
        st.download_button("⬇️ Export transactions as CSV",
                           disp.to_csv(index=False).encode("utf-8"),
                           "money_clarity_transactions.csv", "text/csv")
