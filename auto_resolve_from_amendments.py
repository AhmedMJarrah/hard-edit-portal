"""
auto_resolve_from_amendments.py
================================
For the 411 "غير ساري بدون تاريخ انتهاء" rows: joins on pmk_ID (exact FK,
no ambiguity) against the Diwan UD_leg_Legislative_Amendments export
(LegislationType=2) and takes Status_Date as the end_date wherever a
matching amendment record exists.

Why not also use cleaned_v03_merged_updated.xlsx: matching it needs
Law_Number+Year, but ~10% of that file's (number, year) pairs are shared
by 2-6 different laws (confirmed on this data - up to 6 rows collide on
the same number+year), and checking name consistency showed ~45% of the
naive joins were wrong-law matches. Our own project convention already
says the real identity key is number+year+NAME - so this file needs a
proper name-matched pass to be trustworthy, which is future work, not
folded in here to avoid planting wrong dates.

Usage: py -3.11 auto_resolve_from_amendments.py --amendments data\\q2.csv
Outputs (in outputs\\): auto_resolved.csv, still_needs_volunteer.csv
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
import pandas as pd
import config

TARGET_FLAG = "STATUS_INACTIVE_NO_END_DATE"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--amendments", required=True, help="path to the UD_leg_Legislative_Amendments export (q2.csv)")
    args = ap.parse_args()

    flags_path = Path(config.FLAGS_REPORT_CSV)
    if not flags_path.is_absolute():
        flags_path = config.PROJECT_ROOT / flags_path
    flags = pd.read_csv(flags_path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    todo = flags[flags["flag_type"] == TARGET_FLAG].copy()

    amend = pd.read_csv(args.amendments, dtype=str, keep_default_na=False)
    amend = amend[["pmk_ID", "Status_Date"]].drop_duplicates("pmk_ID")
    # SQL Server NULLs sometimes export as the literal text "NULL", not an
    # empty cell - treat that the same as missing (confirmed 37 such rows).
    amend["Status_Date"] = amend["Status_Date"].where(amend["Status_Date"].str.upper() != "NULL", "")

    merged = todo.merge(amend, on="pmk_ID", how="left")
    merged["Status_Date"] = merged["Status_Date"].fillna("")
    resolved_mask = merged["Status_Date"].str.strip() != ""

    resolved = merged[resolved_mask].copy()
    resolved["end_date"] = resolved["Status_Date"]
    resolved["source"] = "UD_leg_Legislative_Amendments.Status_Date"

    remaining = merged[~resolved_mask].drop(columns=["Status_Date"])

    out_dir = config.PROJECT_ROOT / "outputs"
    out_dir.mkdir(exist_ok=True)
    resolved.to_csv(out_dir / "auto_resolved.csv", index=False, encoding="utf-8-sig")
    remaining.to_csv(out_dir / "still_needs_volunteer.csv", index=False, encoding="utf-8-sig")

    print(f"إجمالي: {len(todo)} | تعبأ تلقائياً: {len(resolved)} | باقي للمتطوعين: {len(remaining)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
