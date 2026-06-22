# web-traffic-estimator-tool

A Python tool that enriches ecommerce lead data with **website age** and an
**estimated web traffic level**, then categorizes and visualizes the leads by
that traffic level.

Real website traffic is private, so this tool *estimates* a traffic level from
signals that are already available in the lead data — domain age, ecommerce
platform, lead score, social presence, and business type — and rolls them into a
single score mapped to **High / Medium / Low / Very Low / Not Available**.

---

## Table of contents

- [Overview](#overview)
- [How it works](#how-it-works)
- [Scoring methodology](#scoring-methodology)
- [Results](#results)
  - [Traffic level distribution](#1-traffic-level-distribution)
  - [Business vs traffic level](#2-business-vs-traffic-level)
- [Key findings](#key-findings)
- [Deliverables](#deliverables)
- [How to run](#how-to-run)
- [Limitations](#limitations)

---

## Overview

The pipeline takes a raw ecommerce leads CSV and produces:

1. An **enriched CSV** with two new columns — `website_age_years` and
   `estimated_web_traffic_level`.
2. A **distribution chart** showing how many leads fall into each traffic level.
3. An **Excel workbook** with the leads sorted and split by traffic level.
4. A **per-business chart** plotting every lead against its traffic level.

This report was generated from a dataset of **466 ecommerce leads** (primarily
in the UAE and Kuwait markets).

---

## How it works

The enrichment runs in two stages.

### 1. Website age (via WHOIS)

- The main domain is extracted from each lead's `website` value
  (e.g. `https://www.example.com/path` → `example.com`).
- Social / platform / directory URLs are **ignored** — `instagram.com`,
  `facebook.com`, `google.com/maps`, `tiktok.com`, `linkedin.com`,
  `youtube.com`, and similar — because they are not real business websites.
- A **WHOIS** lookup retrieves the domain's creation date, and age is computed
  in years against the current date. If WHOIS returns a list of dates, the
  **earliest valid** one is used.
- Results are **cached per domain** (repeated domains are queried only once),
  WHOIS errors are **handled safely** so the run never stops, and a short
  **delay** is added between live lookups to respect rate limits.

### 2. Traffic level estimate

Each lead earns a **traffic score** (0–105) by summing points across five
signals, which is then bucketed into a level.

---

## Scoring methodology

| Signal | Rule | Points |
|---|---|---|
| **Website age** | ≥ 10 yrs | +25 |
| | ≥ 5 yrs | +20 |
| | ≥ 2 yrs | +10 |
| | < 2 yrs | +5 |
| | unknown | +0 |
| **Platform** | Shopify / Magento | +20 |
| | WooCommerce | +15 |
| | unknown / missing | +5 |
| **Lead score** | ≥ 85 | +20 |
| | ≥ 75 | +15 |
| | ≥ 65 | +10 |
| | < 65 | +5 |
| **Social presence** | both Instagram & Facebook | +20 |
| | either one | +10 |
| | none | +0 |
| **Business type** | onlineStore **and** inStore | +20 |
| | onlineStore only | +15 |
| | inStore only | +5 |

**Score → level:**

| Traffic score | Level |
|---|---|
| ≥ 80 | 🟢 High |
| ≥ 60 | 🟡 Medium |
| ≥ 40 | 🟠 Low |
| < 40 | 🔴 Very Low |
| ignored / missing website | ⚪ Not Available |

---

## Results

### 1. Traffic level distribution

How the 466 leads split across the five traffic levels, shown as a count bar
chart and a share pie chart.

![Traffic level distribution](traffic_level_chart.png)

### 2. Business vs traffic level

Every business plotted against its estimated traffic level (High = 4 down to
Not Available = 0), grouped by level. *(Open the full-resolution image to read
individual business names.)*

![Business vs traffic level](business_vs_traffic.png)

---

## Key findings

Out of **466 leads**:

| Level | Leads | Share |
|---|---|---|
| 🟢 High | 151 | 32.4% |
| 🟡 Medium | 146 | 31.3% |
| 🟠 Low | 121 | 26.0% |
| 🔴 Very Low | 38 | 8.2% |
| ⚪ Not Available | 10 | 2.1% |

- Nearly **two-thirds (63.7%)** of leads land in the **High** or **Medium**
  tiers — a strong, established pool of prospects.
- A valid business domain was found for **456** leads; only **10** pointed to
  social/platform URLs and were marked *Not Available*.
- **Website age was resolved for 332 domains.** Most unresolved cases were
  `.com.kw` (Kuwait) domains, whose registry does not expose a public WHOIS
  creation date — those leads are still scored from the other four signals.

---

## Deliverables

| File | Description |
|---|---|
| `leads_with_age_and_traffic.csv` | All original columns + `website_age_years` + `estimated_web_traffic_level`. |
| `leads_sorted_by_traffic.xlsx` | Leads sorted by traffic level; one combined sheet plus a sheet per category (High, Medium, Low, Very Low, Not Available). |
| `traffic_level_chart.png` | Distribution bar + pie chart. |
| `business_vs_traffic.png` | Per-business traffic-level chart (all 466 leads). |

---

## How to run

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Enrich the leads (adds website age + traffic level)
python enrich_leads.py "leads.csv"

# 3. Build the distribution chart + summary
python visualize_traffic.py

# 4. Export the sorted Excel workbook
python export_sorted_excel.py

# 5. Build the per-business chart
python chart_business_vs_traffic.py
```

---

## Limitations

- **Traffic is estimated, not measured.** Real traffic numbers are private; this
  is a heuristic proxy built from available signals.
- **WHOIS coverage is uneven.** Some TLDs (notably `.com.kw`) do not publish
  creation dates, so those leads have a blank age and lose the age signal.
- **WHOIS rate limits** mean large datasets take time — the tool paces and caches
  lookups, but a big file can still take several minutes.
