import argparse
import glob
import logging
import os
import sys
from datetime import datetime

from parse_po import parse_po
from validate import validate_po
from write_excel import write_excel
from load_sqlite import load_excel_to_sqlite, DEFAULT_DB

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.join(PROJECT_DIR, "input")
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
LOG_DIR = os.path.join(PROJECT_DIR, "logs")
TEMPLATE = os.path.join(INPUT_DIR, "output_template_blank.xlsx")

log = logging.getLogger("po_pipeline")


def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = os.path.join(LOG_DIR, f"pipeline_{datetime.now():%Y%m%d_%H%M%S}.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_file, encoding="utf-8")],
    )
    return log_file


def process_file(path, load_to_db, db_path):
    name = os.path.basename(path)
    log.info("---- %s ----", name)

    po = parse_po(path)
    log.info("%s: layout=%s, PO#=%s, line items=%d",
             name, po["layout"], po["header"]["po_number"], len(po["items"]))
    for problem in po["problems"]:
        log.warning("%s: PARSE PROBLEM %s", name, problem)

    validate_po(po)
    flagged = [item for item in po["items"] if item["flags"]]
    for item in flagged:
        for f in item["flags"]:
            log.warning("%s: SKU %s %s - %s -> %s",
                        name, item["sku"], f["flag"], f["detail"], f["decision"])

    output_path = os.path.join(OUTPUT_DIR, os.path.splitext(name)[0] + "_output.xlsx")
    write_excel(po, TEMPLATE, output_path)
    log.info("%s: wrote %s", name, os.path.relpath(output_path, PROJECT_DIR))

    if load_to_db:
        stats = load_excel_to_sqlite(output_path, db_path)
        log.info("%s: loaded into SQLite %s", name, stats)

    return {"rows": len(po["items"]), "flagged": len(flagged),
            "parse_problems": len(po["problems"])}


def main():
    parser = argparse.ArgumentParser(description="Purchase order text -> Excel -> SQLite")
    parser.add_argument("files", nargs="*", help="PO text files (default: input/*.txt)")
    parser.add_argument("--no-load", action="store_true", help="skip the SQLite load")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite database file")
    args = parser.parse_args()

    log_file = setup_logging()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    files = args.files or sorted(glob.glob(os.path.join(INPUT_DIR, "*.txt")))
    log.info("Run started: %d file(s) to process", len(files))

    total_rows = total_flagged = total_problems = 0
    failed_files = []

    for path in files:
        try:
            result = process_file(path, not args.no_load, args.db)
            total_rows += result["rows"]
            total_flagged += result["flagged"]
            total_problems += result["parse_problems"]
        except Exception as error:
            log.error("%s: FAILED - %s", os.path.basename(path), error)
            failed_files.append(os.path.basename(path))

    status = "FAILED" if failed_files else ("WARNING" if total_flagged or total_problems else "OK")
    log.info("==== RUN SUMMARY: status=%s | files=%d | failed=%d | rows processed=%d | "
             "rows flagged=%d | parse problems=%d ====",
             status, len(files), len(failed_files), total_rows, total_flagged, total_problems)
    if failed_files:
        log.error("Failed files: %s", ", ".join(failed_files))
    log.info("Log file: %s", os.path.relpath(log_file, PROJECT_DIR))

    return 1 if failed_files else 0


if __name__ == "__main__":
    sys.exit(main())
