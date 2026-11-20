HEADER_ALIASES = {
    "BUYER": "buyer",
    "SHIP TERMS": "ship_terms",
    "PO#": "po_number",
    "PO NUMBER": "po_number",
    "REF MASTER PO#": "ref_master_po",
    "REF PO": "ref_master_po",
    "SHIP DATE": "ship_date",
}

ITEM_ALIASES = {
    "SKU": "sku",
    "UPC": "upc",
    "DEPT": "dept",
    "DPT": "dept",
    "VENDOR PART#": "vendor_part_no",
    "DESC": "description",
    "DESCRIPTION": "description",
    "RETAIL": "retail",
    "COST": "cost",
    "EXT COST": "ext_cost",
    "CARTONS": "cartons",
    "CTNS": "cartons",
    "CASE PACK": "case_pack",
    "CSPK": "case_pack",
    "EXT QTY": "ext_qty",
    "CUBE": "cube",
    "KG": "kilograms",
    "KILOGRAMS": "kilograms",
}

INTEGER_FIELDS = ["cartons", "case_pack", "ext_qty"]
DECIMAL_FIELDS = ["retail", "cost", "ext_cost", "cube", "kilograms"]

TEMPLATE_COLUMNS = [
    ("FILENAME", "source_file"),
    ("BUYER", "buyer"),
    ("SHIP TERMS", "ship_terms"),
    ("PO#", "po_number"),
    ("REF MASTER PO#", "ref_master_po"),
    ("SHIP DATE", "ship_date"),
    ("VENDOR", "vendor"),
    ("SHIP TO", "ship_to"),
    ("BILL TO", "bill_to"),
    ("Dept", "dept"),
    ("SKU", "sku"),
    ("UPC", "upc"),
    ("Vendor Part #", "vendor_part_no"),
    ("Description", "description"),
    ("Retail", "retail"),
    ("Cost", "cost"),
    ("EXT Cost", "ext_cost"),
    ("CTNS", "cartons"),
    ("CSPK", "case_pack"),
    ("EXT QTY", "ext_qty"),
    ("Cube", "cube"),
    ("Kilograms", "kilograms"),
    ("Total Cost", "total_cost"),
]
