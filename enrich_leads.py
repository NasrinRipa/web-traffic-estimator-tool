"""
Lead data enrichment tool.

Reads an ecommerce leads CSV, keeps every original column, and appends two
enrichment columns:

    1. website_age_years            -> age of the lead's domain in years (via WHOIS)
    2. estimated_web_traffic_level  -> "High" / "Medium" / "Low" / "Very Low" / "Not Available"

Real traffic numbers are private, so the traffic level is a heuristic built from
signals that already exist in the CSV (domain age, ecommerce platform, lead
score, social presence, and business type).

Usage:
    python enrich_leads.py <input.csv>
    python enrich_leads.py <input.csv> --output custom_name.csv --delay 1.5
"""

import argparse
import sys
from datetime import datetime, timezone
from time import sleep
from urllib.parse import urlparse

import pandas as pd

try:
    import whois  # provided by the `python-whois` package
except ImportError:  # pragma: no cover - guidance for a missing dependency
    print(
        "Missing dependency 'python-whois'. Install requirements first:\n"
        "    pip install -r requirements.txt"
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Output file name (per the spec).
DEFAULT_OUTPUT = "leads_with_age_and_traffic.csv"

# Default seconds to wait between *live* WHOIS lookups to avoid rate limits.
DEFAULT_DELAY = 1.0

# Social / platform / directory hosts whose URLs are NOT real business websites.
# We compare against the registrable host, so we list bare domains here.
IGNORED_DOMAINS = {
    "instagram.com",
    "facebook.com",
    "fb.com",
    "google.com",          # covers google.com/maps and other google links
    "goo.gl",
    "maps.google.com",
    "tiktok.com",
    "linkedin.com",
    "youtube.com",
    "youtu.be",
    "twitter.com",
    "x.com",
    "wa.me",               # WhatsApp click-to-chat links
    "t.me",
    "linktr.ee",
    "bit.ly",
}

# The label used when no age-based traffic estimate is possible.
NOT_AVAILABLE = "Not Available"


# ---------------------------------------------------------------------------
# URL / domain helpers
# ---------------------------------------------------------------------------

def clean_url(raw_url):
    """
    Normalize a raw website cell into something urlparse can handle.

    - Returns None for empty / NaN / obviously invalid values.
    - Strips surrounding whitespace.
    - Adds an "http://" scheme if the value has none, so that urlparse treats
      the leading token as a network location instead of a path.
    """
    # pandas represents empty cells as float NaN; guard against that and None.
    if raw_url is None:
        return None
    if isinstance(raw_url, float) and pd.isna(raw_url):
        return None

    url = str(raw_url).strip()
    if not url or url.lower() in {"nan", "none", "null"}:
        return None

    # Without a scheme, urlparse puts the host in `path`; prepend one.
    if "://" not in url:
        url = "http://" + url

    return url


def extract_domain(raw_url):
    """
    Extract the registrable domain (e.g. "example.com") from a website value.

    Returns the lowercased domain without a leading "www.", or None if the
    value is empty or cannot be parsed into a host.
    """
    cleaned = clean_url(raw_url)
    if cleaned is None:
        return None

    try:
        host = urlparse(cleaned).netloc.lower()
    except ValueError:
        # Malformed URLs (e.g. bad characters) should never crash the run.
        return None

    if not host:
        return None

    # Drop any userinfo / port that may be attached to the netloc.
    host = host.split("@")[-1].split(":")[0]

    # Normalize away a leading "www." so caching and matching are consistent.
    if host.startswith("www."):
        host = host[4:]

    # A real domain needs at least one dot (e.g. "example.com").
    if "." not in host:
        return None

    return host


def is_ignored_domain(domain):
    """
    Return True if `domain` is a social/platform/directory host we should skip.

    Matches the exact domain or any subdomain of an ignored host, so
    "m.facebook.com" and "business.facebook.com" are both ignored.
    """
    if not domain:
        return True  # nothing usable -> treat as ignored

    for ignored in IGNORED_DOMAINS:
        if domain == ignored or domain.endswith("." + ignored):
            return True
    return False


# ---------------------------------------------------------------------------
# WHOIS / age helpers
# ---------------------------------------------------------------------------

def _coerce_creation_date(creation_date):
    """
    Reduce a WHOIS creation_date (which may be a single value, a list, or None)
    to the earliest valid datetime.

    Returns a naive datetime (tzinfo stripped) or None if nothing valid found.
    """
    if creation_date is None:
        return None

    # WHOIS libraries sometimes return a list of dates; pick the earliest.
    candidates = creation_date if isinstance(creation_date, (list, tuple)) else [creation_date]

    valid_dates = []
    for value in candidates:
        if isinstance(value, datetime):
            # Strip timezone info so we can compare all dates uniformly.
            if value.tzinfo is not None:
                value = value.astimezone(timezone.utc).replace(tzinfo=None)
            valid_dates.append(value)

    if not valid_dates:
        return None

    return min(valid_dates)


def get_domain_age(domain, cache, delay=DEFAULT_DELAY):
    """
    Look up a domain's age in years via WHOIS, with caching and safe error
    handling.

    Parameters
    ----------
    domain : str
        The registrable domain to query (e.g. "example.com").
    cache : dict
        Maps domain -> age (float years) or None. Mutated in place so repeated
        domains are only queried once.
    delay : float
        Seconds to sleep after a *live* lookup to avoid rate limits. Cached
        hits do not sleep.

    Returns
    -------
    float or None
        Age in years rounded to one decimal, or None when unknown.
    """
    if not domain:
        return None

    # Serve from cache without hitting the network (and without sleeping).
    if domain in cache:
        return cache[domain]

    age_years = None
    try:
        record = whois.whois(domain)
        created = _coerce_creation_date(record.creation_date)
        if created is not None:
            now = datetime.utcnow()
            delta_days = (now - created).days
            if delta_days >= 0:
                age_years = round(delta_days / 365.25, 1)
    except Exception as exc:  # noqa: BLE001 - WHOIS can raise almost anything
        # Any failure (network, parser, no record) must not stop the program.
        print(f"  ! WHOIS lookup failed for {domain}: {exc}")
        age_years = None
    finally:
        # Be polite to WHOIS servers between live queries only.
        sleep(delay)

    cache[domain] = age_years
    return age_years


# ---------------------------------------------------------------------------
# Traffic scoring
# ---------------------------------------------------------------------------

def _age_score(age_years):
    """Points contributed by domain age."""
    if age_years is None:
        return 0
    if age_years >= 10:
        return 25
    if age_years >= 5:
        return 20
    if age_years >= 2:
        return 10
    return 5  # 0 <= age < 2


def _platform_score(platform):
    """Points contributed by the ecommerce platform."""
    name = (str(platform).strip().lower() if platform is not None else "")
    if name in {"shopify", "magento"}:
        return 20
    if name == "woocommerce":
        return 15
    return 5  # unknown / missing / other


def _lead_score_points(score):
    """Points contributed by the existing lead score."""
    try:
        value = float(score)
    except (TypeError, ValueError):
        return 5  # missing / non-numeric -> lowest bucket
    if value >= 85:
        return 20
    if value >= 75:
        return 15
    if value >= 65:
        return 10
    return 5


def _has_value(cell):
    """True if a CSV cell holds a real, non-empty value."""
    if cell is None:
        return False
    if isinstance(cell, float) and pd.isna(cell):
        return False
    text = str(cell).strip().lower()
    return text not in {"", "nan", "none", "null"}


def _social_score(instagram_handle, facebook_url):
    """Points contributed by social media presence."""
    has_ig = _has_value(instagram_handle)
    has_fb = _has_value(facebook_url)
    if has_ig and has_fb:
        return 20
    if has_ig or has_fb:
        return 10
    return 0


def _business_type_score(niche):
    """Points contributed by whether the lead sells online and/or in-store."""
    text = (str(niche).lower() if niche is not None else "")
    online = "onlinestore" in text
    in_store = "instore" in text
    if online and in_store:
        return 20
    if online:
        return 15
    if in_store:
        return 5
    return 0  # niche gives no business-type signal


def calculate_traffic_score(age_years, platform, lead_score, instagram_handle,
                            facebook_url, niche):
    """
    Combine all signals into a single traffic score (0-105).

    Each signal is scored independently and summed, per the spec's rules.
    """
    return (
        _age_score(age_years)
        + _platform_score(platform)
        + _lead_score_points(lead_score)
        + _social_score(instagram_handle, facebook_url)
        + _business_type_score(niche)
    )


def traffic_level_from_score(score):
    """Map a numeric traffic score onto a coarse traffic level label."""
    if score >= 80:
        return "High"
    if score >= 60:
        return "Medium"
    if score >= 40:
        return "Low"
    return "Very Low"


# ---------------------------------------------------------------------------
# Main processing
# ---------------------------------------------------------------------------

# Columns the scoring logic reads. Missing ones are created empty so the run
# can still proceed (with weaker signals) instead of crashing.
EXPECTED_COLUMNS = [
    "website", "platform", "score", "instagram_handle", "facebook_url", "niche",
]


def process_csv(input_path, output_path=DEFAULT_OUTPUT, delay=DEFAULT_DELAY):
    """
    Read `input_path`, enrich every row, and write `output_path`.

    Returns a summary dict so callers/tests can inspect the results.
    """
    # --- Load -------------------------------------------------------------
    try:
        df = pd.read_csv(input_path, dtype=str, keep_default_na=False)
    except FileNotFoundError:
        print(f"Error: input file not found: {input_path}")
        sys.exit(1)
    except pd.errors.EmptyDataError:
        print(f"Error: input file is empty: {input_path}")
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"Error: could not read CSV: {exc}")
        sys.exit(1)

    if df.empty:
        print("Error: the CSV has no data rows; nothing to enrich.")
        sys.exit(1)

    # --- Tolerate missing columns ----------------------------------------
    for column in EXPECTED_COLUMNS:
        if column not in df.columns:
            print(f"  ! Column '{column}' is missing; treating it as empty.")
            df[column] = ""

    # --- Enrich row by row ------------------------------------------------
    age_cache = {}           # domain -> age (years) or None
    website_age_years = []
    traffic_levels = []

    total_rows = len(df)
    valid_domains = 0        # real (non-ignored) domains we attempted
    ages_found = 0           # domains where WHOIS returned a usable age
    ignored_urls = 0         # social/platform/missing URLs skipped

    print(f"Processing {total_rows} rows from {input_path} ...")

    for position, row in enumerate(df.itertuples(index=False), start=1):
        row_map = row._asdict()
        domain = extract_domain(row_map.get("website"))

        if domain is None or is_ignored_domain(domain):
            # Ignored or missing website: blank age, traffic "Not Available".
            ignored_urls += 1
            website_age_years.append(None)
            traffic_levels.append(NOT_AVAILABLE)
            continue

        valid_domains += 1
        age = get_domain_age(domain, age_cache, delay=delay)
        if age is not None:
            ages_found += 1

        # Build the traffic score and level from all available signals.
        score = calculate_traffic_score(
            age_years=age,
            platform=row_map.get("platform"),
            lead_score=row_map.get("score"),
            instagram_handle=row_map.get("instagram_handle"),
            facebook_url=row_map.get("facebook_url"),
            niche=row_map.get("niche"),
        )
        website_age_years.append(age)
        traffic_levels.append(traffic_level_from_score(score))

        if position % 25 == 0:
            print(f"  ... {position}/{total_rows} rows done")

    # --- Attach new columns & save ---------------------------------------
    df["website_age_years"] = website_age_years
    df["estimated_web_traffic_level"] = traffic_levels

    try:
        df.to_csv(output_path, index=False)
    except Exception as exc:  # noqa: BLE001
        print(f"Error: could not write output CSV: {exc}")
        sys.exit(1)

    # --- Summary ----------------------------------------------------------
    summary = {
        "total_rows": total_rows,
        "valid_domains": valid_domains,
        "ages_found": ages_found,
        "ignored_urls": ignored_urls,
        "output_path": output_path,
    }

    print("\n=== Enrichment summary ===")
    print(f"  Total rows processed         : {summary['total_rows']}")
    print(f"  Valid (non-ignored) domains  : {summary['valid_domains']}")
    print(f"  Websites where age was found : {summary['ages_found']}")
    print(f"  Ignored social/platform URLs : {summary['ignored_urls']}")
    print(f"  Output written to            : {summary['output_path']}")

    return summary


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Enrich an ecommerce leads CSV with website age and an "
                    "estimated web traffic level."
    )
    parser.add_argument("input", help="Path to the input leads CSV file.")
    parser.add_argument(
        "-o", "--output", default=DEFAULT_OUTPUT,
        help=f"Output CSV path (default: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "-d", "--delay", type=float, default=DEFAULT_DELAY,
        help=f"Seconds to wait between live WHOIS lookups (default: {DEFAULT_DELAY}).",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    process_csv(args.input, output_path=args.output, delay=args.delay)


if __name__ == "__main__":
    main()
