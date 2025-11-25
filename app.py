import streamlit as st
import requests
import pandas as pd
import re
import io
import zipfile
from urllib.parse import urljoin
from bs4 import BeautifulSoup

st.set_page_config(page_title="TrackTik PDF Downloader", layout="wide")

st.title("📄 TrackTik Bulk PDF Downloader")

# -----------------------------
# Helper functions
# -----------------------------
def safe_filename(s: str) -> str:
    """Sanitize filenames"""
    return re.sub(r'[\\/*?:"<>|]', "_", str(s))

def perform_login(username, password, base_url):
    """Login to TrackTik, returns session and message"""
    session = requests.Session()
    login_page_url = urljoin(base_url, "")

    # GET login page to fetch CSRF token
    try:
        r = session.get(login_page_url, timeout=15)
    except Exception as e:
        return None, f"❌ Could not load login page: {e}"

    if r.status_code != 200:
        return None, f"❌ Could not load login page (status {r.status_code})"

    # Parse CSRF token
    soup = BeautifulSoup(r.text, "html.parser")
    token_input = soup.find("input", {"name": "_csrf_token"})
    if not token_input:
        return None, "❌ CSRF token not found on login page"
    csrf_token = token_input.get("value")

    # POST login
    payload = {
        "email": username,
        "password": password,
        "_csrf_token": csrf_token,
        "locale": "en_us",
        "submit": "Login"
    }
    login_action = "/form/secursignin/signin"
    login_url = urljoin(base_url, login_action)

    try:
        resp = session.post(login_url, data=payload, allow_redirects=True, timeout=15)
    except Exception as e:
        return None, f"❌ Login request failed: {e}"

    # Check success heuristically
    if resp.status_code == 200 and "logout" in resp.text.lower():
        return session, "✅ Login successful!"
    elif resp.status_code in [200, 302]:
        return session, "✅ Login sent; check session cookies"
    else:
        return None, f"❌ Login failed (HTTP {resp.status_code})"

# -----------------------------
# Streamlit UI
# -----------------------------
base_url = st.text_input("Enter TrackTik portal base URL", placeholder="https://client.tracktik.com/")
username = st.text_input("Username")
password = st.text_input("Password", type="password")

if st.button("Login"):
    if not base_url or not username or not password:
        st.error("Please fill all fields")
    else:
        session, msg = perform_login(username, password, base_url)
        if session:
            st.session_state.session = session
            st.success(msg)
        else:
            st.error(msg)

st.markdown("---")

uploaded_csv = st.file_uploader("Upload CSV (id, reportname, account.name, date)")

if uploaded_csv and "session" in st.session_state:
    try:
        df = pd.read_csv(uploaded_csv, dtype=str)
    except Exception as e:
        st.error(f"❌ Failed to read CSV: {e}")
        st.stop()

    required_cols = {"id", "reportname", "account.name", "date"}
    if not required_cols.issubset(df.columns):
        st.error(f"CSV must contain columns: {required_cols}")
        st.stop()

    st.write("Loaded CSV:")
    st.dataframe(df)

    report_base_url = urljoin(base_url, "/patrol/default/viewreportprintable/idreport/")

    session = st.session_state.session

    # ZIP file buffer
    zip_buffer = io.BytesIO()
    zf = zipfile.ZipFile(zip_buffer, "w")

    st.markdown("### Downloading PDFs...")
    for idx, row in df.iterrows():
        rid = row["id"]
        filename = (
            f"{safe_filename(row['reportname'])}_"
            f"{safe_filename(row['account.name'])}_"
            f"{safe_filename(row['date'])}_({rid}).pdf"
        )

        pdf_url = f"{report_base_url}{rid}"
        try:
            r = session.get(pdf_url, timeout=20)
        except Exception as e:
            st.error(f"❌ Failed {rid}: {e}")
            continue

        if r.status_code == 200 and r.content.startswith(b"%PDF"):
            zf.writestr(filename, r.content)
            st.success(f"Saved: {filename}")
            st.download_button(
                label=f"Download {filename}",
                data=r.content,
                file_name=filename,
                mime="application/pdf"
            )
        else:
            st.error(f"❌ Failed {rid}, status: {r.status_code}")

    zf.close()
    st.markdown("### 📦 Download all PDFs as ZIP")
    st.download_button(
        label="Download ZIP",
        data=zip_buffer.getvalue(),
        file_name="all_reports.zip",
        mime="application/zip"
    )
elif uploaded_csv and "session" not in st.session_state:
    st.error("Please login first")
