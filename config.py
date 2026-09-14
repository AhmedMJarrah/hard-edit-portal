"""
config.py
=========
Central configuration for the end-date volunteer portal (project hard_edit).

Reads settings from, in order of preference:
  1. Streamlit secrets (st.secrets) - used on Streamlit Community Cloud
  2. Environment variables / .env (python-dotenv) - used for local runs

Nothing is hardcoded here: no sheet ID, no password, no file paths.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent


def _secrets_file_exists() -> bool:
    """Whether a secrets.toml is actually present anywhere Streamlit would
    look. Checked before ever touching st.secrets, for two reasons:
    (1) accessing st.secrets with no secrets.toml prints a "No secrets
    files found" warning as a side effect on every single lookup, and
    (2) on Streamlit Cloud, secrets ARE materialized to one of these
    paths at deploy time, so this check is also correct there - not
    just a local-only workaround.
    """
    candidates = [
        Path.home() / ".streamlit" / "secrets.toml",
        PROJECT_ROOT / ".streamlit" / "secrets.toml",
    ]
    return any(p.exists() for p in candidates)


_SECRETS_AVAILABLE = _secrets_file_exists()


def get_setting(key: str, default: str | None = None) -> str | None:
    """Look up a setting from Streamlit secrets first, then the environment.

    Only touches Streamlit at all if (a) some other module has already
    imported it - i.e. we're actually inside portal_app.py running under
    `streamlit run`, not a plain CLI script like seed_sheet.py - and
    (b) a secrets.toml actually exists (see _secrets_file_exists).
    Both guards exist to avoid st.secrets' own side effects (a printed
    warning with no file, and needing to run after st.set_page_config()
    - see portal_app.py's import order) when there's nothing to read.
    """
    if "streamlit" in sys.modules and _SECRETS_AVAILABLE:
        import streamlit as st
        try:
            if key in st.secrets:
                return st.secrets[key]
        except Exception:
            pass
    return os.getenv(key, default)


def get_gcp_service_account_info() -> dict | None:
    """Return the service-account credentials as a dict, from Streamlit
    secrets (deployed) if present, otherwise None (caller should fall back
    to a local JSON file). See get_setting() for why the import is guarded."""
    if "streamlit" in sys.modules and _SECRETS_AVAILABLE:
        import streamlit as st
        try:
            if "gcp_service_account" in st.secrets:
                return dict(st.secrets["gcp_service_account"])
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# Named settings used across the project
# ---------------------------------------------------------------------------

GOOGLE_SHEET_ID = get_setting("GOOGLE_SHEET_ID")
SHEET_WORKSHEET_NAME = get_setting("SHEET_WORKSHEET_NAME", "end_dates")
GOOGLE_SERVICE_ACCOUNT_FILE = get_setting(
    "GOOGLE_SERVICE_ACCOUNT_FILE", str(PROJECT_ROOT / "secrets" / "service_account.json")
)
FLAGS_REPORT_CSV = get_setting("FLAGS_REPORT_CSV")

_usernames_raw = get_setting("VOLUNTEER_USERNAMES", "v1,v2,v3,v4,v5")
VOLUNTEER_USERNAMES = [u.strip() for u in _usernames_raw.split(",") if u.strip()]
VOLUNTEER_PASSWORD = get_setting("VOLUNTEER_PASSWORD", "12345")

SHEET_COLUMNS = [
    "pmk_ID",
    "Law_Name",
    "Law_Number",
    "Year",
    "Status_display",
    "assigned_to",
    "end_date",
    "no_source_found",
    "filled_by",
    "filled_at",
    "done",
]
