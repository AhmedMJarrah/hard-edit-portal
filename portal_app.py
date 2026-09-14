"""
portal_app.py
=============
Volunteer portal (Streamlit) for filling the missing End_Date on the 411
"غير ساري بدون تاريخ انتهاء" laws flagged by audit_status_and_chains.py.

Run (Windows CMD):
    py -3.11 -m streamlit run portal_app.py
"""

from __future__ import annotations

from datetime import date

import streamlit as st

# set_page_config() must be the very first Streamlit command executed -
# Streamlit raises StreamlitAPIException otherwise. `import config` below
# can itself touch st.secrets (see config.get_setting), which counts as
# a Streamlit command, so config/sheets_client are deliberately imported
# AFTER set_page_config() rather than grouped with the other imports.
st.set_page_config(page_title="بوابة تدقيق تواريخ الانتهاء", page_icon="📜", layout="wide")

import pandas as pd

import config
import sheets_client

# ---------------------------------------------------------------------------
# Styling: force light theme + RTL + a calm, comfortable palette
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
    html, body, [class*="css"] { direction: rtl; text-align: right; font-family: "Segoe UI", Tahoma, sans-serif; }
    .stApp { background-color: #F3F6F9; }

    /* Hide the default Streamlit chrome (deploy button, hamburger menu, footer)
       for a cleaner, product-like feel rather than an obvious dev tool. */
    [data-testid="stAppDeployButton"], [data-testid="stMainMenu"], footer { display: none; }
    /* Streamlit auto-adds a hover "copy anchor link" icon to markdown headings
       (h1-h6, including our own <h3> inside .law-card) - clutter inside a
       styled card, so it's hidden. */
    [data-testid="stHeaderActionElements"] { display: none; }

    [data-testid="stMainBlockContainer"] { padding-top: 2.2rem; max-width: 980px; }

    /* App header */
    .app-title { font-size: 1.9rem; font-weight: 800; color: #1B3A4B; margin-bottom: 0; }
    .app-subtitle { color: #6B7A87; font-size: 0.98rem; margin-top: 2px; margin-bottom: 1.4rem; }

    /* Login card */
    [data-testid="stForm"] {
        background-color: #FFFFFF;
        border: 1px solid #E3E8EF;
        border-radius: 16px;
        padding: 2rem 2.2rem 1.4rem;
        box-shadow: 0 4px 18px rgba(27,58,75,0.08);
    }

    /* Stat cards row */
    .stat-box {
        background-color: #FFFFFF;
        border: 1px solid #E3E8EF;
        border-radius: 12px;
        padding: 14px 10px;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .stat-box .num { font-size: 1.6rem; font-weight: 800; }
    .stat-box .lbl { color: #6B7A87; font-size: 0.82rem; margin-top: 2px; }
    .stat-done .num { color: #1E8E5A; }
    .stat-remaining .num { color: #B4690E; }
    .stat-total .num { color: #2F6690; }

    /* Law card */
    .law-card {
        background-color: #FFFFFF;
        border: 1px solid #E3E8EF;
        border-right: 6px solid #2F6690;
        border-radius: 12px;
        padding: 22px 26px;
        margin: 18px 0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    .law-card h3 { margin-top: 0; margin-bottom: 14px; color: #1B3A4B; }
    .law-meta-row { color: #45525E; font-size: 0.95rem; margin: 6px 0; }
    .law-meta-row b { color: #1B3A4B; }
    .status-pill {
        display: inline-block; background-color: #FDEDEC; color: #C0392B;
        padding: 4px 14px; border-radius: 999px; font-size: 0.85rem; font-weight: 700;
        margin-top: 8px;
    }

    .section-label {
        font-weight: 700; color: #1B3A4B; margin: 4px 0 10px; font-size: 1.02rem;
    }

    /* Checkbox + date input: bigger, clearer labels and text than the
       Streamlit default, since this is the actual data-entry moment. */
    [data-testid="stCheckbox"] [data-testid="stMarkdownContainer"] p {
        font-size: 1.08rem !important;
        font-weight: 600 !important;
        color: #1B3A4B !important;
    }
    [data-testid="stCheckbox"] span[data-testid="stTickIcon"],
    [data-testid="stCheckbox"] div[class*="e1e6q2zh4"] {
        transform: scale(1.25);
        margin-left: 4px;
    }
    [data-testid="stDateInput"] label[data-testid="stWidgetLabel"] p {
        font-size: 1.08rem !important;
        font-weight: 600 !important;
        color: #1B3A4B !important;
    }
    [data-testid="stDateInputField"] {
        padding: 12px 14px !important;
        min-height: 3.2rem;
        background-color: #FFF9E6 !important;
        border: 3px solid #2F6690 !important;
        border-radius: 10px !important;
        box-shadow: 0 2px 6px rgba(47,102,144,0.25);
    }
    [data-testid="stDateInputField"]:focus-within {
        border-color: #B4690E !important;
        box-shadow: 0 0 0 3px rgba(180,105,14,0.25);
    }
    [data-testid="stDateInput"]::before {
        content: "👇 اضغط هنا واكتب التاريخ";
        display: block; color: #B4690E; font-weight: 700; font-size: 1rem; margin-bottom: 6px;
        text-align: center;
    }
    [data-testid="stDateInput"] label[data-testid="stWidgetLabel"] { text-align: center; display: block; }
    [data-testid="stDateInputField"] span[role="spinbutton"] {
        font-size: 1.15rem !important;
    }

    div.stButton > button {
        border-radius: 10px; padding: 0.5rem 1.4rem; font-weight: 700;
    }

    /* Sidebar branding */
    [data-testid="stSidebarUserContent"] { padding-top: 1.5rem; }
    .sidebar-welcome { color: #FFFFFF; font-size: 1.1rem; font-weight: 700; margin-bottom: 0.2rem; }
    .sidebar-caption { color: #B9CBD8; font-size: 0.85rem; margin-bottom: 1.2rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def render_login() -> None:
    left, mid, right = st.columns([1, 1.3, 1])
    with mid:
        st.markdown('<div style="text-align:center; font-size:3rem;">📜</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="app-title" style="text-align:center;">بوابة تدقيق تواريخ الانتهاء</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="app-subtitle" style="text-align:center;">'
            "سجّل دخولك للبدء بمراجعة القوانين المخصصة لك</div>",
            unsafe_allow_html=True,
        )
        with st.form("login_form"):
            username = st.selectbox("اسم المستخدم", config.VOLUNTEER_USERNAMES)
            password = st.text_input("كلمة المرور", type="password")
            submitted = st.form_submit_button("دخول 🔐", use_container_width=True, type="primary")
        if submitted:
            if password == config.VOLUNTEER_PASSWORD:
                st.session_state["username"] = username
                st.rerun()
            else:
                st.error("كلمة المرور غير صحيحة")


def render_logout_sidebar() -> None:
    with st.sidebar:
        st.markdown(
            f'<div class="sidebar-welcome">👋 أهلاً، {st.session_state["username"]}</div>'
            '<div class="sidebar-caption">بوابة تدقيق تواريخ الانتهاء</div>',
            unsafe_allow_html=True,
        )
        if st.button("🚪 تسجيل خروج", use_container_width=True):
            del st.session_state["username"]
            st.rerun()


# ---------------------------------------------------------------------------
# Data access (cached connection, fresh data each run so writes show up)
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def get_worksheet():
    return sheets_client.get_worksheet()


def load_my_rows(username: str) -> pd.DataFrame:
    worksheet = get_worksheet()
    df = sheets_client.get_all_records_as_df(worksheet)
    if df.empty:
        return df
    return df[df["assigned_to"] == username].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Main working screen
# ---------------------------------------------------------------------------

def render_progress(my_rows: pd.DataFrame) -> None:
    total = len(my_rows)
    done = int((my_rows["done"] == "TRUE").sum())
    remaining = total - done

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            f'<div class="stat-box stat-done"><div class="num">{done}</div>'
            '<div class="lbl">تم إنجازها</div></div>',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f'<div class="stat-box stat-remaining"><div class="num">{remaining}</div>'
            '<div class="lbl">متبقية</div></div>',
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f'<div class="stat-box stat-total"><div class="num">{total}</div>'
            '<div class="lbl">إجمالي المخصص لك</div></div>',
            unsafe_allow_html=True,
        )
    st.write("")
    st.progress(0 if total == 0 else done / total)


def render_picker(my_rows: pd.DataFrame) -> str:
    pending = my_rows[my_rows["done"] != "TRUE"]
    default_pmk = pending.iloc[0]["pmk_ID"] if not pending.empty else my_rows.iloc[0]["pmk_ID"]

    def label(pmk_id: str) -> str:
        row = my_rows[my_rows["pmk_ID"] == pmk_id].iloc[0]
        mark = "✅" if row["done"] == "TRUE" else "🕓"
        return f"{mark} {pmk_id} — {row['Law_Name'][:60]}"

    options = my_rows["pmk_ID"].tolist()
    default_index = options.index(default_pmk)
    st.markdown('<div class="section-label">📂 اختر القانون</div>', unsafe_allow_html=True)
    return st.selectbox("اختر القانون", options, index=default_index, format_func=label, label_visibility="collapsed")


def render_law_card(row: pd.Series) -> None:
    st.markdown(
        f"""
        <div class="law-card">
            <h3>{row['Law_Name']}</h3>
            <div class="law-meta-row">🔢 <b>رقم القانون:</b> {row['Law_Number']}</div>
            <div class="law-meta-row">📅 <b>السنة:</b> {row['Year']}</div>
            <div class="law-meta-row">🆔 <b>pmk_ID:</b> {row['pmk_ID']}</div>
            <span class="status-pill">⛔ {row['Status_display']}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_answer_form(row: pd.Series, username: str) -> None:
    already_done = row["done"] == "TRUE"
    if already_done:
        st.info(
            f"تمت تعبئة هذا القانون مسبقاً بواسطة {row['filled_by']} بتاريخ {row['filled_at']}. "
            "يمكنك تعديل الإجابة وإعادة الإرسال إذا لزم."
        )

    st.markdown('<div class="section-label">✏️ إدخال البيانات</div>', unsafe_allow_html=True)

    no_source_default = row["no_source_found"] == "TRUE"
    no_source = st.checkbox("لم أجد مصدراً يحدد تاريخ انتهاء هذا القانون", value=no_source_default)

    end_date_value: date | None = None
    if not no_source:
        prior_date = None
        if row["end_date"]:
            try:
                prior_date = pd.to_datetime(row["end_date"]).date()
            except (ValueError, TypeError):
                prior_date = None
        _, mid, _ = st.columns([1, 1.4, 1])
        with mid:
            end_date_value = st.date_input(
                "تاريخ انتهاء القانون",
                value=prior_date,
                min_value=date(1900, 1, 1),
                max_value=date.today(),
                format="YYYY-MM-DD",
            )

    st.write("")
    if st.button("💾 حفظ وإرسال", type="primary", use_container_width=True):
        if not no_source and end_date_value is None:
            st.error("لازم تحدد تاريخ الانتهاء، أو تعلّم أنك ما لقيت مصدر.")
            return
        sheets_client.update_row(
            get_worksheet(),
            pmk_id=row["pmk_ID"],
            end_date=end_date_value.isoformat() if end_date_value else "",
            no_source_found=no_source,
            filled_by=username,
        )
        st.success("تم الحفظ بنجاح ✅")
        st.rerun()


def render_main() -> None:
    username = st.session_state["username"]
    render_logout_sidebar()

    st.markdown('<div class="app-title">📜 بوابة تدقيق تواريخ الانتهاء</div>', unsafe_allow_html=True)
    st.markdown('<div class="app-subtitle">راجع القانون، وحدد تاريخ انتهائه أو علّم أنك ما لقيت مصدر</div>', unsafe_allow_html=True)

    my_rows = load_my_rows(username)
    if my_rows.empty:
        st.warning("لا توجد قوانين مخصصة لك حالياً.")
        return

    render_progress(my_rows)
    st.write("")
    selected_pmk = render_picker(my_rows)
    selected_row = my_rows[my_rows["pmk_ID"] == selected_pmk].iloc[0]

    render_law_card(selected_row)
    render_answer_form(selected_row, username)


def main() -> None:
    if "username" not in st.session_state:
        render_login()
    else:
        render_main()


if __name__ == "__main__":
    main()
