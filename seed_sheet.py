"""
seed_sheet.py
=============
One-time setup script: reads the flags_report CSV, keeps only the rows that
need volunteer end-date lookup (flag_type == STATUS_INACTIVE_NO_END_DATE),
splits them evenly across the volunteers, and writes the initial sheet.

Run this ONCE after the Google Sheet + service account are set up. Re-running
without --force will refuse to overwrite an already-seeded sheet, so nobody's
in-progress work gets wiped by accident.

Usage (Windows CMD)
--------------------
py -3.11 seed_sheet.py
py -3.11 seed_sheet.py --input data\\flags_report_20260909_140449.csv --force
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import gspread
import numpy as np
import pandas as pd

import config
import sheets_client

TARGET_FLAG_TYPE = "STATUS_INACTIVE_NO_END_DATE"


def setup_logging() -> logging.Logger:
    logs_dir = config.PROJECT_ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"seed_sheet_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    logger = logging.getLogger("seed_sheet")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    logger.info("Log file: %s", log_path)
    return logger


def load_and_filter(csv_path: Path, logger: logging.Logger) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(f"الملف غير موجود: {csv_path}")

    logger.info("Reading input file: %s", csv_path.resolve())
    df = pd.read_csv(csv_path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    required = {"pmk_ID", "Law_Name", "Law_Number", "Year", "Status_final", "flag_type"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"أعمدة ناقصة بملف الإدخال: {missing}\n"
            f"  الملف المقروء فعلياً: {csv_path.resolve()}\n"
            f"  أعمدة هذا الملف ({len(df.columns)}): {df.columns.tolist()}\n"
            "  تحقق إنك مشوّر FLAGS_REPORT_CSV بملف .env على ملف flags_report_*.csv "
            "(مخرجات audit_status_and_chains.py) وليس على ملف laws_with_rebuilt_chains "
            "الأصلي - هذا الأخير ما فيه عمود flag_type أصلاً."
        )

    subset = df[df["flag_type"] == TARGET_FLAG_TYPE].copy()
    logger.info("Total rows in input: %d | rows with flag_type=%s: %d",
                len(df), TARGET_FLAG_TYPE, len(subset))

    if subset.empty:
        raise ValueError(f"لا يوجد أي صف بـ flag_type={TARGET_FLAG_TYPE} بالملف المُدخل")

    subset = subset.rename(columns={"Status_final": "Status_display"})
    return subset[["pmk_ID", "Law_Name", "Law_Number", "Year", "Status_display"]]


def assign_to_volunteers(
    df: pd.DataFrame, usernames: list[str], logger: logging.Logger, seed: int = 42
) -> pd.DataFrame:
    """Shuffle rows (fixed seed, so the split is reproducible if this
    script is ever re-run) and split into len(usernames) non-overlapping
    chunks. Shuffling avoids handing one volunteer a lopsided share of,
    say, the oldest/hardest-to-research laws just because of row order
    in the source CSV.

    Splits an integer index array (not the DataFrame itself) via
    np.array_split, since splitting a DataFrame directly can hand back
    plain ndarrays instead of DataFrames for uneven split sizes.
    """
    df = df.sample(frac=1, random_state=seed).reset_index(drop=True)
    df["assigned_to"] = ""
    index_chunks = np.array_split(np.arange(len(df)), len(usernames))
    for username, idx in zip(usernames, index_chunks):
        df.loc[idx, "assigned_to"] = username
        logger.info("Assigned %d rows to %s", len(idx), username)
    return df


def build_sheet_rows(df: pd.DataFrame) -> list[list[str]]:
    df = df.copy()
    for col in ["end_date", "no_source_found", "filled_by", "filled_at", "done"]:
        df[col] = ""
    df["no_source_found"] = "FALSE"
    df["done"] = "FALSE"
    df = df[config.SHEET_COLUMNS]
    return [config.SHEET_COLUMNS] + df.values.tolist()


def write_to_sheet(rows: list[list[str]], force: bool, logger: logging.Logger) -> None:
    if not config.GOOGLE_SHEET_ID:
        raise RuntimeError("GOOGLE_SHEET_ID غير معرّف بملف .env")

    client = sheets_client._build_client()
    spreadsheet = client.open_by_key(config.GOOGLE_SHEET_ID)

    try:
        worksheet = spreadsheet.worksheet(config.SHEET_WORKSHEET_NAME)
        existing = worksheet.get_all_values()
        if len(existing) > 1 and not force:
            raise RuntimeError(
                f"التبويب '{config.SHEET_WORKSHEET_NAME}' فيه بيانات مسبقاً "
                f"({len(existing) - 1} صف). استخدم --force إذا متأكد إنك بدك تكتب فوقها "
                "(راح يمسح أي عمل متطوعين موجود)."
            )
        worksheet.clear()
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=config.SHEET_WORKSHEET_NAME, rows=len(rows) + 10, cols=len(config.SHEET_COLUMNS)
        )

    # NOTE: gspread >=6.0 changed update()'s argument order to
    # update(values, range_name) - values first. Passing them in the old
    # (range_name, values) order silently does the wrong thing, so this is
    # explicit here rather than relying on positional defaults.
    worksheet.update(values=rows, range_name="A1")
    logger.info("تمت كتابة %d صف بيانات (+ صف العناوين) إلى الشيت", len(rows) - 1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the volunteer Google Sheet from the flags report CSV.")
    parser.add_argument("--input", type=str, default=None, help="Override FLAGS_REPORT_CSV from .env")
    parser.add_argument("--force", action="store_true", help="Overwrite an already-seeded sheet")
    args = parser.parse_args()

    logger = setup_logging()

    input_str = args.input or config.FLAGS_REPORT_CSV
    if not input_str:
        logger.error("لازم تحدد مسار الملف عبر --input أو FLAGS_REPORT_CSV بملف .env")
        return 1
    csv_path = Path(input_str)
    if not csv_path.is_absolute():
        csv_path = config.PROJECT_ROOT / csv_path

    try:
        df = load_and_filter(csv_path, logger)
        df = assign_to_volunteers(df, config.VOLUNTEER_USERNAMES, logger)
        rows = build_sheet_rows(df)
        write_to_sheet(rows, args.force, logger)
    except Exception as exc:  # noqa: BLE001 - top-level script, log and exit cleanly
        logger.error("فشل التنفيذ: %s", exc)
        return 1

    logger.info("تم بنجاح.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
