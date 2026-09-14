"""
merge_resolved.py
==================
Merges outputs\\auto_resolved.csv's end_date into the master laws CSV
(End_Date_final column), matched by pmk_ID. Before writing, checks
end_date > Active_Date_final (the law's start date) for each row -
a row failing this sanity check is reported and NOT merged, so a bad
date can't silently corrupt the master file.

Usage:
    py -3.11 merge_resolved.py --master data\\laws_with_rebuilt_chains_20260908_reviewed.csv
Writes: outputs\\laws_with_rebuilt_chains_merged.csv (updated master)
        outputs\\merge_failed_date_check.csv (any rows that failed the check, for review)
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
import pandas as pd
import config


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", required=True, help="path to the master laws CSV to update")
    args = ap.parse_args()

    out_dir = config.PROJECT_ROOT / "outputs"
    resolved = pd.read_csv(out_dir / "auto_resolved.csv", dtype=str, keep_default_na=False)
    remaining = pd.read_csv(out_dir / "still_needs_volunteer.csv", dtype=str, keep_default_na=False)
    master = pd.read_csv(args.master, encoding="utf-8-sig", dtype=str, keep_default_na=False)

    check = resolved.merge(
        master[["pmk_ID", "Magazine_Date"]], on="pmk_ID", how="left"
    )
    # Active_Date_final is empty for this entire population (it depends on
    # an editor-merge step these rows never went through) - Magazine_Date
    # (the law's own gazette publication date) is used as the start-date
    # reference instead; it's not perfect (a law can take effect after
    # publication) but it's what's actually populated here.
    start = pd.to_datetime(check["Magazine_Date"], errors="coerce")
    end = pd.to_datetime(check["end_date"], errors="coerce")
    no_start = start.isna()
    ok = (end > start) & ~no_start

    failed = check[~ok & ~no_start]
    unverified = check[no_start]
    passed = check[ok]

    if not failed.empty:
        failed.to_csv(out_dir / "merge_failed_date_check.csv", index=False, encoding="utf-8-sig")
    if not unverified.empty:
        unverified.to_csv(out_dir / "merge_unverified_no_start_date.csv", index=False, encoding="utf-8-sig")

    master = master.set_index("pmk_ID")
    to_write = pd.concat([passed, unverified])  # merge both; only `failed` is held back
    master.loc[to_write["pmk_ID"], "End_Date_final"] = to_write.set_index("pmk_ID")["end_date"]

    if not failed.empty:
        # Ahmed's call: the mismatch isn't just end_date vs Magazine_Date -
        # Magazine_Date itself looks inconsistent with the law's own Year
        # for these, so neither is trustworthy. Clear both in the master
        # file and route these rows to volunteers instead of guessing.
        master.loc[failed["pmk_ID"], ["End_Date_final", "Magazine_Date"]] = ""
        remaining = pd.concat([remaining, failed[remaining.columns]], ignore_index=True)
        remaining.to_csv(out_dir / "still_needs_volunteer.csv", index=False, encoding="utf-8-sig")

    master = master.reset_index()
    master.to_csv(out_dir / "laws_with_rebuilt_chains_merged.csv", index=False, encoding="utf-8-sig")

    print(f"دُمج: {len(to_write)} (منها {len(unverified)} بدون تاريخ نشر لمقارنته - دُمجت بدون تحقق)")
    print(f"فشل الفحص: {len(failed)} - انمسح End_Date_final وMagazine_Date لهن، وانضافوا لملف المتطوعين")
    return 0


if __name__ == "__main__":
    sys.exit(main())
