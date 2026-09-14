"""
sheets_client.py
=================
Thin wrapper around gspread for the end-date volunteer portal.

Auth: uses google.oauth2.service_account.Credentials + gspread.authorize(),
the current (non-deprecated) gspread authentication pattern. Prefers
Streamlit secrets (deployed) and falls back to a local service-account
JSON file (local development) so the same code works in both places.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

import config

logger = logging.getLogger("sheets_client")

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _build_client() -> gspread.Client:
    service_account_info = config.get_gcp_service_account_info()
    if service_account_info:
        creds = Credentials.from_service_account_info(service_account_info, scopes=_SCOPES)
    else:
        creds = Credentials.from_service_account_file(
            config.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=_SCOPES
        )
    return gspread.authorize(creds)


def get_worksheet() -> gspread.Worksheet:
    """Open the configured spreadsheet/worksheet. Raises a clear error if
    the sheet ID is missing or the sheet/tab doesn't exist yet."""
    if not config.GOOGLE_SHEET_ID:
        raise RuntimeError("GOOGLE_SHEET_ID غير معرّف (تحقق من .env أو Streamlit secrets)")

    client = _build_client()
    spreadsheet = client.open_by_key(config.GOOGLE_SHEET_ID)

    try:
        return spreadsheet.worksheet(config.SHEET_WORKSHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        raise RuntimeError(
            f"التبويب '{config.SHEET_WORKSHEET_NAME}' غير موجود بالشيت. "
            "شغّل seed_sheet.py أولاً لإنشائه وتعبئته."
        )


def get_all_records_as_df(worksheet: gspread.Worksheet) -> pd.DataFrame:
    """Fetch the whole sheet as a DataFrame, all columns as strings so
    blank cells stay '' rather than becoming NaN."""
    records = worksheet.get_all_records()
    df = pd.DataFrame(records)
    if df.empty:
        return pd.DataFrame(columns=config.SHEET_COLUMNS)
    return df.astype(str).replace("nan", "")


def _find_row_number(worksheet: gspread.Worksheet, pmk_id: str) -> int:
    """Return the 1-based sheet row number for a given pmk_ID, or raise if not found."""
    cell = worksheet.find(str(pmk_id), in_column=config.SHEET_COLUMNS.index("pmk_ID") + 1)
    if cell is None:
        raise ValueError(f"pmk_ID={pmk_id} غير موجود بالشيت")
    return cell.row


def update_row(
    worksheet: gspread.Worksheet,
    pmk_id: str,
    end_date: str,
    no_source_found: bool,
    filled_by: str,
) -> None:
    """Write a volunteer's answer back to their assigned row only.

    Only the answer columns are touched (end_date, no_source_found,
    filled_by, filled_at, done) - the identifying columns (pmk_ID,
    Law_Name, ...) and assigned_to are left untouched.
    """
    row = _find_row_number(worksheet, pmk_id)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    updates = {
        "end_date": end_date if not no_source_found else "",
        "no_source_found": "TRUE" if no_source_found else "FALSE",
        "filled_by": filled_by,
        "filled_at": now_iso,
        "done": "TRUE",
    }

    cell_list = []
    for column_name, value in updates.items():
        col = config.SHEET_COLUMNS.index(column_name) + 1
        cell_list.append(gspread.Cell(row=row, col=col, value=value))

    worksheet.update_cells(cell_list)
    logger.info("Row for pmk_ID=%s updated by %s", pmk_id, filled_by)
