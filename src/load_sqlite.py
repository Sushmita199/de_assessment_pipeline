import argparse
import os
import sqlite3
from datetime import datetime

from openpyxl import load_workbook

from fields import TEMPLATE_COLUMNS

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_FILE = os.path.join(PROJECT_DIR, "sql", "schema.sql")
DEFAULT_DB = os.path.join(PROJECT_DIR, "output", "purchase_orders.db")

DB_COLUMNS = [field for _, field in TEMPLATE_COLUMNS] + ["validation_flags", "loaded_at"]

UPSERT_SQL = f"""
    INSERT INTO po_line_items ({", ".join(DB_COLUMNS)})
    VALUES ({", ".join("?" for _ in DB_COLUMNS)})
    ON CONFLICT(po_number, sku) DO UPDATE SET
    {", ".join(f"{col} = excluded.{col}" for col in DB_COLUMNS if col not in ("po_number", "sku"))}
"""


def read_excel_rows(xlsx_path):
    wb = load_workbook(xlsx_path, read_only=True)

    flags_by_sku = {}
    for _, _, sku, flag, _, _ in wb["Validation Flags"].iter_rows(min_row=2, values_only=True):
        flags_by_sku.setdefault(sku, []).append(flag)

    header_to_field = dict(TEMPLATE_COLUMNS)
    sheet = wb.worksheets[0]
    all_rows = list(sheet.iter_rows(values_only=True))
    headers = all_rows[0]

    rows = []
    for values in all_rows[1:]:
        row = {header_to_field[h]: v for h, v in zip(headers, values)}
        row["validation_flags"] = "; ".join(flags_by_sku.get(row["sku"], [])) or None
        rows.append(row)
    wb.close()
    return rows


def load_excel_to_sqlite(xlsx_path, db_path=DEFAULT_DB):
    rows = read_excel_rows(xlsx_path)
    loaded_at = datetime.now().isoformat(timespec="seconds")

    conn = sqlite3.connect(db_path)
    try:
        with open(SCHEMA_FILE) as f:
            conn.executescript(f.read())

        before = conn.execute("SELECT COUNT(*) FROM po_line_items").fetchone()[0]

        with conn:
            for row in rows:
                row["loaded_at"] = loaded_at
                conn.execute(UPSERT_SQL, [row.get(col) for col in DB_COLUMNS])

        after = conn.execute("SELECT COUNT(*) FROM po_line_items").fetchone()[0]
    finally:
        conn.close()

    inserted = after - before
    return {"rows_in_file": len(rows), "inserted": inserted,
            "updated": len(rows) - inserted, "table_rows_total": after}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load PO output Excel files into SQLite")
    parser.add_argument("xlsx_files", nargs="+")
    parser.add_argument("--db", default=DEFAULT_DB)
    args = parser.parse_args()

    for path in args.xlsx_files:
        stats = load_excel_to_sqlite(path, args.db)
        print(f"{os.path.basename(path)}: {stats}")
