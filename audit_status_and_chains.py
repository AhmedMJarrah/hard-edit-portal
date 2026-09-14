"""
audit_status_and_chains.py
============================
Project: hard_edit
Purpose: Phase 1 data-quality audit for the JLexAI "rebuilt chains" laws
         dataset (laws_with_rebuilt_chains_*.csv).

Checks performed
-----------------
1. Status flags (based on the raw `Status` column, coded 1=ساري / 2=غير ساري):
   a. Status == '1' (ساري) AND End_Date_final is populated       -> STATUS_ACTIVE_WITH_END_DATE
   b. Status == '2' (غير ساري) AND End_Date_final is empty       -> STATUS_INACTIVE_NO_END_DATE
   c. Status is empty                                            -> STATUS_EMPTY
   d. Status (raw) contradicts Status_final (resolved text)      -> STATUS_RAW_FINAL_MISMATCH
      (kept separate because it is NOT covered by (a)/(b) when the raw
      column is the one used for the primary rule)

2. Chain integrity on chain_id_v2 / chain_position_v2:
   a. Multi-row chains whose positions are not a clean 0..N-1 sequence
      (gap, duplicate, or doesn't start at 0)                    -> CHAIN_SEQUENCE_BROKEN
   b. chain_position_v2 that cannot be parsed as an integer       -> CHAIN_INVALID_POSITION
   c. A row that carries a ModLeg (amendment marker) but sits
      alone in its own chain at position 0 (should be a member
      of its base law's chain, not a standalone chain)            -> CHAIN_ORPHANED_AMENDMENT

3. Referential integrity:
   a. fnk_leg_Laws10765 populated but the value does not match
      any pmk_ID in the dataset                                  -> FK_BROKEN_FNK_LEG_LAWS10765

Notes / things deliberately NOT validated here (documented so nobody
re-checks them and gets confused later):
   - FK_leg_Laws10765 is a GUID, not a pmk_ID reference -> not comparable.
   - fnk, fnk_rebuilt, fnk_chain_id, fnk_clean are legacy/intermediate
     columns from earlier pipeline generations with much higher
     non-match rates against pmk_ID; they are NOT validated as FKs here
     because it is not established what ID space they reference. Only
     fnk_leg_Laws10765 had a clean (>99%) match rate against pmk_ID,
     which is why it is the only one checked.

Output
------
- outputs/flags_report_<timestamp>.csv : every flagged row, one line per
  (row, flag_type) pair.
- logs/audit_<timestamp>.log           : full run log + summary counts.

Usage (Windows CMD)
--------------------
py -3.11 audit_status_and_chains.py

Configuration is read from .env (INPUT_CSV_PATH). Override at the
command line with --input if needed.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
import os

__version__ = "1.0.0"

# ---------------------------------------------------------------------------
# Paths / configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

# Columns the script depends on; if any are missing we fail fast with a
# clear error instead of crashing deep inside some function.
REQUIRED_COLUMNS = [
    "pmk_ID",
    "Law_Name",
    "Law_Number",
    "Year",
    "ModLeg",
    "Status",
    "Status_final",
    "End_Date_final",
    "chain_id_v2",
    "chain_position_v2",
    "fnk_leg_Laws10765",
]

STATUS_CODE_TO_TEXT = {"1": "ساري", "2": "غير ساري"}


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging(run_id: str) -> logging.Logger:
    """Configure a logger that writes to both console and a timestamped log file."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"audit_{run_id}.log"

    logger = logging.getLogger("audit")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    logger.info("Log file: %s", log_path)
    return logger


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_dataset(csv_path: Path, logger: logging.Logger) -> pd.DataFrame:
    """Load the CSV as strings, preserving empty strings (not NaN) so
    blank-detection logic ('' checks) behaves correctly."""
    if not csv_path.exists():
        raise FileNotFoundError(f"Input CSV not found: {csv_path}")

    df = pd.read_csv(csv_path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    logger.info("Loaded %d rows, %d columns from %s", len(df), len(df.columns), csv_path)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Required columns missing from input CSV: {missing}")

    if df["pmk_ID"].duplicated().any():
        dupes = df.loc[df["pmk_ID"].duplicated(), "pmk_ID"].tolist()
        logger.warning("Duplicate pmk_ID values found (should be unique): %s", dupes)

    return df


# ---------------------------------------------------------------------------
# Check 1: Status flags
# ---------------------------------------------------------------------------

def audit_status(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    """Return a long-format DataFrame of flagged rows for all Status-related checks."""
    flags = []

    status = df["Status"].str.strip()
    end_date = df["End_Date_final"].str.strip()
    status_final = df["Status_final"].str.strip()

    # (a) active (raw) with an end date populated
    mask_a = (status == "1") & (end_date != "")
    flags.append(_build_flag_rows(df, mask_a, "STATUS_ACTIVE_WITH_END_DATE",
                                   "Status(raw)=1 (ساري) لكن End_Date_final معبّى"))

    # (b) inactive (raw) with no end date
    mask_b = (status == "2") & (end_date == "")
    flags.append(_build_flag_rows(df, mask_b, "STATUS_INACTIVE_NO_END_DATE",
                                   "Status(raw)=2 (غير ساري) بدون End_Date_final"))

    # (c) empty raw status
    mask_c = status == ""
    flags.append(_build_flag_rows(df, mask_c, "STATUS_EMPTY",
                                   "عمود Status الخام فارغ"))

    # (d) raw Status contradicts Status_final
    expected_final = status.map(STATUS_CODE_TO_TEXT)
    mask_d = (status.isin(["1", "2"])) & (status_final != "") & (status_final != expected_final)
    flags.append(_build_flag_rows(df, mask_d, "STATUS_RAW_FINAL_MISMATCH",
                                   "Status(الخام) لا يطابق Status_final"))

    result = pd.concat(flags, ignore_index=True) if flags else pd.DataFrame()
    logger.info("Status checks -> a:%d  b:%d  c:%d  d:%d",
                mask_a.sum(), mask_b.sum(), mask_c.sum(), mask_d.sum())
    return result


# ---------------------------------------------------------------------------
# Check 2: Chain integrity (chain_id_v2 / chain_position_v2)
# ---------------------------------------------------------------------------

def _parse_int(value: str) -> int | None:
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def audit_chains(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    """Validate chain_id_v2 / chain_position_v2 sequencing and detect
    amendment rows that failed to link to their base law's chain."""
    flags = []

    pos_parsed = df["chain_position_v2"].apply(_parse_int)
    invalid_pos_mask = pos_parsed.isna() & (df["chain_position_v2"].str.strip() != "")
    flags.append(_build_flag_rows(df, invalid_pos_mask, "CHAIN_INVALID_POSITION",
                                   "chain_position_v2 غير قابل للتحويل لرقم صحيح"))

    broken_chain_pmk_ids: set[str] = set()
    orphan_amendment_pmk_ids: set[str] = set()

    work = df.copy()
    work["_pos"] = pos_parsed

    for chain_id, group in work.groupby("chain_id_v2"):
        positions = sorted(p for p in group["_pos"] if p is not None)

        if len(group) == 1:
            # Single-row chain: only suspicious if it's flagged as an
            # amendment (ModLeg populated) yet has no base-law siblings.
            row = group.iloc[0]
            if row["ModLeg"].strip() != "":
                orphan_amendment_pmk_ids.add(row["pmk_ID"])
            continue

        expected = list(range(0, len(group)))
        if positions != expected:
            broken_chain_pmk_ids.update(group["pmk_ID"].tolist())

    broken_mask = df["pmk_ID"].isin(broken_chain_pmk_ids)
    flags.append(_build_flag_rows(df, broken_mask, "CHAIN_SEQUENCE_BROKEN",
                                   "chain_id_v2: الترتيب غير متسلسل (فجوة/تكرار/لا يبدأ من 0)"))

    orphan_mask = df["pmk_ID"].isin(orphan_amendment_pmk_ids)
    flags.append(_build_flag_rows(df, orphan_mask, "CHAIN_ORPHANED_AMENDMENT",
                                   "صف تعديل (ModLeg معبّى) لكنه وحيد بسلسلته الخاصة"))

    result = pd.concat(flags, ignore_index=True) if flags else pd.DataFrame()
    logger.info("Chain checks -> invalid_position:%d  broken_sequence:%d  orphaned_amendment:%d",
                invalid_pos_mask.sum(), len(broken_chain_pmk_ids), len(orphan_amendment_pmk_ids))
    return result


# ---------------------------------------------------------------------------
# Check 3: Referential integrity
# ---------------------------------------------------------------------------

def audit_fk_references(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    """Check fnk_leg_Laws10765 values resolve to an existing pmk_ID."""
    pmk_set = set(df["pmk_ID"])
    fnk = df["fnk_leg_Laws10765"].str.strip()

    mask = (fnk != "") & (~fnk.isin(pmk_set))
    result = _build_flag_rows(df, mask, "FK_BROKEN_FNK_LEG_LAWS10765",
                               "fnk_leg_Laws10765 يشير إلى pmk_ID غير موجود بالملف")
    logger.info("FK checks -> broken_fnk_leg_laws10765:%d", mask.sum())
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_flag_rows(df: pd.DataFrame, mask: pd.Series, flag_type: str, details: str) -> pd.DataFrame:
    if not mask.any():
        return pd.DataFrame(columns=[
            "pmk_ID", "Law_Name", "Law_Number", "Year", "ModLeg", "Status",
            "Status_final", "End_Date_final", "chain_id_v2", "chain_position_v2",
            "flag_type", "details",
        ])
    subset = df.loc[mask, [
        "pmk_ID", "Law_Name", "Law_Number", "Year", "ModLeg", "Status",
        "Status_final", "End_Date_final", "chain_id_v2", "chain_position_v2",
    ]].copy()
    subset["flag_type"] = flag_type
    subset["details"] = details
    return subset


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Phase 1 audit: Status flags + chain_v2 integrity + FK checks.")
    parser.add_argument("--input", type=str, default=None,
                         help="Override INPUT_CSV_PATH from .env")
    args = parser.parse_args()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger = setup_logging(run_id)
    logger.info("audit_status_and_chains.py v%s starting", __version__)

    input_path_str = args.input or os.getenv("INPUT_CSV_PATH")
    if not input_path_str:
        logger.error("No input path given. Set INPUT_CSV_PATH in .env or pass --input.")
        return 1
    csv_path = (PROJECT_ROOT / input_path_str).resolve() if not Path(input_path_str).is_absolute() else Path(input_path_str)

    try:
        df = load_dataset(csv_path, logger)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Failed to load dataset: %s", exc)
        return 1

    status_flags = audit_status(df, logger)
    chain_flags = audit_chains(df, logger)
    fk_flags = audit_fk_references(df, logger)

    all_flags = pd.concat([status_flags, chain_flags, fk_flags], ignore_index=True)

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUTS_DIR / f"flags_report_{run_id}.csv"
    all_flags.to_csv(output_path, index=False, encoding="utf-8-sig")

    logger.info("Total flagged rows (row x flag_type pairs): %d", len(all_flags))
    logger.info("Unique rows with at least one flag: %d", all_flags["pmk_ID"].nunique() if not all_flags.empty else 0)
    logger.info("Report written to: %s", output_path)

    summary = all_flags["flag_type"].value_counts() if not all_flags.empty else "no flags"
    logger.info("Summary by flag_type:\n%s", summary)

    return 0


if __name__ == "__main__":
    sys.exit(main())
