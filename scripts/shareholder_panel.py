"""Build a daily panel of major shareholders for instruments listed in a CSV.

    python scripts/shareholder_panel.py instruments.csv --start 20250101 --end 20250907

instruments.csv needs columns ``inscode`` and ``symbol`` (other columns are carried through);
use ``--filter-type 8`` to keep only mutual funds when a ``paper_type_number`` column exists.
"""

import argparse
import logging
from datetime import date

import pandas as pd

from tehran_data import TsetmcClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
p = argparse.ArgumentParser()
p.add_argument("instruments")
p.add_argument("--start", required=True)
p.add_argument("--end", default=date.today().strftime("%Y%m%d"))
p.add_argument("--filter-type", type=int)
p.add_argument("--out", default="shareholders_panel.csv")
a = p.parse_args()

ins = pd.read_csv(a.instruments, dtype={"inscode": str})
if a.filter_type is not None:
    ins = ins[ins["paper_type_number"] == a.filter_type]
panel = TsetmcClient().shareholder_panel(ins, a.start, a.end)
panel.to_csv(a.out, index=False, encoding="utf-8-sig")       # BOM so Excel shows Persian text
print(f"{len(panel)} rows for {ins.shape[0]} instruments -> {a.out}")
