import os
import re
from datetime import datetime

from fields import HEADER_ALIASES, ITEM_ALIASES, INTEGER_FIELDS, DECIMAL_FIELDS

LABEL_VALUE = re.compile(r"(?<![A-Za-z#])([A-Z][A-Z#/]*(?: [A-Z#/]+)*)\s*:\s*(\S.*?)(?=\s{2,}|$)")

TABLE_ITEM_LINE = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+(\S+)\s+(.*?)"
    r"\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)"
    r"\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*$"
)
TABLE_COLUMNS = ["dept", "sku", "vendor_part_no", "description", "retail", "cost",
                 "ext_cost", "cartons", "case_pack", "ext_qty", "cube", "kilograms"]

TABLE_UPC_LINE = re.compile(r"^\s+(\d{12,14})\s*$")


def find_label_values(line):
    return [(" ".join(label.split()), value.strip())
            for label, value in LABEL_VALUE.findall(line)]


def is_dash_line(line):
    return line.strip() != "" and set(line.strip()) <= {"-", " "}


def read_block(lines, start):
    block = []
    for line in lines[start:]:
        if line.strip() == "":
            break
        block.append(line)
    return block


def normalize_date(text):
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return text


def detect_layout(lines):
    for line in lines:
        text = line.strip().upper()
        if text.startswith("SKU:"):
            return "labeled"
        if text.startswith("DPT") and "DESCRIPTION" in text:
            return "table"
    raise ValueError("Unknown PO layout: no 'DPT ... DESCRIPTION' table header "
                     "and no 'SKU:' item lines found")


def parse_header(lines):
    header = {}
    for line in lines:
        if is_dash_line(line):
            break
        for label, value in find_label_values(line):
            field = HEADER_ALIASES.get(label)
            if field and field not in header:
                header[field] = value
    return header


def parse_addresses(lines):
    vendor = ship_to = bill_to = ""

    for i, line in enumerate(lines):
        text = line.strip().upper()

        if text in ("VENDOR", "VENDOR ADDRESS"):
            vendor = ", ".join(row.strip() for row in read_block(lines, i + 2))

        elif "SHIP TO" in text and "BILL TO" in text:
            ship_col = line.upper().index("SHIP TO")
            bill_col = line.upper().index("BILL TO")
            split_at = max(ship_col, bill_col)

            left, right = [], []
            for row in read_block(lines, i + 2):
                if row[:split_at].strip():
                    left.append(row[:split_at].strip())
                if row[split_at:].strip():
                    right.append(row[split_at:].strip())

            if ship_col < bill_col:
                ship_to, bill_to = ", ".join(left), ", ".join(right)
            else:
                bill_to, ship_to = ", ".join(left), ", ".join(right)

    return vendor, ship_to, bill_to


def parse_table_items(lines, problems):
    items = []
    in_table = False

    for line_no, line in enumerate(lines, start=1):
        text = line.strip().upper()
        if text.startswith("DPT") and "DESCRIPTION" in text:
            in_table = True
            continue
        if not in_table or text == "" or is_dash_line(line):
            continue
        if text.startswith("TOTALS"):
            break

        item_match = TABLE_ITEM_LINE.match(line)
        upc_match = TABLE_UPC_LINE.match(line)

        if item_match:
            item = dict(zip(TABLE_COLUMNS, item_match.groups()))
            item["upc"] = None
            item["line_no"] = line_no
            items.append(item)
        elif upc_match and items and items[-1]["upc"] is None:
            items[-1]["upc"] = upc_match.group(1)
        else:
            problems.append(f"line {line_no}: could not understand line: {line.strip()!r}")

    return items


def parse_labeled_items(lines, problems):
    items = []
    current = None

    for line_no, line in enumerate(lines, start=1):
        text = line.strip().upper()
        if text.startswith("TOTALS"):
            break
        if text.startswith("SKU:"):
            current = {"upc": None, "line_no": line_no}
            items.append(current)
        if current is None or text == "":
            continue

        for label, value in find_label_values(line):
            field = ITEM_ALIASES.get(label)
            if field:
                current[field] = value
            else:
                problems.append(f"line {line_no}: unknown item label {label!r} ignored")

    return items


def convert_numbers(item):
    item["bad_numbers"] = {}
    for field in INTEGER_FIELDS + DECIMAL_FIELDS:
        raw = item.get(field)
        if raw is None:
            continue
        try:
            number = float(raw)
            item[field] = int(number) if field in INTEGER_FIELDS else number
        except ValueError:
            item[field] = None
            item["bad_numbers"][field] = raw


def parse_po(path):
    with open(path, encoding="utf-8") as f:
        lines = [line.expandtabs().rstrip() for line in f.read().splitlines()]

    problems = []
    layout = detect_layout(lines)

    header = parse_header(lines)
    header["vendor"], header["ship_to"], header["bill_to"] = parse_addresses(lines)
    if "ship_date" in header:
        header["ship_date"] = normalize_date(header["ship_date"])

    if layout == "table":
        items = parse_table_items(lines, problems)
    else:
        items = parse_labeled_items(lines, problems)

    for item in items:
        convert_numbers(item)

    if not header.get("po_number"):
        raise ValueError("PO number not found in header")
    if not items:
        raise ValueError("No line items found")

    for field in ("buyer", "ship_terms", "ref_master_po", "ship_date",
                  "vendor", "ship_to", "bill_to"):
        if not header.get(field):
            problems.append(f"header field '{field}' not found")
            header[field] = ""

    return {
        "source_file": os.path.basename(path),
        "layout": layout,
        "header": header,
        "items": items,
        "problems": problems,
    }
