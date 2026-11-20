TOLERANCE = 0.01


def add_flag(item, flag, detail, decision):
    item["flags"].append({"flag": flag, "detail": detail, "decision": decision})


def fix_bad_cost(item):
    raw = item["bad_numbers"]["cost"]
    guess = float(raw.replace(",", "."))

    can_check = None not in (item.get("cartons"), item.get("case_pack"), item.get("ext_cost"))
    if can_check and abs(guess * item["cartons"] * item["case_pack"] - item["ext_cost"]) <= TOLERANCE:
        item["cost"] = guess
        add_flag(item, "COST_REPAIRED",
                 f"cost printed as '{raw}', read as {guess}",
                 "best guess, accepted because cost x qty matches printed EXT COST")
    else:
        add_flag(item, "BAD_NUMBER",
                 f"cost printed as '{raw}' and could not be verified",
                 "cost left blank - needs manual review")


def validate_item(item):
    item["flags"] = []

    for field, raw in item["bad_numbers"].items():
        if field == "cost":
            fix_bad_cost(item)
        else:
            add_flag(item, "BAD_NUMBER", f"{field} printed as '{raw}'",
                     f"{field} left blank - needs manual review")

    if not item.get("upc"):
        add_flag(item, "MISSING_UPC", "no UPC found for this SKU",
                 "row kept, UPC left blank - never invent a UPC")

    cartons, case_pack, cost = item.get("cartons"), item.get("case_pack"), item.get("cost")
    if None in (cartons, case_pack, cost):
        item["total_cost"] = None
        add_flag(item, "CANNOT_VALIDATE", "cost/cartons/case pack missing",
                 "totals not checked")
        return

    calc_qty = cartons * case_pack
    calc_cost = round(cost * calc_qty, 3)
    item["total_cost"] = calc_cost

    if item.get("ext_qty") != calc_qty:
        add_flag(item, "EXT_QTY_MISMATCH",
                 f"printed EXT QTY {item.get('ext_qty')} vs computed {calc_qty}",
                 "printed value kept, flagged for review")

    if item.get("ext_cost") is None or abs(item["ext_cost"] - calc_cost) > TOLERANCE:
        add_flag(item, "EXT_COST_MISMATCH",
                 f"printed EXT COST {item.get('ext_cost')} vs computed {calc_cost}",
                 "printed value kept in 'EXT Cost', computed value in 'Total Cost'")


def validate_po(po):
    seen_skus = set()
    for item in po["items"]:
        validate_item(item)
        if item["sku"] in seen_skus:
            add_flag(item, "DUPLICATE_SKU", f"SKU {item['sku']} appears more than once",
                     "row kept; database load will keep the last one")
        seen_skus.add(item["sku"])
    return po
