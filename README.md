# Purchase Order Pipeline — BHF Data Engineer Take-Home

Turns vendor purchase-order text files into a validated Excel file (exact template
columns) and loads them into a SQLite table. The load is safe to run more than once.

```
input/*.txt  ──►  parse  ──►  validate  ──►  Excel (output/)  ──►  SQLite (output/purchase_orders.db)
                                    │
                                    └──►  log (console + logs/)
```

## How to run

```bash
pip install -r requirements.txt

python src/run_pipeline.py                 # process every input/*.txt
python src/run_pipeline.py --no-load       # Excel only, skip the database
python src/load_sqlite.py output/purchase_order_sample_output.xlsx   # load step on its own

python -m unittest discover tests -v       # 9 tests
```

## Project structure

| Path | What it does |
|---|---|
| `input/` | The two sample POs and the blank output template |
| `src/fields.py` | Maps each vendor's labels to one internal name (`PO#` / `PO NUMBER` → `po_number`) and lists the template columns |
| `src/parse_po.py` | Detects the layout, then reads the header, the address blocks and the line items |
| `src/validate.py` | Recomputes EXT QTY and EXT COST, and flags every problem along with the decision taken |
| `src/write_excel.py` | Writes the Excel file from the template |
| `src/load_sqlite.py` | Loads the Excel into SQLite with an upsert |
| `src/run_pipeline.py` | Runs every step for every file, handles logging and sets the exit code |
| `sql/schema.sql` | Table DDL |
| `output/` | Generated spreadsheets, one per input file |
| `logs/example_run.log` | Log from two back-to-back runs (shows idempotency) |
| `tests/test_pipeline.py` | Tests for both layouts, the planted problems and idempotency |

## Approach

1. **Detect the layout.** A line starting with `DPT … DESCRIPTION` means the **table** layout
   (sample 1). A line starting with `SKU:` means the **labeled** layout (sample 2).
   If neither is present, the file **fails** with a clear error. It never guesses.
2. **Header.** The header is every `LABEL: value` pair above the first `-----` line,
   found with one regex. Labels go through `HEADER_ALIASES`, so `PO#` and `PO NUMBER`
   both become `po_number`, and `REF MASTER PO#` and `REF PO` both become `ref_master_po`.
   The position of a field on the page does not matter.
3. **Address blocks.** The vendor block is the lines under `VENDOR` / `VENDOR ADDRESS`.
   For Ship To and Bill To, each address line is split at the column where the
   right-hand heading starts. Whether `SHIP TO` or `BILL TO` is on the left is read
   from the heading line, which is how the swapped order in sample 2 is handled.
4. **Line items.**
   - **Table layout:** one regex reads dept, SKU, vendor part#, description and the
     8 numbers. A following line that holds only a 12–14 digit number is that item's UPC.
   - **Labeled layout:** each `SKU:` line starts a new item, and every `LABEL: value`
     on the following lines is mapped through `ITEM_ALIASES`.
5. **Validate.** For each row: EXT QTY = cartons × case pack, and EXT COST = cost × EXT QTY,
   with a 1-cent tolerance.
6. **Output.** The template sheet keeps its exact 23 columns. Flagged rows are
   highlighted yellow, and a second sheet, **Validation Flags**, lists every flag with its
   detail and the decision taken.
7. **Load.** Rows are upserted into SQLite (see below).

### Assumptions

- **FILENAME** = the source text file name.
- **Total Cost** = our recomputed cost × cartons × case pack. **EXT Cost** keeps the
  value printed on the PO, so the two side by side show any mismatch.
- **VENDOR, SHIP TO and BILL TO** hold the whole address block joined with `, `,
  including phone and fax, so nothing is lost.
- **Ship dates** are US month/day order and are normalised to `YYYY-MM-DD`.
- **SKU, UPC, Dept, Vendor Part # and PO#** are kept as **text**, so leading zeros
  (`0091…`, `04212`) survive.
- **One file = one PO.**

## How each messy case is handled

Every row is kept. Nothing is silently dropped.

| Case | Decision | Why |
|---|---|---|
| **SKU 71097218 has no UPC line** | **Flag** `MISSING_UPC`. The row is kept with UPC blank. | All the other fields are fine. Dropping the row would understate the order, and a UPC is a scan identifier, so guessing one could put wrong data into receiving. |
| **SKU 71293252: EXT COST printed 4146.08, computed 4046.08** | **Flag** `EXT_COST_MISMATCH`. The printed value stays in `EXT Cost`; the computed value goes in `Total Cost`. | We should not silently rewrite a vendor's document. Someone has to query the vendor, and they need both numbers to do that. |
| **SKU 71293276: COST printed `55,440`** | **Best guess, verified, then flag** `COST_REPAIRED`. The comma is read as a decimal point (55.440) **only because** 116 × 55.44 = 6431.04, which exactly matches the printed EXT COST. | The rest of the row proves the guess is right, so blanking a value we can verify would be needlessly lossy. If the check had failed, the cost would be left blank and flagged `BAD_NUMBER` for manual review. |
| **Unknown layout, no PO#, or no items** | **Fail the whole file** (logged as ERROR, exit code 1). Other files still run. | Without these we cannot trust any row from the file, so loading part of it would be worse than loading nothing. |
| **Unrecognised line inside the item table** | Logged as `PARSE PROBLEM` with the line number, and counted in the run summary. | It may be a missed item, so a human should see it. |

