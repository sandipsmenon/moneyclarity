"""
Supabase Auth integration for Streamlit.

Login flows supported:
  1. Email magic link — user clicks link in email → fragment handler converts
     #access_token=... to ?access_token=... → handle_auth_callback logs in
  2. Email OTP — user types 6-digit code from email → verify_otp logs in
  3. Google OAuth (PKCE) — user clicks Google button → ?code= callback

Supabase magic links use the implicit flow (tokens in URL fragment #).
Streamlit Python cannot read URL fragments, so we inject a tiny JS snippet
(inject_fragment_handler) that converts the fragment to a query param and
reloads the page — after which Python can read and process it.
"""

import streamlit as st
import streamlit.components.v1 as components
from supabase import Client, create_client


@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    anon_key = st.secrets["SUPABASE_ANON_KEY"]
    return create_client(url, anon_key)


def init_auth_state() -> None:
    if "sb_session" not in st.session_state:
        st.session_state["sb_session"] = None
    if "sb_user" not in st.session_state:
        st.session_state["sb_user"] = None


def _inject_fragment_handler() -> None:
    """
    JS bridge: Supabase magic links redirect with tokens in the URL fragment
    (e.g. #access_token=...). Streamlit Python can't read fragments — only JS can.
    This snippet detects the fragment, moves the tokens to query params, and
    reloads so Python's handle_auth_callback can finish the login.
    """
    components.html("""
    <script>
    (function() {
        var hash = window.parent.location.hash;
        if (hash && hash.indexOf('access_token=') !== -1) {
            var p = new URLSearchParams(hash.substring(1));
            var at = p.get('access_token'), rt = p.get('refresh_token') || '';
            if (at) {
                window.parent.history.replaceState(null, '',
                    window.parent.location.pathname +
                    '?access_token=' + encodeURIComponent(at) +
                    (rt ? '&refresh_token=' + encodeURIComponent(rt) : ''));
                window.parent.location.reload();
            }
        }
    })();
    </script>
    """, height=0)


def get_session():
    return st.session_state.get("sb_session")


def get_access_token() -> str | None:
    session = get_session()
    return session.access_token if session else None


def get_user():
    return st.session_state.get("sb_user")


def is_authenticated() -> bool:
    return get_session() is not None


def login_with_magic_link(email: str) -> bool:
    """Send magic link / OTP email. Returns True on success."""
    supabase = get_supabase()
    redirect_to = st.secrets.get("SITE_URL", "http://localhost:8501")
    try:
        supabase.auth.sign_in_with_otp({
            "email": email,
            "options": {"email_redirect_to": redirect_to},
        })
        return True
    except Exception as e:
        st.error(f"Login error: {e}")
        return False


def verify_otp(email: str, token: str) -> bool:
    """Verify 6-digit OTP from email. Stores session on success."""
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
    """Get Google OAuth URL from Supabase. Returns URL for user to open."""
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
    Process Supabase auth callbacks. Call at the top of every page.

    Handles three cases:
      - ?code=...         PKCE flow (Google OAuth, newer Supabase magic links)
      - ?access_token=... Implicit flow (magic link, converted from fragment by JS)
      - Neither           No callback pending; run JS fragment handler for next reload
    """
    # Always inject the fragment-to-querystring bridge.
    # On first load after magic link click: JS detects #access_token, converts,
    # and reloads. On the reload: Python finds ?access_token and logs in.
    _inject_fragment_handler()

    params = st.query_params

    # PKCE flow — Google OAuth or newer Supabase.
    # Guard: skip if already authenticated — prevents trying to exchange a Gmail
    # OAuth ?code= as a Supabase auth code (both use the same param name).
    code = params.get("code")
    if code and not is_authenticated():
        supabase = get_supabase()
        try:
            resp = supabase.auth.exchange_code_for_session({"auth_code": code})
            if resp.session:
                st.session_state["sb_session"] = resp.session
                st.session_state["sb_user"] = resp.user
                st.query_params.clear()
                return True
        except Exception as e:
            st.error(f"Auth callback error: {e}")
        return False

    # Implicit flow — magic link (fragment converted to query param by JS above)
    access_token = params.get("access_token")
    if access_token:
        refresh_token = params.get("refresh_token", "")
        supabase = get_supabase()
        try:
            resp = supabase.auth.set_session(access_token, refresh_token)
            if resp.session:
                st.session_state["sb_session"] = resp.session
                st.session_state["sb_user"] = resp.user
                st.query_params.clear()
                return True
        except Exception as e:
            st.error(f"Magic link login error: {e}")
        return False

    return False


def refresh_session() -> bool:
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
    supabase = get_supabase()
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    st.session_state["sb_session"] = None
    st.session_state["sb_user"] = None
    st.rerun()


def render_login_ui() -> None:
    st.markdown("## Sign in to Money Clarity")

    tab_otp, tab_google = st.tabs(["Email", "Google"])

    with tab_otp:
        email = st.text_input("Email address", placeholder="you@example.com", key="login_email")
        if "otp_sent" not in st.session_state:
            st.session_state["otp_sent"] = False

        if not st.session_state["otp_sent"]:
            if st.button("Send login email", use_container_width=True):
                if email:
                    if login_with_magic_link(email):
                        st.session_state["otp_sent"] = True
                        st.session_state["otp_email"] = email
                        st.rerun()
                else:
                    st.warning("Please enter your email")
        else:
            st.success("Email sent! Check your inbox.")
            st.info(
                "**Option 1 — click the link** in the email. "
                "You'll be logged in automatically when it redirects back here.\n\n"
                "**Option 2 — enter the 6-digit code** below (shown in some email clients)."
            )
            otp = st.text_input("6-digit code (optional)", max_chars=6, key="otp_input")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Verify code", use_container_width=True, type="primary"):
                    if otp:
                        if verify_otp(st.session_state.get("otp_email", ""), otp):
                            st.success("Logged in!")
                            st.rerun()
                        else:
                            st.error("Invalid or expired code")
                    else:
                        st.warning("Enter the 6-digit code from your email")
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
