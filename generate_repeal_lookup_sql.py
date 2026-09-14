"""
generate_repeal_lookup_sql.py
==============================
Reads flags_report CSV, takes the pmk_IDs still needing an end date
(STATUS_INACTIVE_NO_END_DATE), and writes a .sql file with two exploratory
queries against the Diwan DB: the base law rows, and any linked amendment
records (LegislationType=2) from UD_leg_Legislative_Amendments.

We don't yet know what UD_leg_Legislative_Amendments' columns actually are
(only pmk_ID and LegislationType, from the examples given) or what
Replaced_For actually holds there, so this pulls SELECT * rather than
guessing column names - safer than a wrong assumption breaking the query
or silently pulling the wrong field.

Usage: py -3.11 generate_repeal_lookup_sql.py
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
import config

TARGET_FLAG = "STATUS_INACTIVE_NO_END_DATE"


def main() -> int:
    csv_path = Path(config.FLAGS_REPORT_CSV)
    if not csv_path.is_absolute():
        csv_path = config.PROJECT_ROOT / csv_path
    if not csv_path.exists():
        print(f"الملف غير موجود: {csv_path}")
        return 1

    df = pd.read_csv(csv_path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    ids = df.loc[df["flag_type"] == TARGET_FLAG, "pmk_ID"].tolist()
    if not ids:
        print(f"لا يوجد صفوف بـ flag_type={TARGET_FLAG}")
        return 1

    id_list = ", ".join(ids)
    sql = f"""-- تحقق من قاعدة الديوان: {len(ids)} قانون ناقص تاريخ الانتهاء
-- (1) القوانين الأساسية نفسها
SELECT *
FROM UD_leg_Laws
WHERE pmk_ID IN ({id_list});

-- (2) أي سجلات تعديل/إلغاء مرتبطة فيهم (فحص أول، قبل أي منطق تلقائي)
SELECT *
FROM UD_leg_Legislative_Amendments
WHERE LegislationType = 2
  AND pmk_ID IN ({id_list});
"""
    out_path = config.PROJECT_ROOT / "outputs"
    out_path.mkdir(exist_ok=True)
    out_file = out_path / "repeal_lookup.sql"
    out_file.write_text(sql, encoding="utf-8")
    print(f"كتبت {len(ids)} pmk_ID بالاستعلام -> {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
