"""Build or update a daily panel of all Iranian mutual funds from FIPIRAN.

    python scripts/fund_panel.py --start 2025-02-17 --out funds.parquet          # build
    python scripts/fund_panel.py --start 2025-02-17 --details --out funds.csv    # with licences/investors
    python scripts/fund_panel.py --update funds.parquet                          # append new days only

Use .parquet for speed or .csv for Excel (written with a BOM so Persian text displays).
"""

import argparse
import logging
from datetime import date

from tehran_data.fund_panel import FundPanelBuilder, update_panel, write_panel

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--start", help="first day, YYYY-MM-DD")
p.add_argument("--end", default=date.today().isoformat())
p.add_argument("--details", action="store_true", help="also fetch per-fund details (slower)")
p.add_argument("--no-index", action="store_true", help="skip the TSETMC market index return")
p.add_argument("--out", default="fund_panel.parquet")
p.add_argument("--update", metavar="FILE", help="append days after the last date in FILE")
a = p.parse_args()

opts = {"details": a.details, "index": not a.no_index}
if a.update:
    panel = update_panel(a.update, end=a.end, **opts)
    print(f"{a.update}: {len(panel):,} rows, last day {panel['date'].max().date()}")
else:
    if not a.start:
        p.error("--start is required when building a new panel")
    panel = FundPanelBuilder().build(a.start, a.end, **opts)
    write_panel(panel, a.out)
    print(f"{a.out}: {len(panel):,} rows, {panel['regNo'].nunique()} funds, "
          f"{panel['date'].nunique()} days")
