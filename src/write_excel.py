from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill

from fields import TEMPLATE_COLUMNS

YELLOW = PatternFill(start_color="FFFF99", end_color="FFFF99", fill_type="solid")


def build_rows(po):
    rows = []
    for item in po["items"]:
        row = {"source_file": po["source_file"], **po["header"], **item}
        rows.append(row)
    return rows


def write_excel(po, template_path, output_path):
    wb = load_workbook(template_path)
    sheet = wb.active

    template_headers = [cell.value for cell in sheet[1]]
    expected_headers = [header for header, _ in TEMPLATE_COLUMNS]
    if template_headers != expected_headers:
        raise ValueError(f"Template columns changed! template={template_headers}")

    for row in build_rows(po):
        sheet.append([row.get(field) for _, field in TEMPLATE_COLUMNS])
        if row["flags"]:
            for cell in sheet[sheet.max_row]:
                cell.fill = YELLOW

    formats = {"Retail": "0.00", "Cost": "0.000", "EXT Cost": "0.000",
               "Cube": "0.0000", "Kilograms": "0.00", "Total Cost": "0.000"}
    for col_idx, header in enumerate(expected_headers, start=1):
        if header in formats:
            for (cell,) in sheet.iter_rows(min_row=2, min_col=col_idx, max_col=col_idx):
                cell.number_format = formats[header]

    flags_sheet = wb.create_sheet("Validation Flags")
    flags_sheet.append(["FILENAME", "PO#", "SKU", "Flag", "Detail", "Decision"])
    for cell in flags_sheet[1]:
        cell.font = Font(bold=True)
    for item in po["items"]:
        for f in item["flags"]:
            flags_sheet.append([po["source_file"], po["header"]["po_number"],
                                item["sku"], f["flag"], f["detail"], f["decision"]])

    wb.save(output_path)
