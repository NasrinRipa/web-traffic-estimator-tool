"""
Sort enriched leads by estimated web traffic level and export to one Excel file.

Reads leads_with_age_and_traffic.csv and writes leads_sorted_by_traffic.xlsx with:
  - "All (sorted)" : every lead, ordered High -> Medium -> Low -> Very Low -> Not Available
  - One sheet per category: "High", "Medium", "Low", "Very Low", "Not Available"

All original columns are preserved exactly as in the CSV.

Usage:
    python export_sorted_excel.py
    python export_sorted_excel.py --input leads_with_age_and_traffic.csv --output myfile.xlsx
"""

import argparse
import sys

import pandas as pd

# Category order, best -> worst, with unknown last.
LEVEL_ORDER = ["High", "Medium", "Low", "Very Low", "Not Available"]
TRAFFIC_COLUMN = "estimated_web_traffic_level"

DEFAULT_INPUT = "leads_with_age_and_traffic.csv"
DEFAULT_OUTPUT = "leads_sorted_by_traffic.xlsx"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Sort leads by web traffic level and export to Excel."
    )
    parser.add_argument("-i", "--input", default=DEFAULT_INPUT,
                        help=f"Enriched CSV to read (default: {DEFAULT_INPUT}).")
    parser.add_argument("-o", "--output", default=DEFAULT_OUTPUT,
                        help=f"Excel file to write (default: {DEFAULT_OUTPUT}).")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    # --- Load (as strings, so we keep the original cell values untouched) ---
    try:
        df = pd.read_csv(args.input, dtype=str, keep_default_na=False)
    except FileNotFoundError:
        print(f"Error: input file not found: {args.input}")
        print("Run enrich_leads.py first to generate it.")
        sys.exit(1)
    except pd.errors.EmptyDataError:
        print(f"Error: input file is empty: {args.input}")
        sys.exit(1)

    if TRAFFIC_COLUMN not in df.columns:
        print(f"Error: column '{TRAFFIC_COLUMN}' not found in {args.input}.")
        sys.exit(1)

    # Normalize any blank/unexpected label to "Not Available" so every row
    # lands in exactly one of the five categories.
    df[TRAFFIC_COLUMN] = df[TRAFFIC_COLUMN].where(
        df[TRAFFIC_COLUMN].isin(LEVEL_ORDER), "Not Available"
    )

    # --- Sort: primary by traffic level order, secondary by lead score desc ---
    # A numeric helper for the secondary sort (kept separate, dropped before export).
    df["_level_rank"] = pd.Categorical(df[TRAFFIC_COLUMN], categories=LEVEL_ORDER, ordered=True)
    df["_score_num"] = pd.to_numeric(df.get("score"), errors="coerce")

    df_sorted = df.sort_values(
        by=["_level_rank", "_score_num"],
        ascending=[True, False],
        kind="stable",
    ).drop(columns=["_level_rank", "_score_num"])

    # --- Write the workbook ---
    try:
        with pd.ExcelWriter(args.output, engine="openpyxl") as writer:
            # Combined, fully sorted sheet.
            df_sorted.to_excel(writer, sheet_name="All (sorted)", index=False)

            # One sheet per category (only those with at least one lead).
            for level in LEVEL_ORDER:
                subset = df_sorted[df_sorted[TRAFFIC_COLUMN] == level]
                if subset.empty:
                    continue
                # Excel sheet names can't contain certain chars; our names are safe.
                subset.to_excel(writer, sheet_name=level, index=False)
    except PermissionError:
        print(f"Error: could not write {args.output}. "
              "Close the file in Excel if it is open, then re-run.")
        sys.exit(1)

    # --- Report ---
    print(f"Wrote {args.output}")
    print(f"  Sheet 'All (sorted)'  : {len(df_sorted)} leads (all columns kept)")
    for level in LEVEL_ORDER:
        count = int((df_sorted[TRAFFIC_COLUMN] == level).sum())
        if count:
            print(f"  Sheet '{level}'{' ' * (14 - len(level))}: {count} leads")


if __name__ == "__main__":
    main()