## Fixed vs. flexible, and what a third vendor would break

**Flexible (no code change needed):**
- the order and position of header fields
- label wording, by adding a line to `fields.py`
- Bill To / Ship To order
- the UPC being inline or on the next line
- extra spaces and tabs

**Fixed (assumed):**
- Header values are `LABEL: value`, and multiple pairs on one line are separated by 2+ spaces.
- The header ends at the first `-----` line.
- **Table layout:** the column order is fixed (dept, SKU, part#, description, then the
  8 numbers in sample 1's order), dept and SKU are numeric, and the description is
  the text between part# and the numbers.
- Ship To and Bill To are side by side, and the left column does not run past the
  right-hand heading.
- The items section ends at `TOTALS`.

**What a third vendor would break:**
- **No `DPT` table header and no `SKU:` lines:** the file fails with "Unknown PO
  layout". That's intended: it fails loudly rather than producing wrong rows. Fix:
  add a detection rule and a small item parser.
- **New label wording** (e.g. `ORDER NO:`): that field comes back empty and is logged
  as a parse problem. Fix: add one alias in `fields.py`.
- **A table with different column order or count:** the item regex won't match, and
  each line is logged as a parse problem, so no row is created from it.
- **Multi-page POs with repeated headers, day/month dates, or several POs in one
  file** are not handled.

## Load step: idempotency / dedupe strategy

- **Natural key:** `PRIMARY KEY (po_number, sku)`. A SKU can appear on many POs, but
  only once per PO.
- **Upsert:** `INSERT … ON CONFLICT(po_number, sku) DO UPDATE SET …`. A new key is
  inserted. An existing key is overwritten with the latest values, and `loaded_at`
  is updated.
- **Transaction:** each file loads inside one transaction, so a crash can't leave a
  half-loaded PO.
- **Proof** (see `logs/example_run.log` and the `TestLoadIsIdempotent` test):

  ```
  run 1: purchase_order_sample.txt   inserted 12, updated 0  -> table 12
         purchase_order_sample_2.txt inserted 6,  updated 0  -> table 18
  run 2: purchase_order_sample.txt   inserted 0,  updated 12 -> table 18
         purchase_order_sample_2.txt inserted 0,  updated 6  -> table 18
  ```

- **Validation flags** are loaded into a `validation_flags` column, so flagged rows
  can be found with SQL:
  `SELECT * FROM po_line_items WHERE validation_flags IS NOT NULL`.

## Log / audit trail: knowing something went wrong overnight

Every run writes to the console and to `logs/pipeline_<timestamp>.log`:

```
WARNING purchase_order_sample.txt: SKU 71293252 EXT_COST_MISMATCH - printed EXT COST 4146.08 vs computed 4046.08 -> ...
==== RUN SUMMARY: status=WARNING | files=2 | failed=0 | rows processed=18 | rows flagged=3 | parse problems=0 ====
```

- **The last line is a one-line summary** with status `OK`, `WARNING` or `FAILED`,
  plus counts of rows processed, rows flagged and parse problems.
- **Exit code 1 if any file failed.** The scheduler (cron, Windows Task Scheduler,
  Airflow) sees that and can alert, with no need to open the Excel.
- **Flags are queryable** in the database, so a morning report or dashboard can show them.

## What I'd change or add with more time

- **Send alerts:** email or Slack when status is `FAILED`, or when flags exceed a threshold.
- **Check PO totals:** compare row sums against the `TOTALS:` line, to catch items the
  parser missed.
- **Handle removed lines:** when a revised PO drops a line, delete it. Today's upsert
  only inserts and updates.
- **Add a `load_runs` audit table:** run time, file, file hash and counts. Skip files
  whose hash was already loaded.
- **Read the table layout's columns from its header line** instead of using a fixed order.
- **Validate the UPC check digit,** and add more unit tests for edge cases.
- **In production:** land the raw files in cloud storage and run this as a scheduled
  Databricks or Airflow job, loading into a Delta or SQL Server table with `MERGE`
  on (po_number, sku).

## AI usage

I used **Claude Code** (Anthropic's CLI assistant, inside VS Code). No `CLAUDE.md`
or other instruction file was used. I directed it through the chat:

1. First I asked it to read the brief and the sample files and to **only explain
   what to do, without writing code**. It gave me a staged plan, and I reviewed the
   files and the edge cases myself.
2. Then I asked it to build the project. I told it to **keep my folder structure**
   (`input/ output/ src/ sql/ logs/`) and to **not over-engineer: keep the code basic
   so I can explain it in the interview.**
3. I checked the results by running the pipeline, reading the generated Excel and
   the database, and running the tests.
4. I asked it to remove all code comments. The explanations of the design live in
   this README instead.

### One thing the AI got wrong

- **Over-engineered first draft.** It started by writing a dataclass models file, and
  it planned a generic "number candidate" resolver and code that would read table
  columns dynamically from the header line. That was far more than this task needs,
  and hard to explain in a walkthrough. I stopped it and told it to keep things basic.
  It deleted the dataclass file, and the final code uses plain dicts, one regex per
  layout, and a single explicit rule for the `55,440` cost.
- **Wrong column count in its plan.** Its written plan said each sample-1 item line
  ends with "9 numeric fields". It actually has **8** (retail, cost, ext cost, ctns,
  cspk, ext qty, cube, kg). A parser built on that would have mis-assigned every
  number. The final regex uses 8.
