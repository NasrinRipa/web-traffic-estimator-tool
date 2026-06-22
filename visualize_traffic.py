"""
Categorize enriched leads by their estimated web traffic level and visualize it.

Inputs
------
leads_with_age_and_traffic.csv  (produced by enrich_leads.py)

Outputs
-------
1. traffic_level_summary.csv  -> count + percentage per traffic level
2. traffic_level_chart.png    -> bar chart (count per level) + pie (share)

Usage
-----
    python visualize_traffic.py
    python visualize_traffic.py --input leads_with_age_and_traffic.csv
"""

import argparse
import sys

import pandas as pd

# Use a non-interactive backend so the script works headless (no display needed).
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# Fixed display order, best -> worst, with "Not Available" last.
LEVEL_ORDER = ["High", "Medium", "Low", "Very Low", "Not Available"]

# A distinct, intuitive color per level (green=high ... grey=unknown).
LEVEL_COLORS = {
    "High": "#2e7d32",        # green
    "Medium": "#f9a825",      # amber
    "Low": "#ef6c00",         # orange
    "Very Low": "#c62828",    # red
    "Not Available": "#9e9e9e",  # grey
}

TRAFFIC_COLUMN = "estimated_web_traffic_level"

DEFAULT_INPUT = "leads_with_age_and_traffic.csv"
SUMMARY_CSV = "traffic_level_summary.csv"
CHART_PNG = "traffic_level_chart.png"


def load_data(input_path):
    """Read the enriched CSV and validate the traffic column exists."""
    try:
        df = pd.read_csv(input_path, dtype=str, keep_default_na=False)
    except FileNotFoundError:
        print(f"Error: input file not found: {input_path}")
        print("Run enrich_leads.py first to generate it.")
        sys.exit(1)
    except pd.errors.EmptyDataError:
        print(f"Error: input file is empty: {input_path}")
        sys.exit(1)

    if TRAFFIC_COLUMN not in df.columns:
        print(f"Error: column '{TRAFFIC_COLUMN}' not found in {input_path}.")
        sys.exit(1)

    return df


def build_summary(df):
    """
    Count leads per traffic level in the canonical order and add percentages.

    Returns a DataFrame with columns: traffic_level, count, percentage.
    """
    # Normalize any unexpected/blank labels into "Not Available".
    levels = df[TRAFFIC_COLUMN].where(df[TRAFFIC_COLUMN].isin(LEVEL_ORDER), "Not Available")

    counts = levels.value_counts()
    # Reindex onto the fixed order so every category appears (0 if absent).
    counts = counts.reindex(LEVEL_ORDER, fill_value=0)

    total = int(counts.sum())
    percentages = (counts / total * 100).round(1) if total else counts * 0

    summary = pd.DataFrame({
        "traffic_level": counts.index,
        "count": counts.values,
        "percentage": percentages.values,
    })
    return summary, total


def draw_chart(summary, total, output_path):
    """Draw a bar chart (counts) beside a pie chart (share) and save to PNG."""
    colors = [LEVEL_COLORS[level] for level in summary["traffic_level"]]

    fig, (ax_bar, ax_pie) = plt.subplots(1, 2, figsize=(13, 6))

    # --- Bar chart: count per level ---
    bars = ax_bar.bar(summary["traffic_level"], summary["count"], color=colors)
    ax_bar.set_title("Leads by Estimated Web Traffic Level", fontsize=13, fontweight="bold")
    ax_bar.set_xlabel("Traffic level")
    ax_bar.set_ylabel("Number of leads")
    ax_bar.bar_label(bars, padding=3, fontweight="bold")  # value on top of each bar
    ax_bar.margins(y=0.12)
    ax_bar.tick_params(axis="x", rotation=15)

    # --- Pie chart: share, excluding empty slices ---
    nonzero = summary[summary["count"] > 0]
    ax_pie.pie(
        nonzero["count"],
        labels=nonzero["traffic_level"],
        colors=[LEVEL_COLORS[l] for l in nonzero["traffic_level"]],
        autopct="%1.1f%%",
        startangle=90,
        counterclock=False,
    )
    ax_pie.set_title("Traffic Level Share", fontsize=13, fontweight="bold")

    fig.suptitle(f"Lead Traffic Distribution  (total = {total} leads)", fontsize=15, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Categorize and visualize lead traffic levels.")
    parser.add_argument("-i", "--input", default=DEFAULT_INPUT,
                        help=f"Enriched CSV to read (default: {DEFAULT_INPUT}).")
    parser.add_argument("--summary", default=SUMMARY_CSV,
                        help=f"Summary CSV to write (default: {SUMMARY_CSV}).")
    parser.add_argument("--chart", default=CHART_PNG,
                        help=f"Chart image to write (default: {CHART_PNG}).")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    df = load_data(args.input)
    summary, total = build_summary(df)

    # Save the category counts as a small CSV.
    summary.to_csv(args.summary, index=False)

    # Draw and save the visualization.
    draw_chart(summary, total, args.chart)

    # Print the breakdown to the terminal.
    print(f"Categorized {total} leads by traffic level:\n")
    for _, row in summary.iterrows():
        print(f"  {row['traffic_level']:<14} {int(row['count']):>4}  ({row['percentage']:.1f}%)")
    print(f"\nSaved summary -> {args.summary}")
    print(f"Saved chart   -> {args.chart}")


if __name__ == "__main__":
    main()
