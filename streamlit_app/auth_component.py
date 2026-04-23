"""
Supabase Auth integration for Streamlit.

RECOMMENDED pattern: supabase-py (Python client) handles auth.
  - Signs in with Supabase (Google OAuth provider)
  - Stores session in st.session_state
  - Auto-refreshes token via supabase client
  - Passes access_token as Bearer header to FastAPI

How login works:
  1. User clicks "Sign in with Google"
  2. We generate OAuth URL via Supabase and open it in a new tab
  3. Supabase handles Google consent screen
  4. Supabase redirects back with tokens in URL fragment (#access_token=...)
  5. We parse the fragment via st.query_params and store in session_state
  6. Subsequent API calls use the stored access_token

Note: Streamlit doesn't directly access URL fragments (JS-only).
      We use a Supabase magic link / PKCE flow instead:
      - User enters email for magic link (no password)
      - OR use Supabase's implicit flow with st.query_params for the token
"""

import streamlit as st
from supabase import Client, create_client


@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    anon_key = st.secrets["SUPABASE_ANON_KEY"]
    return create_client(url, anon_key)


def init_auth_state() -> None:
    """Initialize auth-related session state keys."""
    if "sb_session" not in st.session_state:
        st.session_state["sb_session"] = None
    if "sb_user" not in st.session_state:
        st.session_state["sb_user"] = None


def get_session():
    """Return current Supabase session or None."""
    return st.session_state.get("sb_session")


def get_access_token() -> str | None:
    session = get_session()
    return session.access_token if session else None


def get_user():
    return st.session_state.get("sb_user")


def is_authenticated() -> bool:
    return get_session() is not None


def login_with_magic_link(email: str) -> bool:
    """Send OTP magic link to email. Returns True on success."""
    supabase = get_supabase()
    try:
        supabase.auth.sign_in_with_otp({"email": email})
        return True
    except Exception as e:
        st.error(f"Login error: {e}")
        return False


def verify_otp(email: str, token: str) -> bool:
    """Verify OTP from email. Stores session on success."""
    supabase = get_supabase()
    try:
        resp = supabase.auth.verify_otp({"email": email, "token": token, "type": "email"})
        if resp.session:
            st.session_state["sb_session"] = resp.session
            st.session_state["sb_user"] = resp.user
            return True
        return False
    except Exception as e:
        st.error(f"OTP verification error: {e}")
        return False


def login_with_google() -> str:
    """
    Get Google OAuth URL from Supabase.
    Returns URL for user to open in a new tab.
    Supabase handles the Google consent and redirects back to SITE_URL.
    """
    supabase = get_supabase()
    redirect_to = st.secrets.get("SITE_URL", "http://localhost:8501")
    resp = supabase.auth.sign_in_with_oauth({
        "provider": "google",
        "options": {
            "redirect_to": redirect_to,
            "scopes": "openid email profile",
        },
    })
    return resp.url


def handle_auth_callback() -> bool:
    """
    Handle Supabase auth callback from URL query params.
    Supabase redirects with ?code=... for PKCE flow.
    Call this at the top of your Streamlit page.
    """
    params = st.query_params
    code = params.get("code")
    if not code:
        return False

    supabase = get_supabase()
    try:
        resp = supabase.auth.exchange_code_for_session({"auth_code": code})
        if resp.session:
            st.session_state["sb_session"] = resp.session
            st.session_state["sb_user"] = resp.user
            # Clean URL — remove the code param
            st.query_params.clear()
            return True
    except Exception as e:
        st.error(f"Auth callback error: {e}")
    return False


def refresh_session() -> bool:
    """Attempt to refresh the access token using the stored refresh token."""
    session = get_session()
    if not session:
        return False
    supabase = get_supabase()
    try:
        resp = supabase.auth.refresh_session(session.refresh_token)
        if resp.session:
            st.session_state["sb_session"] = resp.session
            st.session_state["sb_user"] = resp.user
            return True
    except Exception:
        pass
    logout()
    return False


def logout() -> None:
    """
    Log out: invalidate session client-side and clear server session.
    This answers the product question: Supabase Auth supports clean logout.
    """
    supabase = get_supabase()
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    st.session_state["sb_session"] = None
    st.session_state["sb_user"] = None
    st.rerun()


def render_login_ui() -> None:
    """
    Render the login form. Supports:
      1. Magic link / OTP (recommended for production)
      2. Google OAuth button (opens new tab)
    """
    st.markdown("## 🔐 Sign in to Money Clarity")

    tab_otp, tab_google = st.tabs(["Email OTP", "Google"])

    with tab_otp:
        email = st.text_input("Email address", placeholder="you@example.com", key="login_email")
        if "otp_sent" not in st.session_state:
            st.session_state["otp_sent"] = False

        if not st.session_state["otp_sent"]:
            if st.button("Send magic link", use_container_width=True):
                if email:
                    if login_with_magic_link(email):
                        st.session_state["otp_sent"] = True
                        st.session_state["otp_email"] = email
                        st.success("Check your email for the 6-digit code!")
                        st.rerun()
                else:
                    st.warning("Please enter your email")
        else:
            otp = st.text_input("Enter the 6-digit code from your email", max_chars=6, key="otp_input")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Verify", use_container_width=True, type="primary"):
                    if verify_otp(st.session_state.get("otp_email", ""), otp):
                        st.success("Logged in successfully!")
                        st.rerun()
                    else:
                        st.error("Invalid or expired code")
            with col2:
                if st.button("← Back", use_container_width=True):
                    st.session_state["otp_sent"] = False
                    st.rerun()

    with tab_google:
        st.markdown("Sign in with your Google account.")
        if st.button("Sign in with Google", use_container_width=True):
            url = login_with_google()
            st.markdown(
                f'<a href="{url}" target="_blank"><button style="width:100%;padding:8px;">Open Google Sign-in</button></a>',
                unsafe_allow_html=True,
            )
            st.info("After signing in with Google, return here and refresh the page.")
