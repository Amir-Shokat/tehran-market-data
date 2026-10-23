"""Map Iranian mutual funds to their managers, guarantors and custodians.

    python scripts/fund_network.py                      # live data from FIPIRAN
    python scripts/fund_network.py --json saved.json    # a saved dependencygraph response
"""

import argparse
import json
from pathlib import Path

import pandas as pd

from tehran_data import FipiranClient, flatten_funds, fund_network, manager_concentration
from tehran_data.fipiran import to_html

p = argparse.ArgumentParser()
p.add_argument("--json", help="saved FIPIRAN dependencygraph response")
p.add_argument("--out", default="output")
a = p.parse_args()

if a.json:
    funds = flatten_funds(json.loads(Path(a.json).read_text(encoding="utf-8"))["items"])
else:
    funds = FipiranClient().funds()
funds = funds[funds["netAsset"].fillna(0) > 0]

out = Path(a.out)
out.mkdir(exist_ok=True)
g = fund_network(funds)
print(f"{len(funds)} funds with assets, {sum(1 for _, d in g.nodes(data=True) if d['kind'] == 'firm')} firms, "
      f"{g.number_of_edges()} links")
for role in ("manager", "guarantor", "custodian", "auditor"):
    if funds[role].notna().sum() == 0:
        continue                       # this endpoint does not report the role
    table, hhi = manager_concentration(funds, role)
    top5 = table["share"].head(5).sum()
    print(f"{role:9s}: {len(table):3d} firms, top-5 share of assets {top5:.1%}, HHI {hhi:,.0f}")
    table.to_csv(out / f"concentration_{role}.csv", encoding="utf-8-sig")
try:
    to_html(g, str(out / "fund_network.html"))
    print(f"Interactive network: {out / 'fund_network.html'}")
except ImportError:
    print("pip install pyvis for the interactive network")
